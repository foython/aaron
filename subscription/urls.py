from django.urls import path
from . import views
from .webhook import stripe_webhook

urlpatterns = [
    path("create-checkout-session/", views.create_subscription_session, name="create_checkout_session"),
    path('cancel_subscription/', views.cancel_subscription, name='cancel_subscription'),
    path("webhook/", stripe_webhook, name="stripe_webhook"),
]

