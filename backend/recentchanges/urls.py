"""URL patterns for the recentchanges app."""
from django.urls import path

from .views import RecentEditsView

urlpatterns = [
    path('', RecentEditsView.as_view(), name='recent_edits'),
]
