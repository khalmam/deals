from django.urls import path

from . import live_views, views

urlpatterns = [
    path("", views.home, name="home"),
    path("deals/", views.deal_list, name="deals"),
    path("activity/", views.activity, name="activity"),
    path("health", views.health),
    path("deals/<uuid:deal_id>/", views.deal_page, name="deal"),
    path("deals/<uuid:deal_id>/receipt/", views.receipt_page, name="receipt"),
    path("start/", live_views.start_page, name="start"),
    path("api/deals", live_views.api_create),
    path("api/deals/<uuid:deal_id>", live_views.api_get),
    path("api/deals/<uuid:deal_id>/offers", live_views.api_say),
    path("api/deals/<uuid:deal_id>/advance", live_views.api_advance),
    path("api/deals/<uuid:deal_id>/delivery", live_views.api_delivery),
    path("api/deals/<uuid:deal_id>/cancel", live_views.api_cancel),
    path("api/deals/<uuid:deal_id>/refresh", live_views.api_refresh),
    path("deals/<uuid:deal_id>/return/", live_views.hold_return, name="hold_return"),
    path("webhooks/paypal/", views.paypal_webhook),
]
