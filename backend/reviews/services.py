"""Service layer for interacting with Wikimedia projects via Pywikibot."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime

import mwparserfromhell
import pywikibot
from django.db import transaction
from django.utils import timezone as dj_timezone

from .models import EditorProfile, PendingPage, PendingRevision, Wiki

logger = logging.getLogger(__name__)

os.environ.setdefault("PYWIKIBOT2_NO_USER_CONFIG", "1")
os.environ.setdefault("PYWIKIBOT_NO_USER_CONFIG", "2")


@dataclass
class RevisionPayload:
    revid: int
    parentid: int | None
    user: str | None
    userid: int | None
    timestamp: datetime
    comment: str
    sha1: str
    wikitext: str
    tags: list[str]
    categories: list[str]


class WikiClient:
    """Client responsible for synchronising data for a wiki."""

    def __init__(self, wiki: Wiki):
        self.wiki = wiki
        self.site = pywikibot.Site(code=wiki.code, fam=wiki.family)

    def fetch_pending_pages(self, limit: int = 50) -> list[PendingPage]:
        """Fetch the oldest pending pages and cache them in the database."""

        request = self.site._simple_request(
            action="query",
            format="json",
            list="oldreviewedpages",
            ornamespace=0,
            ornlimit=str(limit),
            formatversion=2,
        )
        payload = request.submit()
        pages: list[PendingPage] = []

        with transaction.atomic():
            PendingRevision.objects.filter(page__wiki=self.wiki).delete()
            PendingPage.objects.filter(wiki=self.wiki).delete()
            for entry in payload.get("query", {}).get("oldreviewedpages", []):
                pending_since = None
                if entry.get("pendingSince"):
                    pending_since = datetime.fromisoformat(
                        entry["pendingSince"].replace("Z", "+00:00")
                    )
                page = PendingPage.objects.create(
                    wiki=self.wiki,
                    pageid=entry["pageid"],
                    title=entry["title"],
                    stable_revid=entry.get("revid", 0),
                    pending_since=pending_since,
                )
                pages.append(page)

        return pages

    def fetch_revisions_for_page(self, page: PendingPage) -> list[PendingRevision]:
        """Fetch pending revisions for a single page using Pywikibot."""

        request = self.site._simple_request(
            action="query",
            pageids=str(page.pageid),
            prop="revisions",
            rvprop="ids|timestamp|user|userid|comment|sha1|tags|content",
            rvslots="main",
            rvdir="newer",
            rvstartid=str(page.stable_revid),
            format="json",
            formatversion=2,
        )
        data = request.submit()
        revisions_data = data.get("query", {}).get("pages", [])
        if not revisions_data:
            return []
        page_data = revisions_data[0]
        revisions: list[PendingRevision] = []
        for revision in page_data.get("revisions", []):
            if revision["revid"] <= page.stable_revid:
                continue
            text = revision.get("slots", {}).get("main", {}).get("content", "")
            categories = parse_categories(text)
            payload = RevisionPayload(
                revid=revision["revid"],
                parentid=revision.get("parentid"),
                user=revision.get("user"),
                userid=revision.get("userid"),
                timestamp=datetime.fromisoformat(
                    revision["timestamp"].replace("Z", "+00:00")
                ),
                comment=revision.get("comment", ""),
                sha1=revision.get("sha1", ""),
                wikitext=text,
                tags=revision.get("tags", []),
                categories=categories,
            )
            revisions.append(self._save_revision(page, payload))
        return revisions

    def _save_revision(self, page: PendingPage, payload: RevisionPayload) -> PendingRevision:
        age = dj_timezone.now() - payload.timestamp
        revision, _ = PendingRevision.objects.update_or_create(
            page=page,
            revid=payload.revid,
            defaults={
                "parentid": payload.parentid,
                "user_name": payload.user or "",
                "user_id": payload.userid,
                "timestamp": payload.timestamp,
                "age_at_fetch": age,
                "sha1": payload.sha1,
                "comment": payload.comment,
                "change_tags": payload.tags,
                "wikitext": payload.wikitext,
                "categories": payload.categories,
            },
        )
        if payload.user:
            self.ensure_editor_profile(payload.user)
        return revision

    def ensure_editor_profile(self, username: str) -> EditorProfile:
        profile, created = EditorProfile.objects.get_or_create(
            wiki=self.wiki,
            username=username,
            defaults={
                "usergroups": [],
                "is_blocked": False,
                "is_bot": False,
                "is_autopatrolled": False,
                "is_autoreviewed": False,
            },
        )
        if created or profile.is_expired:
            user_info = next(self.site.users([username]), None)
            if user_info is None:
                return profile
            groups = sorted(user_info.get("groups", []))
            profile.usergroups = groups
            profile.is_blocked = bool(
                user_info.get("blocked")
                or user_info.get("blockid")
                or ("blocked" in user_info)
            )
            profile.is_bot = "bot" in groups
            profile.is_autopatrolled = "autopatrolled" in groups
            profile.is_autoreviewed = "autoreview" in groups or "autoreviewer" in groups
            profile.save(update_fields=[
                "usergroups",
                "is_blocked",
                "is_bot",
                "is_autopatrolled",
                "is_autoreviewed",
                "fetched_at",
            ])
        return profile

    def refresh(self) -> list[PendingPage]:
        pages = self.fetch_pending_pages()
        for page in pages:
            try:
                self.fetch_revisions_for_page(page)
            except Exception:  # pragma: no cover - logged for observability
                logger.exception("Failed to fetch revisions for %s", page.title)
        return pages


def parse_categories(wikitext: str) -> list[str]:
    code = mwparserfromhell.parse(wikitext or "")
    categories: list[str] = []
    for link in code.filter_wikilinks():
        target = str(link.title).strip()
        if target.lower().startswith("category:"):
            categories.append(target.split(":", 1)[-1])
    return sorted(set(categories))
