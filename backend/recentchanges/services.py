"""Services for interacting with Wikipedia recent changes via Pywikibot."""
from __future__ import annotations

from typing import Callable, Iterable, Protocol

import pywikibot
from pywikibot.exceptions import Error as PywikibotError
from pywikibot.site import APISite


class SupportsRecentChanges(Protocol):
    """Protocol for objects exposing the subset of the Pywikibot API we need."""

    def recentchanges(self, total: int, **kwargs: object) -> Iterable[dict]:
        """Return an iterable of recent change dictionaries."""


class RecentChangesError(RuntimeError):
    """Raised when fetching recent changes fails."""


def _default_site_factory(language: str) -> APISite:
    """Return a Pywikibot site for the given language."""

    return pywikibot.Site(language, 'wikipedia')


def fetch_recent_edits(
    language: str,
    limit: int = 50,
    *,
    site_factory: Callable[[str], SupportsRecentChanges] = _default_site_factory,
) -> list[dict]:
    """Fetch the latest edits for the provided Wikipedia language edition.

    Parameters
    ----------
    language:
        Wikipedia language code. Only project namespace is assumed.
    limit:
        Maximum number of edits to return.
    site_factory:
        Factory used to create the Pywikibot site. This is injectable for testing.
    """

    if limit <= 0:
        return []

    try:
        site = site_factory(language)
        changes = site.recentchanges(total=limit)
    except PywikibotError as exc:  # pragma: no cover - network errors are hard to trigger in tests
        raise RecentChangesError(str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safeguard for unexpected failures
        raise RecentChangesError(str(exc)) from exc

    results: list[dict] = []
    for change in changes:
        if len(results) >= limit:
            break
        results.append(
            {
                'title': change.get('title', ''),
                'user': change.get('user', ''),
                'timestamp': change.get('timestamp'),
                'comment': change.get('comment', ''),
                'oldid': change.get('old_revid'),
                'newid': change.get('revid'),
                'type': change.get('type'),
            }
        )
    return results
