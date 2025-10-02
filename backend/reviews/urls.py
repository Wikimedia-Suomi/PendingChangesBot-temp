from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/wikis/", views.api_wikis, name="api_wikis"),
    path("api/wikis/<int:pk>/refresh/", views.api_refresh, name="api_refresh"),
    path("api/wikis/<int:pk>/pending/", views.api_pending, name="api_pending"),
    path("api/wikis/<int:pk>/clear/", views.api_clear_cache, name="api_clear_cache"),
    path("api/wikis/<int:pk>/configuration/", views.api_configuration, name="api_configuration"),
]
