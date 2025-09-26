"""URL configuration for wiki_edits project."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include(('recentchanges.urls', 'recentchanges'), namespace='recentchanges')),
]
