"""Views for the recent changes application."""
from __future__ import annotations

import json
from typing import Any

from django.http import JsonResponse
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from .services import RecentChangesError, fetch_recent_edits

SUPPORTED_LANGUAGES = {'fi', 'en', 'hu', 'pl'}
DEFAULT_LANGUAGE = 'fi'
DEFAULT_EDIT_LIMIT = 50
MIN_EDIT_LIMIT = 1
MAX_EDIT_LIMIT = 200


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
                'config_url': reverse('recentchanges:config_page'),
                'default_edit_limit': DEFAULT_EDIT_LIMIT,
                'min_edit_limit': MIN_EDIT_LIMIT,
                'max_edit_limit': MAX_EDIT_LIMIT,
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
            limit_param = request.GET.get('limit')
            try:
                limit = int(limit_param) if limit_param is not None else DEFAULT_EDIT_LIMIT
            except (TypeError, ValueError):
                limit = DEFAULT_EDIT_LIMIT
            limit = max(MIN_EDIT_LIMIT, min(MAX_EDIT_LIMIT, limit))

            edits = fetch_recent_edits(language, limit=limit)
        except RecentChangesError as exc:
            return JsonResponse({'error': str(exc)}, status=503)

        return JsonResponse(
            {
                'language': language,
                'supported_languages': sorted(SUPPORTED_LANGUAGES),
                'limit': limit,
                'edits': edits,
            }
        )


class ConfigPageView(TemplateView):
    """Render the configuration page for Wikipedia preferences."""

    template_name = 'recentchanges/config.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        supported_languages = sorted(SUPPORTED_LANGUAGES)
        default_language = (
            DEFAULT_LANGUAGE if DEFAULT_LANGUAGE in SUPPORTED_LANGUAGES else (supported_languages[0] if supported_languages else '')
        )
        context.update(
            {
                'supported_languages_json': json.dumps(supported_languages),
                'default_language': default_language,
                'home_url': reverse('recentchanges:recent_edits_page'),
                'config_url': reverse('recentchanges:config_page'),
                'default_edit_limit': DEFAULT_EDIT_LIMIT,
                'min_edit_limit': MIN_EDIT_LIMIT,
                'max_edit_limit': MAX_EDIT_LIMIT,
            }
        )
        return context
