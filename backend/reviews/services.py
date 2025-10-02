"""Service layer for interacting with Wikimedia projects via Pywikibot."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import mwparserfromhell
import pywikibot
from pywikibot.data.superset import SupersetQuery
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
    superset_data: dict | None = None


class WikiClient:
    """Client responsible for synchronising data for a wiki."""

    def __init__(self, wiki: Wiki):
        self.wiki = wiki
        self.site = pywikibot.Site(code=wiki.code, fam=wiki.family)

    def fetch_pending_pages(self, limit: int = 50) -> list[PendingPage]:
        """Fetch the pending pages using Superset and cache them in the database."""

        limit = int(limit)
        if limit <= 0:
            return []

        sql_query = f"""
select 
   page_title,
   page_namespace,
   page_is_redirect,
   fp_page_id,
   fp_pending_since,
   fp_stable, 
   rev_id,
   rev_timestamp,
   rev_len,
   rev_parent_id,
   rev_deleted,
   rev_sha1,
   comment_text,
   a.actor_name,
   group_concat(DISTINCT(ctd_name)) as change_tags,
   group_concat(DISTINCT(ug_group)) as user_groups,
   group_concat(DISTINCT(ufg_group)) as user_former_groups,
   rc_bot,
   rc_patrolled
from 
   (SELECT * FROM flaggedpages ORDER BY fp_pending_since DESC LIMIT {limit}) as fp, 
   revision as r 
       LEFT JOIN change_tag ON r.rev_id=ct_rev_id 
       LEFT JOIN change_tag_def ON ct_tag_id = ctd_id
       LEFT JOIN recentchanges ON rc_this_oldid = r.rev_id AND rc_source="mw.edit"
   , 
   page as p,
   comment_revision,
   actor_revision as a
   LEFT JOIN user_groups ON a.actor_user=ug_user
   LEFT JOIN user_former_groups ON a.actor_user=ufg_user
where 
   fp_pending_since IS NOT NULL 
   AND r.rev_page=fp_page_id 
   AND page_id=fp_page_id 
   and page_namespace=0 
   AND r.rev_id>fp_stable 
   AND r.rev_actor=a.actor_id
   AND r.rev_comment_id=comment_id
GROUP BY r.rev_id
ORDER BY fp_pending_since, rev_id DESC
"""

        superset = SupersetQuery(site=self.site)
        payload = superset.query(sql_query)
        pages: list[PendingPage] = []
        pages_by_id: dict[int, PendingPage] = {}

        with transaction.atomic():
            PendingRevision.objects.filter(page__wiki=self.wiki).delete()
            PendingPage.objects.filter(wiki=self.wiki).delete()
            for entry in payload:
                pageid = entry.get("fp_page_id")
                try:
                    pageid_int = int(pageid)
                except (TypeError, ValueError):
                    continue
                page = pages_by_id.get(pageid_int)
                if page is None:
                    pending_since = parse_superset_timestamp(
                        entry.get("fp_pending_since")
                    )
                    page = PendingPage.objects.create(
                        wiki=self.wiki,
                        pageid=pageid_int,
                        title=entry.get("page_title", ""),
                        stable_revid=int(entry.get("fp_stable") or 0),
                        pending_since=pending_since,
                    )
                    pages_by_id[pageid_int] = page
                    pages.append(page)

                revid = entry.get("rev_id")
                try:
                    revid_int = int(revid)
                except (TypeError, ValueError):
                    continue

                superset_revision_timestamp = parse_superset_timestamp(
                    entry.get("rev_timestamp")
                )
                if superset_revision_timestamp is None:
                    superset_revision_timestamp = dj_timezone.now()

                payload_entry = RevisionPayload(
                    revid=revid_int,
                    parentid=_parse_optional_int(entry.get("rev_parent_id")),
                    user=entry.get("actor_name"),
                    userid=None,
                    timestamp=superset_revision_timestamp,
                    comment=entry.get("comment_text", "") or "",
                    sha1=entry.get("rev_sha1", "") or "",
                    wikitext="",
                    tags=parse_superset_list(entry.get("change_tags")),
                    categories=[],
                    superset_data=_prepare_superset_metadata(entry),
                )
                self._save_revision(page, payload_entry)

        return pages

    def fetch_revisions_for_page(self, page: PendingPage) -> list[PendingRevision]:
        """Fetch pending revisions for a single page using Pywikibot."""

        request = self.site.simple_request(
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
        defaults = {
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
        }
        if payload.superset_data is not None:
            defaults["superset_data"] = payload.superset_data

        revision, _ = PendingRevision.objects.update_or_create(
            page=page,
            revid=payload.revid,
            defaults=defaults,
        )
        if payload.user and payload.superset_data is None:
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


def parse_superset_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            timestamp = datetime.fromisoformat(normalized.replace(" ", "T"))
        except ValueError:
            if normalized.isdigit() and len(normalized) == 14:
                try:
                    timestamp = datetime.strptime(normalized, "%Y%m%d%H%M%S")
                except ValueError:
                    logger.warning("Unable to parse Superset timestamp: %s", value)
                    return None
                else:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                logger.warning("Unable to parse Superset timestamp: %s", value)
                return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp


def parse_superset_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item and item.strip()]


def _parse_optional_int(value) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _prepare_superset_metadata(entry: dict) -> dict:
    metadata = dict(entry)
    for key in ("change_tags", "user_groups", "user_former_groups"):
        if key in metadata and isinstance(metadata[key], str):
            metadata[key] = parse_superset_list(metadata[key])
    return metadata
