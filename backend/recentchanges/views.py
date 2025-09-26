"""Views for the recent changes application."""
from __future__ import annotations

import json
from typing import Any

from django.http import JsonResponse
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from .services import RecentChangesError, fetch_recent_edits
from .models import WikiConfiguration

SUPPORTED_LANGUAGES = {'fi', 'en', 'hu', 'pl'}
DEFAULT_LANGUAGE = 'fi'
DEFAULT_EDIT_LIMIT = 50
MIN_EDIT_LIMIT = 1
MAX_EDIT_LIMIT = 200
DEFAULT_AUTO_APPROVE_GROUPS = [
    'sysop',
    'bot',
    'reviewer',
    'editor',
    'patroller',
    'autoreview',
    'autoreviewer',
]
AVAILABLE_AUTO_APPROVE_GROUPS = list(dict.fromkeys(DEFAULT_AUTO_APPROVE_GROUPS))


def _normalize_groups(groups: list[str]) -> list[str]:
    """Return a list of valid, de-duplicated groups in display order."""

    order = {group: index for index, group in enumerate(AVAILABLE_AUTO_APPROVE_GROUPS)}
    seen: set[str] = set()
    normalized: list[str] = []
    for group in groups:
        if not isinstance(group, str):
            continue
        name = group.strip().lower()
        if not name or name not in order or name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    normalized.sort(key=lambda value: order[value])
    return normalized


DEFAULT_NORMALIZED_AUTO_APPROVE_GROUPS = _normalize_groups(DEFAULT_AUTO_APPROVE_GROUPS)


class RecentEditsPageView(TemplateView):
    """Render the single-page interface for browsing recent edits."""

    template_name = 'recentchanges/index.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        supported_languages = sorted(SUPPORTED_LANGUAGES)
        if supported_languages:
            default_language = (
                DEFAULT_LANGUAGE
                if DEFAULT_LANGUAGE in SUPPORTED_LANGUAGES
                else supported_languages[0]
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

        config, _ = WikiConfiguration.objects.get_or_create(
            language_code=language,
            defaults={'auto_approve_groups': list(DEFAULT_NORMALIZED_AUTO_APPROVE_GROUPS)},
        )
        normalized_auto_groups = set(_normalize_groups(config.auto_approve_groups or []))

        annotated_edits: list[dict[str, Any]] = []
        for edit in edits:
            normalized_user_groups = [
                group.strip().lower()
                for group in edit.get('user_groups', [])
                if isinstance(group, str) and group.strip()
            ]
            annotated_edits.append(
                {
                    **edit,
                    'user_groups': normalized_user_groups,
                    'auto_approved': bool(normalized_auto_groups.intersection(normalized_user_groups)),
                }
            )

        return JsonResponse(
            {
                'language': language,
                'supported_languages': sorted(SUPPORTED_LANGUAGES),
                'limit': limit,
                'edits': annotated_edits,
            }
        )


class ConfigPageView(TemplateView):
    """Render the configuration page for Wikipedia preferences."""

    template_name = 'recentchanges/config.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        supported_languages = sorted(SUPPORTED_LANGUAGES)
        default_language = (
            DEFAULT_LANGUAGE
            if DEFAULT_LANGUAGE in SUPPORTED_LANGUAGES
            else (supported_languages[0] if supported_languages else '')
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
                'wiki_config_api_url': reverse('recentchanges:wiki_config'),
                'available_auto_approve_groups_json': json.dumps(AVAILABLE_AUTO_APPROVE_GROUPS),
                'default_auto_approve_groups_json': json.dumps(DEFAULT_AUTO_APPROVE_GROUPS),
            }
        )
        return context


class WikiConfigurationView(View):
    """Provide read/write access to per-wiki configuration."""

    def get(self, request, *args, **kwargs):  # type: ignore[override]
        language = (request.GET.get('lang') or DEFAULT_LANGUAGE).lower()
        if language not in SUPPORTED_LANGUAGES:
            return JsonResponse(
                {
                    'error': 'Unsupported language code.',
                    'supported_languages': sorted(SUPPORTED_LANGUAGES),
                },
                status=400,
            )

        config, _ = WikiConfiguration.objects.get_or_create(
            language_code=language,
            defaults={'auto_approve_groups': _normalize_groups(DEFAULT_AUTO_APPROVE_GROUPS)},
        )
        return JsonResponse(
            {
                'language': language,
                'auto_approve_groups': _normalize_groups(config.auto_approve_groups or []),
                'available_auto_approve_groups': AVAILABLE_AUTO_APPROVE_GROUPS,
            }
        )

    def post(self, request, *args, **kwargs):  # type: ignore[override]
        try:
            body = request.body.decode('utf-8') or '{}'
            payload = json.loads(body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)

        language = (payload.get('language') or DEFAULT_LANGUAGE).lower()
        if language not in SUPPORTED_LANGUAGES:
            return JsonResponse(
                {
                    'error': 'Unsupported language code.',
                    'supported_languages': sorted(SUPPORTED_LANGUAGES),
                },
                status=400,
            )

        groups = payload.get('auto_approve_groups')
        if not isinstance(groups, list):
            return JsonResponse({'error': 'auto_approve_groups must be a list.'}, status=400)

        normalized_groups = _normalize_groups(groups)

        config, _ = WikiConfiguration.objects.get_or_create(
            language_code=language,
            defaults={'auto_approve_groups': _normalize_groups(DEFAULT_AUTO_APPROVE_GROUPS)},
        )
        config.auto_approve_groups = normalized_groups
        config.save(update_fields=['auto_approve_groups'])

        return JsonResponse(
            {
                'language': language,
                'auto_approve_groups': config.auto_approve_groups,
                'available_auto_approve_groups': AVAILABLE_AUTO_APPROVE_GROUPS,
            }
        )
