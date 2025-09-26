"""URL patterns for the recentchanges app."""
from django.urls import path

from .views import ConfigPageView, RecentEditsPageView, RecentEditsView

app_name = 'recentchanges'

urlpatterns = [
    path('', RecentEditsPageView.as_view(), name='recent_edits_page'),
    path('config/', ConfigPageView.as_view(), name='config_page'),
    path('api/recent-edits/', RecentEditsView.as_view(), name='recent_edits'),
]
