"""Views for the recent changes application."""
from __future__ import annotations

import json
from typing import Any

from django.http import JsonResponse
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from .services import RecentChangesError, fetch_recent_edits

SUPPORTED_LANGUAGES = {'fi', 'en'}
DEFAULT_LANGUAGE = 'fi'


class RecentEditsPageView(TemplateView):
    """Render the single-page interface for browsing recent edits."""

    template_name = 'recentchanges/index.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        supported_languages = sorted(SUPPORTED_LANGUAGES)
        if supported_languages:
            default_language = (
                DEFAULT_LANGUAGE if DEFAULT_LANGUAGE in SUPPORTED_LANGUAGES else supported_languages[0]
            )
        else:
            default_language = ''
        context.update(
            {
                'supported_languages_json': json.dumps(supported_languages),
                'default_language': default_language,
                'api_url': reverse('recentchanges:recent_edits'),
            }
        )
        return context


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
