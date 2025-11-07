from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework import status
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import BasePermission, IsAuthenticated
from django.contrib.auth import get_user_model
from datetime import datetime, timedelta
from accounts.serializers import CustomUserSerializer
from accounts.models import CustomUser
from django.conf import settings
from django.http import JsonResponse
import os, json
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv 
load_dotenv()
CustomUser = get_user_model()
from django.utils import timezone

import stripe
stripe.api_key = os.getenv("STRIPE_API_KEY")
User = get_user_model()

@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_subscription_session(request):
    try:
        user = request.user
        email = user.email
        user_id = user.id

        plan_type = request.data.get("plan_type", "").lower()
        if plan_type not in ["small", "medium"]:
            return Response(
                {"error": "Invalid plan type. Choose 'small' or 'medium'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 🔒 Secure server-side plan definitions
        PLAN_MAP = {
            "small": {
                "amount": 20000,  # 200 EUR in cents
                "currency": "eur",
                "name": "Small Enterprise",
                "description": "Perfect for growing teams with moderate automation needs",
                "limits": { 
                    "duration": 30,                   
                    "processes": 5,
                    "chatbot_inquiries": 150
                }
            },
            "medium": {
                "amount": 75000,  # 750 EUR in cents
                "currency": "eur",
                "name": "Medium Enterprise",
                "description": "Ideal for mid-sized companies scaling automation",
                "limits": { 
                    "duration": 30,                   
                    "processes": 25,
                    "chatbot_inquiries": 500
                }
            }
        }

        plan = PLAN_MAP[plan_type]

        # 🧩 Prevent double subscription
        if user.is_subscribed:
            return Response(
                {"error": "User already has an active subscription."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 🧩 Create or retrieve Stripe customer
        customers = stripe.Customer.list(email=email).data
        if customers:
            customer = customers[0]
        else:
            customer = stripe.Customer.create(
                email=email,
                metadata={"user_id": str(user_id)}
            )

        # 🧩 Create dynamic recurring price (monthly)
        price = stripe.Price.create(
        unit_amount=plan["amount"],
        currency=plan["currency"],
        recurring={"interval": "month"},
        product_data={
            "name": plan["name"],
            "metadata": {
                "plan_type": plan_type,
                "plan_description": plan["description"]
            }
        },
    )

        # 🧩 Create checkout session
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer.id,
            line_items=[{"price": price.id, "quantity": 1}],
            metadata={
                "user_id": user_id,
                "user_email": email,
                "plan_type": plan_type,
                "limits": json.dumps(plan["limits"]),
            },
            success_url=f"http://localhost:7006/dashboard/priceing?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"http://10.10.13.92:8000/cancel",
        )

        return Response({"checkout_url": session.url}, status=status.HTTP_200_OK)

    except KeyError as e:
        return Response({"error": f"Missing field: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



@api_view(['GET'])
def success(request):
    return Response({"Message": "Success"}, status=status.HTTP_200_OK)



@api_view(['GET'])
def cancel(request):
    return Response({"Message": "Cancel"}, status=status.HTTP_200_OK)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_subscription(request):
    user_profile = request.user
    subscription_id = getattr(user_profile, 'subscription_id', None)

    if not subscription_id:
        return Response(
            {"message": "No active subscription ID found for this account."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Fetch the latest subscription state first (helps with idempotency)
        sub = stripe.Subscription.retrieve(subscription_id)

        # If already canceled, clean up locally and exit
        if sub.get('status') == 'canceled':
            _finalize_local_cancellation(user_profile)
            return Response(
                {"message": "Subscription already canceled on Stripe. Local status updated."},
                status=status.HTTP_200_OK
            )

        # If already scheduled to cancel at period end, just inform the user
        if sub.get('cancel_at_period_end') is True:
            period_end_ts = sub.get('current_period_end')
            msg = _pending_cancel_msg(period_end_ts)
            # Reflect pending state locally (idempotent)
            user_profile.subscription_status = "pending_cancellation"
            user_profile.save(update_fields=["subscription_status"])
            return Response({"message": msg}, status=status.HTTP_200_OK)

        # Schedule cancellation at period end (soft cancel)
        canceled_subscription = stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True
        )

        period_end_ts = canceled_subscription.get('current_period_end')
        message = _pending_cancel_msg(period_end_ts)

        # Update local DB to reflect pending cancellation
        user_profile.subscription_status = "pending_cancellation"
        user_profile.save(update_fields=["subscription_status"])

        return Response({"message": message}, status=status.HTTP_200_OK)

    # --- Correct Stripe exceptions (module: stripe.error) ---
    except stripe.error.InvalidRequestError as e:
        # Common cases: "No such subscription", "already canceled", bad ID, etc.
        error_message = (e.user_message or str(e)).lower()

        if "no such subscription" in error_message or "already canceled" in error_message:
            _finalize_local_cancellation(user_profile)
            return Response(
                {"message": "Subscription not active on Stripe. Local status updated."},
                status=status.HTTP_200_OK
            )

        return Response(
            {"message": f"Stripe Invalid Request: {e.user_message or str(e)}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    except stripe.error.StripeError as e:
        # Network/auth/other Stripe API issues
        return Response(
            {"message": f"Stripe API Error: {e.user_message or str(e)}"},
            status=status.HTTP_502_BAD_GATEWAY
        )

    except Exception as e:
        # Unknown server-side issue
        return Response(
            {"message": f"Server error during cancellation: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ---- helpers ----

def _pending_cancel_msg(period_end_ts: int | None) -> str:
    if period_end_ts:
        # Stripe timestamps are seconds since epoch (UTC)
        period_end_date = datetime.fromtimestamp(period_end_ts, tz=py_tz.utc).strftime('%Y-%m-%d')
        return f"Subscription cancellation scheduled. You will retain access until {period_end_date}."
    return "Subscription cancellation scheduled. Check your dashboard for the exact access end date."

def _finalize_local_cancellation(user_profile):
    """
    Immediate local downgrade used when Stripe reports the sub is gone/canceled.
    """
    user_profile.is_subscribed = False
    user_profile.subscription_status = 'expired'
    user_profile.subscription_id = None
    user_profile.subsciption_expires_on = timezone.now()  # keep your existing field name
    # If you track the plan name, downgrade it visibly
    if hasattr(user_profile, 'subsciption_plan_name'):
        user_profile.subsciption_plan_name = 'Free'
    user_profile.save()


    
class IsAdminUser(BasePermission):
   
    def has_permission(self, request, view):
        
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True        
       
        return request.user and request.user.is_authenticated and request.user.role == 'ADMIN'
    


@api_view(['GET', 'PATCH'])
def subscribe_user_view(request, pk=None):
    
    if request.user.role != 'ADMIN':
        return Response({"detail": "You do not have permission to perform this action."},
                        status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        if pk:
            try:
                user = CustomUser.objects.get(pk=pk)
                serializer = CustomUserSerializer(user)
                return Response(serializer.data, status=status.HTTP_200_OK)
            except CustomUser.DoesNotExist:
                return Response({"detail": "Subscribed user not found."},
                                status=status.HTTP_404_NOT_FOUND)
        else:
            subscribed_users = CustomUser.objects.filter(is_subscribed=True)
            serializer = CustomUserSerializer(subscribed_users, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'PATCH':
        if request.user.role != 'ADMIN':
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)
        
        if not pk:
            return Response({"detail": "User ID is required in the URL to update."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            user_to_update = CustomUser.objects.get(pk=pk)
        except CustomUser.DoesNotExist:
            return Response({"detail": "User not found."},
                            status=status.HTTP_404_NOT_FOUND)
        
        # Check if a 'status' change is requested
        if 'status' in request.data:
            new_status = request.data.get('status')
            valid_statuses = [s[0] for s in CustomUser.STATUS]
            
            if new_status not in valid_statuses:
                return Response(
                    {"detail": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            user_to_update.status = new_status
            user_to_update.save()
            
            serializer = CustomUserSerializer(user_to_update)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # Check for subscription status update
        subscription_status = request.data.get('subscription_status')
        
        if subscription_status:
            if user_to_update.is_subscribed and user_to_update.subscription_status == subscription_status:
                return Response({"detail": "User is already subscribed."},
                                status=status.HTTP_409_CONFLICT)
            
            valid_packages = ['MONTHLY', 'QUARTERLY', 'HALF YEARLY', 'YEARLY']
            if subscription_status not in valid_packages:
                return Response(
                    {"detail": "Invalid subscription status. Must be one of: " + ", ".join(valid_packages)},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user_to_update.subscription_status = subscription_status
            user_to_update.is_subscribed = True
           
            if subscription_status == 'MONTHLY':
                user_to_update.subsciption_expires_on = datetime.now() + timedelta(days=30)
            elif subscription_status == 'QUARTERLY':
                user_to_update.subsciption_expires_on = datetime.now() + timedelta(days=90)
            elif subscription_status == 'HALF YEARLY':
                user_to_update.subsciption_expires_on = datetime.now() + timedelta(days=180)
            elif subscription_status == 'YEARLY':
                user_to_update.subsciption_expires_on = datetime.now() + timedelta(days=365)
            
            user_to_update.save()
            
            serializer = CustomUserSerializer(user_to_update)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        # Handle cases where neither status nor subscription_status is provided
        return Response(
            {"detail": "The 'subscription_status' or 'status' field is required to update data."},
            status=status.HTTP_400_BAD_REQUEST
        )
        

@api_view(['GET'])
def non_subscribe_user_view(request, pk=None):
    
    if request.user.role != 'ADMIN':
        return Response({"detail": "You do not have permission to perform this action."},
                        status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        if pk:
            try:
                user = CustomUser.objects.get(pk=pk, is_subscribed=False)
                serializer = CustomUserSerializer(user)
                return Response(serializer.data, status=status.HTTP_200_OK)
            except CustomUser.DoesNotExist:
                return Response({"detail": "Nonsubscribed user not found."},
                                status=status.HTTP_404_NOT_FOUND)
        else:
            subscribed_users = CustomUser.objects.filter(is_subscribed=False)
            serializer = CustomUserSerializer(subscribed_users, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def cancel_subscription_by_pk(request, pk):
      
    try:     
        user_profile = CustomUser.objects.get(pk=pk)

        if user_profile.is_subscribed == True:                              
      
            user_profile.subscription_status = "cancelled"
            user_profile.is_subscribed = False
            user_profile.subsciption_expires_on = None
            user_profile.save()

            return Response(
                {"Message": "Subscription Deleted Successfully."},
                status=status.HTTP_200_OK
            )
    except CustomUser.DoesNotExist:

        return Response(
            {"Message": "User profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except stripe.error.StripeError as e:
    
        return Response(
            {"Message": f"Stripe error: {e.user_message}"},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {"Message": f"An unexpected error occurred: {e}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
