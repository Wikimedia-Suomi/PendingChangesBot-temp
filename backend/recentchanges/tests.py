"""Unit tests for the recentchanges app."""
from __future__ import annotations

from typing import Iterable
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse

from .services import RecentChangesError, fetch_recent_edits
from .views import DEFAULT_EDIT_LIMIT, MAX_EDIT_LIMIT, MIN_EDIT_LIMIT


class _FakeSite:
    """Simple fake Pywikibot site for testing."""

    def __init__(self, changes: Iterable[dict]):
        self._changes = list(changes)
        self.requested_total: int | None = None

    def recentchanges(self, total: int, **_: object) -> Iterable[dict]:
        self.requested_total = total
        return iter(self._changes)


class FetchRecentEditsTests(SimpleTestCase):
    """Tests for the fetch_recent_edits service."""

    def test_returns_trimmed_change_list(self) -> None:
        changes = [
            {
                'title': 'Page 1',
                'user': 'UserA',
                'timestamp': '2023-01-01T00:00:00Z',
                'comment': 'Test comment',
                'old_revid': 1,
                'revid': 2,
                'type': 'edit',
            },
            {
                'title': 'Page 2',
                'user': 'UserB',
                'timestamp': '2023-01-01T01:00:00Z',
                'comment': 'Test comment 2',
                'old_revid': 3,
                'revid': 4,
                'type': 'edit',
            },
        ]
        fake_site = _FakeSite(changes)

        result = fetch_recent_edits('fi', limit=1, site_factory=lambda _: fake_site)

        self.assertEqual(len(result), 1)
        self.assertEqual(fake_site.requested_total, 1)
        self.assertEqual(result[0]['title'], 'Page 1')

    def test_returns_empty_list_for_non_positive_limit(self) -> None:
        result = fetch_recent_edits('fi', limit=0, site_factory=lambda _: _FakeSite([]))
        self.assertEqual(result, [])

    def test_wraps_errors(self) -> None:
        def failing_factory(_: str) -> _FakeSite:
            raise ValueError('boom')

        with self.assertRaises(RecentChangesError):
            fetch_recent_edits('fi', site_factory=failing_factory)


@override_settings(ROOT_URLCONF='wiki_edits.urls')
class RecentEditsViewTests(SimpleTestCase):
    """Tests for the API view."""

    def setUp(self) -> None:
        self.client = Client()

    @patch('recentchanges.views.fetch_recent_edits')
    def test_successful_response(self, mock_fetch) -> None:
        mock_fetch.return_value = [
            {
                'title': 'Page 1',
                'user': 'UserA',
                'timestamp': '2023-01-01T00:00:00Z',
                'comment': 'Example comment',
                'oldid': 1,
                'newid': 2,
                'type': 'edit',
            }
        ]

        response = self.client.get(f"{reverse('recentchanges:recent_edits')}?lang=fi")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['language'], 'fi')
        self.assertEqual(len(payload['edits']), 1)
        mock_fetch.assert_called_once_with('fi', limit=DEFAULT_EDIT_LIMIT)

    def test_rejects_unsupported_language(self) -> None:
        response = self.client.get(f"{reverse('recentchanges:recent_edits')}?lang=sv")
        self.assertEqual(response.status_code, 400)

    @patch('recentchanges.views.fetch_recent_edits', side_effect=RecentChangesError('boom'))
    def test_handles_service_errors(self, mock_fetch) -> None:
        response = self.client.get(f"{reverse('recentchanges:recent_edits')}?lang=fi")
        self.assertEqual(response.status_code, 503)
        mock_fetch.assert_called_once_with('fi', limit=DEFAULT_EDIT_LIMIT)

    @patch('recentchanges.views.fetch_recent_edits')
    def test_limit_parameter_is_clamped(self, mock_fetch) -> None:
        mock_fetch.return_value = []

        response = self.client.get(
            f"{reverse('recentchanges:recent_edits')}?lang=fi&limit={MAX_EDIT_LIMIT + 50}"
        )

        self.assertEqual(response.status_code, 200)
        mock_fetch.assert_called_once_with('fi', limit=MAX_EDIT_LIMIT)
        payload = response.json()
        self.assertEqual(payload['limit'], MAX_EDIT_LIMIT)

    @patch('recentchanges.views.fetch_recent_edits')
    def test_invalid_limit_falls_back_to_default(self, mock_fetch) -> None:
        mock_fetch.return_value = []

        response = self.client.get(
            f"{reverse('recentchanges:recent_edits')}?lang=fi&limit=not-a-number"
        )

        self.assertEqual(response.status_code, 200)
        mock_fetch.assert_called_once_with('fi', limit=DEFAULT_EDIT_LIMIT)
        payload = response.json()
        self.assertEqual(payload['limit'], DEFAULT_EDIT_LIMIT)

    @patch('recentchanges.views.fetch_recent_edits')
    def test_limit_parameter_respects_minimum(self, mock_fetch) -> None:
        mock_fetch.return_value = []

        response = self.client.get(
            f"{reverse('recentchanges:recent_edits')}?lang=fi&limit={MIN_EDIT_LIMIT - 5}"
        )

        self.assertEqual(response.status_code, 200)
        mock_fetch.assert_called_once_with('fi', limit=MIN_EDIT_LIMIT)
        payload = response.json()
        self.assertEqual(payload['limit'], MIN_EDIT_LIMIT)


@override_settings(ROOT_URLCONF='wiki_edits.urls')
class RecentEditsPageViewTests(SimpleTestCase):
    """Tests for the frontend page view."""

    def setUp(self) -> None:
        self.client = Client()

    def test_page_renders_successfully(self) -> None:
        response = self.client.get(reverse('recentchanges:recent_edits_page'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('supported_languages_json', response.context)
        self.assertIn('default_language', response.context)
        self.assertIn('api_url', response.context)
        self.assertIn('config_url', response.context)
        self.assertIn('default_edit_limit', response.context)


@override_settings(ROOT_URLCONF='wiki_edits.urls')
class ConfigPageViewTests(SimpleTestCase):
    """Tests for the configuration page."""

    def setUp(self) -> None:
        self.client = Client()

    def test_config_page_renders(self) -> None:
        response = self.client.get(reverse('recentchanges:config_page'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('supported_languages_json', response.context)
        self.assertIn('default_language', response.context)
        self.assertIn('default_edit_limit', response.context)
