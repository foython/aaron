import stripe
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
import os
import json # Required for parsing plan_data

# Ensure your CustomUser model is correctly imported
# from accounts.models import CustomUser # Assuming CustomUser is here
# For this example, we'll assume get_user_model() returns your CustomUser
User = get_user_model()

# --- CONFIGURATION (Load from environment) ---
# Assuming these environment variables are set
# load_dotenv()
# stripe.api_key = os.getenv("STRIPE_API_KEY")
# STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
# NOTE: For a runnable example, ensure stripe.api_key and STRIPE_WEBHOOK_SECRET are defined.

# --- HELPER FUNCTIONS ---
def handle_subscription_started(user_email, subscription_id, plan_data):
    """Updates the CustomUser fields upon successful checkout completion."""
    try:
        user_profile = User.objects.get(email__iexact=user_email)

        duration_months = plan_data.get('duration_months')
        if duration_months is None or duration_months <= 0:
            duration_months = 1
            print(f"Warning: duration_months missing/invalid for {user_email}. Defaulting to 1 month.")

        days = duration_months * 30
        user_profile.subsciption_expires_on = timezone.now() + timedelta(days=days)

        user_profile.is_subscribed = True
        user_profile.subscription_id = subscription_id
        user_profile.subscription_status = f"{duration_months} Month Plan"

        # ✅ New field
        user_profile.subsciption_plan_name = plan_data.get('plan_type', 'unknown').capitalize()

        # Update limits
        user_profile.processes = plan_data.get('processes', 0)
        user_profile.chatbot_inquiries = plan_data.get('chatbot_inq', 0)

        user_profile.save()
        print(f"✅ Subscription activated for {user_email} ({user_profile.subsciption_plan_name}).")

    except User.DoesNotExist:
        print(f"❌ No user found with email {user_email}.")
    except Exception as e:
        print(f"⚠️ Error handling subscription start for {user_email}: {e}")



def handle_subscription_renewal(user_id, subscription_id, plan_data_str):
    """Updates the CustomUser fields upon successful invoice payment."""
    try:
        user_profile = User.objects.get(pk=user_id)

        try:
            plan_data = json.loads(plan_data_str)
        except json.JSONDecodeError:
            print(f"⚠️ Error parsing plan_data for renewal of user {user_id}. Using fallback.")
            plan_data = {}

        duration_months = plan_data.get('duration_months') or 1
        days = duration_months * 30

        user_profile.subsciption_expires_on = timezone.now() + timedelta(days=days)
        user_profile.is_subscribed = True
        user_profile.subscription_id = subscription_id
        user_profile.subscription_status = f"{duration_months} Month Plan"

        # ✅ Maintain plan name
        user_profile.subsciption_plan_name = plan_data.get('plan_type', user_profile.subsciption_plan_name).capitalize()

        user_profile.processes = plan_data.get('processes', user_profile.processes)
        user_profile.chatbot_inquiries = plan_data.get('chatbot_inq', user_profile.chatbot_inquiries)

        user_profile.save()
        print(f"🔁 Subscription renewed for {user_profile.email} ({user_profile.subsciption_plan_name}).")

    except User.DoesNotExist:
        print(f"❌ No user found with id {user_id}.")
    except Exception as e:
        print(f"⚠️ Error handling renewal for {user_id}: {e}")

def handle_failed_payment(user_id):
    """Updates the CustomUser status upon payment failure."""
    try:
        user_profile = User.objects.get(pk=user_id)

        user_profile.is_subscribed = False
        user_profile.subscription_status = 'payment_failed'
        user_profile.subscription_id = None # Clear subscription ID
        
        user_profile.save()

        print(f"Payment failed for user {user_id}, subscription suspended.")

    except User.DoesNotExist:
        print(f"No user found with user_id {user_id}.")



