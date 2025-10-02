from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import TestCase

from reviews.models import EditorProfile, PendingPage, PendingRevision, Wiki
from reviews.services import WikiClient, parse_categories


class FakeRequest:
    def __init__(self, data):
        self._data = data

    def submit(self):
        return self._data


class FakeSite:
    def __init__(self):
        self.response = {"query": {"pages": []}}
        self.users_data: dict[str, dict] = {}
        self.requests: list[dict] = []

    def simple_request(self, **kwargs):
        self.requests.append(kwargs)
        return FakeRequest(self.response)

    def users(self, users):
        for username in users:
            data = self.users_data.get(username)
            if data is not None:
                yield data
            else:
                yield {
                    "name": username,
                    "groups": [],
                }


class WikiClientTests(TestCase):
    def setUp(self):
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            api_endpoint="https://test.example/api.php",
        )
        self.fake_site = FakeSite()
        self.site_patcher = mock.patch(
            "reviews.services.pywikibot.Site",
            return_value=self.fake_site,
        )
        self.site_patcher.start()
        self.addCleanup(self.site_patcher.stop)
        self.superset_patcher = mock.patch("reviews.services.SupersetQuery")
        self.mock_superset_cls = self.superset_patcher.start()
        self.addCleanup(self.superset_patcher.stop)
        self.mock_superset = self.mock_superset_cls.return_value
        self.mock_superset.query.return_value = []

    def test_parse_categories_extracts_unique_names(self):
        wikitext = (
            "Some text [[Category:Example]] and [[category:Second|label]] "
            "and [[Category:Example]]"
        )
        categories = parse_categories(wikitext)
        self.assertEqual(categories, ["Example", "Second"])

    def test_fetch_pending_pages_caches_pages(self):
        self.mock_superset.query.return_value = [
            {
                "fp_page_id": 123,
                "page_title": "Example",
                "fp_stable": 10,
                "fp_pending_since": "2024-01-01T00:00:00Z",
                "rev_id": 11,
                "rev_timestamp": "2024-01-02 03:04:05",
                "rev_parent_id": 9,
                "comment_text": "Superset edit",
                "rev_sha1": "abc123",
                "change_tags": "mobile,pc",
                "user_groups": "autopatrolled,bot",
                "user_former_groups": "sysop",
                "actor_name": "SupersetUser",
            }
        ]
        client = WikiClient(self.wiki)
        pages = client.fetch_pending_pages(limit=10)
        self.assertEqual(len(pages), 1)
        page = PendingPage.objects.get()
        self.assertEqual(page.pageid, 123)
        self.assertEqual(page.stable_revid, 10)
        self.assertIsNotNone(page.pending_since)
        sql_argument = self.mock_superset.query.call_args[0][0]
        self.assertIn("LIMIT 10) as fp", sql_argument)
        revision = PendingRevision.objects.get()
        self.assertEqual(revision.revid, 11)
        self.assertEqual(revision.comment, "Superset edit")
        self.assertEqual(revision.change_tags, ["mobile", "pc"])
        self.assertEqual(revision.superset_data["user_groups"], ["autopatrolled", "bot"])
        self.assertEqual(revision.superset_data["user_former_groups"], ["sysop"])

    def test_fetch_revisions_for_page_saves_revision_and_editor(self):
        client = WikiClient(self.wiki)
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=1,
            title="Page",
            stable_revid=100,
        )
        self.fake_site.response = {
            "query": {
                "pages": [
                    {
                        "revisions": [
                            {
                                "revid": 101,
                                "parentid": 100,
                                "timestamp": "2024-01-01T12:00:00Z",
                                "user": "Example",
                                "userid": 55,
                                "comment": "Edit",
                                "sha1": "abc123",
                                "tags": ["tag1"],
                                "slots": {
                                    "main": {
                                        "content": "Text [[Category:Foo]]",
                                    }
                                },
                            }
                        ]
                    }
                ]
            }
        }
        self.fake_site.users_data["Example"] = {
            "name": "Example",
            "groups": ["user", "autopatrolled"],
        }
        revisions = client.fetch_revisions_for_page(page)
        self.assertEqual(len(revisions), 1)
        revision = PendingRevision.objects.get()
        self.assertEqual(revision.revid, 101)
        self.assertEqual(revision.categories, ["Foo"])
        profile = EditorProfile.objects.get(username="Example")
        self.assertTrue(profile.is_autopatrolled)

    def test_ensure_editor_profile_refreshes_after_expiry(self):
        client = WikiClient(self.wiki)
        profile = EditorProfile.objects.create(
            wiki=self.wiki,
            username="OldUser",
            usergroups=["user"],
            is_blocked=False,
            is_bot=False,
            is_autopatrolled=False,
            is_autoreviewed=False,
        )
        EditorProfile.objects.filter(pk=profile.pk).update(
            fetched_at=datetime.now(timezone.utc) - timedelta(minutes=200)
        )
        profile.refresh_from_db()
        self.fake_site.users_data["OldUser"] = {
            "name": "OldUser",
            "groups": ["user", "bot"],
            "blocked": True,
        }
        refreshed = client.ensure_editor_profile("OldUser")
        refreshed.refresh_from_db()
        self.assertTrue(refreshed.is_blocked)
        self.assertTrue(refreshed.is_bot)
        self.assertFalse(refreshed.is_autopatrolled)


class RefreshWorkflowTests(TestCase):
    @mock.patch("reviews.services.SupersetQuery")
    @mock.patch("reviews.services.pywikibot.Site")
    def test_refresh_handles_errors(self, mock_site, mock_superset):
        wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            api_endpoint="https://test.example/api.php",
        )
        fake_site = FakeSite()
        fake_site.response = {"query": {"pages": []}}
        mock_site.return_value = fake_site
        mock_superset.return_value.query.side_effect = RuntimeError("boom")
        client = WikiClient(wiki)
        with self.assertRaises(RuntimeError):
            client.refresh()
