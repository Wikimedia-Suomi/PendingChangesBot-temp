"""Views for the recent changes API."""
from __future__ import annotations

from django.http import JsonResponse
from django.views import View

from .services import RecentChangesError, fetch_recent_edits

SUPPORTED_LANGUAGES = {'fi', 'en'}


class RecentEditsView(View):
    """Provide a JSON endpoint that returns recent edits."""

    def get(self, request, *args, **kwargs):  # type: ignore[override]
        language = request.GET.get('lang', 'fi').lower()
        if language not in SUPPORTED_LANGUAGES:
            return JsonResponse(
                {
                    'error': 'Unsupported language code.',
                    'supported_languages': sorted(SUPPORTED_LANGUAGES),
                },
                status=400,
            )

        try:
            edits = fetch_recent_edits(language)
        except RecentChangesError as exc:
            return JsonResponse({'error': str(exc)}, status=503)

        return JsonResponse(
            {
                'language': language,
                'supported_languages': sorted(SUPPORTED_LANGUAGES),
                'edits': edits,
            }
        )
