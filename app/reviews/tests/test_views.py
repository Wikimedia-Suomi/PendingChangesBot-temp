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
        self.assertCountEqual(codes, ["de", "en", "pl", "fi"])

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

    def test_api_autoreview_marks_bot_revision_auto_approvable(self):
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=100,
            title="Bot Page",
            stable_revid=1,
        )
        PendingRevision.objects.create(
            page=page,
            revid=200,
            parentid=150,
            user_name="HelpfulBot",
            user_id=999,
            timestamp=datetime.now(timezone.utc) - timedelta(days=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(days=1),
            sha1="hash",
            comment="Automated edit",
            change_tags=[],
            wikitext="",
            categories=[],
            superset_data={"user_groups": ["bot"], "rc_bot": True},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["mode"], "dry-run")
        self.assertEqual(len(data["results"]), 1)
        result = data["results"][0]
        self.assertEqual(result["decision"]["status"], "approve")
        self.assertEqual(len(result["tests"]), 1)
        self.assertEqual(result["tests"][0]["status"], "passed")
        self.assertEqual(result["tests"][0]["id"], "bot-user")

    def test_api_autoreview_allows_configured_user_groups(self):
        config = self.wiki.configuration
        config.auto_approved_groups = ["sysop"]
        config.save(update_fields=["auto_approved_groups"])

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=101,
            title="Group Page",
            stable_revid=1,
        )
        PendingRevision.objects.create(
            page=page,
            revid=201,
            parentid=150,
            user_name="AdminUser",
            user_id=1000,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=5),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=5),
            sha1="hash2",
            comment="Admin edit",
            change_tags=[],
            wikitext="",
            categories=[],
            superset_data={"user_groups": ["Sysop"]},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["decision"]["status"], "approve")
        self.assertEqual(len(result["tests"]), 2)
        self.assertEqual(result["tests"][1]["status"], "passed")
        self.assertEqual(result["tests"][1]["id"], "auto-approved-group")

    def test_api_autoreview_blocks_on_blocking_categories(self):
        config = self.wiki.configuration
        config.blocking_categories = ["Secret"]
        config.save(update_fields=["blocking_categories"])

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=102,
            title="Blocked Page",
            stable_revid=1,
        )
        PendingRevision.objects.create(
            page=page,
            revid=202,
            parentid=160,
            user_name="RegularUser",
            user_id=1001,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=3),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=3),
            sha1="hash3",
            comment="Edit",
            change_tags=[],
            wikitext="",
            categories=["Secret"],
            superset_data={},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["decision"]["status"], "blocked")
        self.assertEqual(len(result["tests"]), 3)
        self.assertEqual(result["tests"][2]["status"], "failed")
        self.assertEqual(result["tests"][2]["id"], "blocking-categories")

    def test_api_autoreview_requires_manual_review_when_no_rules_apply(self):
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=103,
            title="Manual Page",
            stable_revid=1,
        )
        PendingRevision.objects.create(
            page=page,
            revid=203,
            parentid=170,
            user_name="Editor",
            user_id=1002,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=2),
            sha1="hash4",
            comment="Edit",
            change_tags=[],
            wikitext="",
            categories=["General"],
            superset_data={"user_groups": ["user"]},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["decision"]["status"], "manual")
        self.assertEqual(len(result["tests"]), 3)
        self.assertEqual(result["tests"][2]["status"], "passed")

    def test_api_autoreview_orders_revisions_from_oldest_to_newest(self):
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=104,
            title="Multiple Revisions",
            stable_revid=1,
        )
        older_timestamp = datetime.now(timezone.utc) - timedelta(days=2)
        newer_timestamp = datetime.now(timezone.utc) - timedelta(days=1)
        PendingRevision.objects.create(
            page=page,
            revid=301,
            parentid=200,
            user_name="Editor1",
            user_id=2001,
            timestamp=older_timestamp,
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(days=2),
            sha1="sha-old",
            comment="Old",
            change_tags=[],
            wikitext="",
            categories=[],
            superset_data={"user_groups": ["user"]},
        )
        PendingRevision.objects.create(
            page=page,
            revid=302,
            parentid=301,
            user_name="Editor2",
            user_id=2002,
            timestamp=newer_timestamp,
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(days=1),
            sha1="sha-new",
            comment="New",
            change_tags=[],
            wikitext="",
            categories=[],
            superset_data={"user_groups": ["user"]},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual([result["revid"] for result in results], [301, 302])
