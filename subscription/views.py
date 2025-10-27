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
        email = request.data["email"]
        amount = int(float(request.data["amount"]) * 100)  # in cents
        currency = request.data.get("currency", "usd")
        plan_data = json.dumps(request.data.get("plan_data", {}))
        user = User.objects.get(email=email)
        if user.is_subscribed:
            return Response(
                {"error": "User already has an active subscription."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1️⃣ Create or retrieve customer
        customers = stripe.Customer.list(email=email).data
        customer = customers[0] if customers else stripe.Customer.create(email=email)

        # 2️⃣ Create dynamic price (recurring)
        price = stripe.Price.create(
            unit_amount=amount,
            currency=currency,
            recurring={"interval": "year"},  # can be day, week, month, year
            product_data={"name": "Custom Subscription Plan"},
        )

        # 3️⃣ Create checkout session for subscription
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer.id,
            line_items=[{"price": price.id, "quantity": 1}],
            metadata={
                "user_email": email,
                "plan_data": plan_data,
            },
            success_url=f"http://10.10.13.92:8000/success?session_id={{CHECKOUT_SESSION_ID}}",
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
    subscription_id = user_profile.subscription_id
    
    if not subscription_id:
        return Response(
            {"Message": "No active subscription ID found for this account."}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Soft cancellation: Cancels at the end of the billing period
        canceled_subscription = stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True 
        )

        # FIX 1: Safely retrieve current_period_end using getattr().
        # If the attribute is missing, default to a message indicating the cancellation is pending.
        # Note: Stripe timestamps are in seconds.
        period_end_ts = getattr(canceled_subscription, 'current_period_end', None)

        if period_end_ts:
            # Convert timestamp to human-readable date for the message
            period_end_date = timezone.datetime.fromtimestamp(period_end_ts, tz=timezone.utc).strftime('%Y-%m-%d')
            message = f"Subscription cancellation scheduled. You will retain access until {period_end_date}."
        else:
            # Fallback message if the field is missing (e.g., if subscription was already weirdly configured)
            message = "Subscription cancellation scheduled. Please check your account dashboard for the exact access end date."


        # Update local DB status to reflect pending cancellation
        user_profile.subscription_status = "pending_cancellation"
        user_profile.save()
        
        return Response(
            {"Message": message}, 
            status=status.HTTP_200_OK
        )

    # FIX 2: Use the error path suggested by the traceback: stripe.api_resources.error or the base class
    # We will use the base class for all API errors which is stripe.APIError or the class from your old code
    # If the traceback suggests 'stripe' has no attribute 'error', we catch the base Stripe exception.
    except stripe.InvalidRequestError as e: 
    # If the above still fails, try 'except stripe.APIError as e:' or even 'except stripe.StripeError as e:'
    
        # Handle errors like 'No such subscription' or 'already canceled'
        error_message = str(e)
        if "No such subscription" in error_message or "already canceled" in error_message:
            # Clean up local DB state
            user_profile.subscription_status = "cancelled"
            user_profile.subscription_id = None
            user_profile.is_subscribed = False
            user_profile.subsciption_expires_on = timezone.now()
            user_profile.save()
            return Response(
                {"Message": "Subscription was already cancelled or does not exist on Stripe. Local status updated."}, 
                status=status.HTTP_200_OK
            )
        
        # Other API errors (e.g., authentication)
        return Response(
            {"Message": f"Stripe API Error: {e.user_message}"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
        
    except Exception as e:
        print(f"Unexpected error during cancellation: {e}")
        return Response(
            {"Message": "An unexpected server error occurred."}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

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
