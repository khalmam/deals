from django.urls import path

from . import views

urlpatterns = [path("", views.health), path("health", views.health)]
