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
        # Find user by email (case-insensitive)
        user_profile = User.objects.get(email__iexact=user_email)
        
        # 1. Get duration and feature limits from plan_data
        duration_months = plan_data.get('duration_months')
        
        # 2. Handle missing duration gracefully (default to 1 month)
        if duration_months is None or duration_months <= 0:
             duration_months = 1
             print(f"Warning: duration_months missing/invalid for {user_email}. Defaulting to 1 month.")

        # 3. Calculate expiration date: Use 30 days per month as an approximation
        days = duration_months * 30 
        user_profile.subsciption_expires_on = timezone.now() + timedelta(days=days)
        
        # 4. Set subscription status and IDs
        user_profile.is_subscribed = True
        user_profile.subscription_id = subscription_id
        user_profile.subscription_status = f"{duration_months} Month Plan"
        
        # 5. Update feature limits using fields from plan_data
        user_profile.processes = plan_data.get('processes', 0)
        user_profile.chatbot_inquiries = plan_data.get('chatbot_inq', 0) # Mapping 'chatbot_inq' to 'chatbot_inquiries'
        
        user_profile.save()

        print(f"Subscription activated for user {user_email}. Expires: {user_profile.subsciption_expires_on}.")

    except User.DoesNotExist:
        print(f"No user found with email {user_email}.")
    except Exception as e:
        print(f"Error handling subscription start for {user_email}: {e}")


def handle_subscription_renewal(user_id, subscription_id, plan_data_str):
    """Updates the CustomUser fields upon successful invoice payment."""
    try:
        # 1. Find user by primary key
        user_profile = User.objects.get(pk=user_id)
        
        # 2. Parse plan_data from string
        try:
            plan_data = json.loads(plan_data_str)
        except json.JSONDecodeError:
            print(f"Error parsing plan_data for renewal of user {user_id}. Using current duration.")
            plan_data = {} # Use empty dict if parsing fails

        duration_months = plan_data.get('duration_months')
        
        if duration_months is None or duration_months <= 0:
             duration_months = 1 
             print(f"Warning: duration_months missing/invalid for renewal of user {user_id}. Defaulting to 1 month.")

        # 3. Calculate new expiration date (Renewal adds time from NOW)
        days = duration_months * 30 
        user_profile.subsciption_expires_on = timezone.now() + timedelta(days=days)
        
        # 4. Set subscription status and IDs
        user_profile.is_subscribed = True
        user_profile.subscription_id = subscription_id
        user_profile.subscription_status = f"{duration_months} Month Plan"

        # 5. Update feature limits
        user_profile.processes = plan_data.get('processes', user_profile.processes)
        user_profile.chatbot_inquiries = plan_data.get('chatbot_inq', user_profile.chatbot_inquiries)

        user_profile.save()

        print(f"Subscription renewed for user {user_id}.")

    except User.DoesNotExist:
        print(f"No user found with user_id {user_id}.")
    except Exception as e:
        print(f"Error handling subscription renewal for {user_id}: {e}")


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
    """
    Handles the final deletion of a subscription from Stripe. 
    This is the point where access is truly revoked in your system.
    """
    try:
        user_profile = User.objects.get(pk=user_id)

        # Safety check: ensure we are deleting the correct subscription
        if user_profile.subscription_id != subscription_id:
            print(f"Warning: Subscription ID mismatch for user {user_id}. Stored: {user_profile.subscription_id}, Webhook: {subscription_id}")
            # Still proceed with cancellation if the webhook provides a valid ID
        
        # *** THIS IS WHERE is_subscribed is set to False ***
        user_profile.is_subscribed = False
        user_profile.subscription_status = 'expired'
        user_profile.subscription_id = None
        user_profile.subsciption_expires_on = timezone.now() # Mark it as expired now
        
        # Optional: Reset feature limits to the free tier (if applicable)
        # user_profile.processes = 0
        # user_profile.chatbot_inquiries = 0

        user_profile.save()

        print(f"Subscription {subscription_id} successfully marked as expired for user {user_id}.")

    except User.DoesNotExist:
        print(f"No user found with user_id {user_id} for subscription deletion.")
    except Exception as e:
        print(f"Error handling subscription deletion for {user_id}: {e}")


# --- WEBHOOK MAIN FUNCTION ---

@csrf_exempt
@require_http_methods(["POST"])
def stripe_webhook(request):    
    payload = request.body      
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    # NOTE: Replace with actual environment variable loading for production
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")                     

    # 1. Verify and Construct Event
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        return HttpResponse('Invalid payload', status=400)
    except stripe.error.SignatureVerificationError as e:
        return HttpResponse('Invalid signature', status=400)

  
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        subscription_id = session.get('subscription')
        
        user_email = session['metadata'].get('user_email')
        plan_data_str = session['metadata'].get('plan_data')
        
        if user_email and plan_data_str and subscription_id:
            try:
                plan_data = json.loads(plan_data_str)
                
                # A. Handle subscription activation and feature updates in your DB
                handle_subscription_started(user_email, subscription_id, plan_data)
                
                # B. Update Stripe Subscription metadata with user_id for future renewals
                try:
                    user = User.objects.get(email__iexact=user_email)
                    # Include user_id and plan_data string in the subscription metadata
                    metadata = {"user_id": str(user.pk), "plan_data": plan_data_str} 
                    stripe.Subscription.modify(subscription_id, metadata=metadata)
                except User.DoesNotExist:
                    print(f"Could not find user with email {user_email} to update Stripe metadata.")
                
            except json.JSONDecodeError:
                print("Error parsing plan_data from metadata.")
            except Exception as e:
                print(f"An unexpected error occurred during checkout.session.completed: {e}")
        else:
            print("Missing required data (email, plan, or subscription ID) for session completed.")

        
    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        subscription_id =  invoice.get('subscription')
        
        if subscription_id:
            try:
                subscription = stripe.Subscription.retrieve(subscription_id)
                metadata = subscription.get('metadata', {})
                user_id = metadata.get('user_id')
                plan_data_str = metadata.get('plan_data') 
                
                if user_id and plan_data_str:
                     handle_subscription_renewal(user_id, subscription_id, plan_data_str)

            except stripe.error.InvalidRequestError:
                print(f"Subscription {subscription_id} not found for renewal.")
        
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']

        # Try to get user_id from various places in the invoice object
        user_id = invoice.get('subscription_details', {}).get('metadata', {}).get('user_id') or \
                  invoice.get('metadata', {}).get('user_id')
        
        if user_id:
            handle_failed_payment(user_id)
        else:
            print("Could not find user_id in invoice metadata for payment_failed event.")

    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        subscription_id = subscription.get('id')
        metadata = subscription.get('metadata', {})
        user_id = metadata.get('user_id')
        
        # This function will set is_subscribed = False
        if user_id:
            handle_subscription_deleted(user_id, subscription_id)
        else:
            print(f"Subscription deleted event received but missing user_id in metadata: {subscription_id}")

    return JsonResponse({'status': 'success'}, status=200)

    