def handle_subscription_deleted(user_id, subscription_id):
    """Handles final deletion of a subscription (expired or canceled)."""
    try:
        user_profile = User.objects.get(pk=user_id)

        if user_profile.subscription_id != subscription_id:
            print(f"⚠️ Subscription ID mismatch for user {user_id}. Stored: {user_profile.subscription_id}")

        user_profile.is_subscribed = False
        user_profile.subscription_status = 'expired'
        user_profile.subscription_id = None
        user_profile.subsciption_expires_on = timezone.now()

        # ✅ Downgrade plan to 'free'
        user_profile.subsciption_plan_name = 'Free'

        user_profile.save()
        print(f"🚫 Subscription expired for {user_profile.email}, reverted to Free plan.")

    except User.DoesNotExist:
        print(f"❌ No user found with id {user_id}.")
    except Exception as e:
        print(f"⚠️ Error handling subscription deletion for {user_id}: {e}")


# --- WEBHOOK MAIN FUNCTION ---
@csrf_exempt
@require_http_methods(["POST"])
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")    

    # --- Verify and construct event ---
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        return HttpResponse('Invalid payload', status=400)
    except stripe.error.SignatureVerificationError:
        return HttpResponse('Invalid signature', status=400)

    # --- Secure plan definitions (mirror of backend create_subscription_session) ---
    PLAN_MAP = {
        "small": {
            "plan_type": "small",
            "duration_months": 1,
            "processes": 5,
            "chatbot_inq": 150,            
        },
        "medium": {
            "plan_type": "medium",
            "duration_months": 1,
            "processes": 25,
            "chatbot_inq": 500,            
        }
    }

    event_type = event['type']
    data = event['data']['object']

    # ✅ 1️⃣ CHECKOUT SESSION COMPLETED
    if event_type == 'checkout.session.completed':
        session = data
        subscription_id = session.get('subscription')
        user_email = session['metadata'].get('user_email')
        plan_type = session['metadata'].get('plan_type')

        if not (user_email and subscription_id and plan_type):
            print("⚠️ Missing email, plan_type, or subscription_id in session metadata.")
            return JsonResponse({'status': 'ignored'}, status=200)

        # Ensure plan_type is valid
        plan_data = PLAN_MAP.get(plan_type)
        if not plan_data:
            print(f"⚠️ Unknown plan_type '{plan_type}' in session metadata.")
            return JsonResponse({'status': 'ignored'}, status=200)

        # A. Activate subscription
        handle_subscription_started(user_email, subscription_id, plan_data)

        # B. Attach user_id + plan_type metadata to Stripe subscription
        try:
            user = User.objects.get(email__iexact=user_email)
            stripe.Subscription.modify(
                subscription_id,
                metadata={
                    "user_id": str(user.pk),
                    "plan_type": plan_type
                }
            )
        except User.DoesNotExist:
            print(f"❌ User {user_email} not found when updating Stripe metadata.")
        except Exception as e:
            print(f"⚠️ Error updating Stripe subscription metadata: {e}")

    # ✅ 2️⃣ INVOICE PAYMENT SUCCEEDED (renewal)
    elif event_type == 'invoice.payment_succeeded':
        invoice = data
        subscription_id = invoice.get('subscription')
        if not subscription_id:
            print("⚠️ invoice.payment_succeeded missing subscription_id.")
            return JsonResponse({'status': 'ignored'}, status=200)

        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            metadata = subscription.get('metadata', {})
            user_id = metadata.get('user_id')
            plan_type = metadata.get('plan_type')
            plan_data = PLAN_MAP.get(plan_type)
            if user_id and plan_data:
                handle_subscription_renewal(user_id, subscription_id, json.dumps(plan_data))
        except Exception as e:
            print(f"⚠️ Error processing invoice.payment_succeeded: {e}")

    # ✅ 3️⃣ PAYMENT FAILED
    elif event_type == 'invoice.payment_failed':
        invoice = data
        user_id = invoice.get('metadata', {}).get('user_id')
        if user_id:
            handle_failed_payment(user_id)
        else:
            print("⚠️ invoice.payment_failed missing user_id in metadata.")

    # ✅ 4️⃣ SUBSCRIPTION DELETED (canceled or expired)
    elif event_type == 'customer.subscription.deleted':
        subscription = data
        subscription_id = subscription.get('id')
        metadata = subscription.get('metadata', {})
        user_id = metadata.get('user_id')
        if user_id:
            handle_subscription_deleted(user_id, subscription_id)
        else:
            print(f"⚠️ Subscription deleted missing user_id: {subscription_id}")

    return JsonResponse({'status': 'success'}, status=200)
