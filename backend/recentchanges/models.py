"""Database models for the recentchanges app."""
from __future__ import annotations

from django.db import models


class WikiConfiguration(models.Model):
    """Persist per-wiki configuration values."""

    language_code = models.CharField(max_length=10, unique=True)
    auto_approve_groups = models.JSONField(default=list)

    class Meta:
        ordering = ['language_code']

    def __str__(self) -> str:  # pragma: no cover - trivial representation
        return f"Configuration for {self.language_code}"
