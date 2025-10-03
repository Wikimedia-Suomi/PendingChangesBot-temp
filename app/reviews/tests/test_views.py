from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from reviews.models import PendingPage, PendingRevision, Wiki, WikiConfiguration


class ViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.wiki = Wiki.objects.create(
            name="Example Wiki",
            code="ex",
            api_endpoint="https://example.org/api.php",
        )
        WikiConfiguration.objects.create(wiki=self.wiki)

    def test_index_creates_default_wiki_if_missing(self):
        Wiki.objects.all().delete()
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending Changes Review")
        codes = list(Wiki.objects.values_list("code", flat=True))
        self.assertCountEqual(codes, ["de", "en", "pl", "pt"])

    @mock.patch("reviews.views.WikiClient")
    def test_api_refresh_returns_error_on_failure(self, mock_client):
        mock_client.return_value.refresh.side_effect = RuntimeError("failure")
        response = self.client.post(reverse("api_refresh", args=[self.wiki.pk]))
        self.assertEqual(response.status_code, 502)
        self.assertIn("error", response.json())

    @mock.patch("reviews.views.WikiClient")
    def test_api_refresh_success(self, mock_client):
        mock_client.return_value.refresh.return_value = []
        response = self.client.post(reverse("api_refresh", args=[self.wiki.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("pages", response.json())

    def test_api_pending_returns_cached_revisions(self):
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=1,
            title="Page",
            stable_revid=1,
        )
        revision = PendingRevision.objects.create(
            page=page,
            revid=2,
            parentid=1,
            user_name="User",
            user_id=10,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=2),
            sha1="hash",
            comment="Comment",
            change_tags=[],
            wikitext="",
            categories=[],
            superset_data={
                "user_groups": ["user", "autopatrolled"],
                "change_tags": ["tag"],
                "page_categories": ["Cat"],
                "rc_bot": False,
            },
        )
        response = self.client.get(reverse("api_pending", args=[self.wiki.pk]))
        payload = response.json()
        self.assertEqual(len(payload["pages"]), 1)
        rev_payload = payload["pages"][0]["revisions"][0]
        self.assertEqual(rev_payload["revid"], revision.revid)
        self.assertTrue(rev_payload["editor_profile"]["is_autopatrolled"])
        self.assertEqual(rev_payload["change_tags"], ["tag"])
        self.assertEqual(rev_payload["categories"], ["Cat"])

    def test_api_page_revisions_returns_revision_payload(self):
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=42,
            title="Example",
            stable_revid=1,
        )
        revision = PendingRevision.objects.create(
            page=page,
            revid=5,
            parentid=3,
            user_name="Another",
            user_id=20,
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=30),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(minutes=30),
            sha1="sha",
            comment="More",
            change_tags=[],
            wikitext="",
            categories=[],
            superset_data={
                "user_groups": ["editor", "autoreviewer"],
                "change_tags": ["foo"],
                "page_categories": ["Bar"],
                "rc_bot": False,
            },
        )

        url = reverse("api_page_revisions", args=[self.wiki.pk, page.pageid])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["pageid"], page.pageid)
        self.assertEqual(len(data["revisions"]), 1)
        payload = data["revisions"][0]
        self.assertEqual(payload["revid"], revision.revid)
        self.assertTrue(payload["editor_profile"]["is_autoreviewed"])
        self.assertEqual(payload["change_tags"], ["foo"])
        self.assertEqual(payload["categories"], ["Bar"])

    def test_api_clear_cache_deletes_records(self):
        PendingPage.objects.create(
            wiki=self.wiki,
            pageid=1,
            title="Page",
            stable_revid=1,
        )
        response = self.client.post(reverse("api_clear_cache", args=[self.wiki.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PendingPage.objects.count(), 0)

    def test_api_configuration_updates_settings(self):
        url = reverse("api_configuration", args=[self.wiki.pk])
        payload = {
            "blocking_categories": ["Foo"],
            "auto_approved_groups": ["sysop"],
        }
        response = self.client.put(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        config = self.wiki.configuration
        config.refresh_from_db()
        self.assertEqual(config.blocking_categories, ["Foo"])
        self.assertEqual(config.auto_approved_groups, ["sysop"])
