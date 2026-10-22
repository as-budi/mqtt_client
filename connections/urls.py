"""Profil koneksi. Semua diawali /connections/ (lihat config/urls.py)."""
from django.urls import path

from . import views

app_name = "connections"

urlpatterns = [
    path("", views.profile_list, name="list"),
    path("new/", views.profile_create, name="create"),
    path("<int:pk>/edit/", views.profile_edit, name="edit"),
    path("<int:pk>/duplicate/", views.profile_duplicate, name="duplicate"),
    path("<int:pk>/delete/", views.profile_delete, name="delete"),
]
