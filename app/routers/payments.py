import httpx
from fastapi import APIRouter, HTTPException, Depends, Request, status, BackgroundTasks
from typing import Dict, Optional
import uuid
from datetime import datetime, timedelta
import json
import asyncio
from supabase import PostgrestAPIResponse

from app.core.security import verify_token
from app.core.database import get_database
from app.core.config import settings

router = APIRouter()

# Subscription plans (Kenyan Shillings)
SUBSCRIPTION_PLANS = {
    "pro": {
        "name": "Pro Learner",
        "price": 500,  # KES
        "duration_days": 30,
        "features": [
            "Unlimited AI questions",
            "Advanced analytics",
            "Custom themes",
            "Priority support"
        ]
    },
    "premium": {
        "name": "Premium Scholar",
        "price": 1000,  # KES
        "duration_days": 30,
        "features": [
            "Everything in Pro",
            "Group study rooms",
            "Voice features",
            "Priority AI processing",
            "Advanced gamification"
        ]
    }
}

@router.get("/plans")
async def get_subscription_plans():
    """Get available subscription plans"""
    return {
        "plans": SUBSCRIPTION_PLANS,
        "currency": "KES",
        "payment_method": "M-Pesa via Instasend",
        "demo_available": True
    }

@router.post("/initiate")
async def initiate_payment(
    payment_data: Dict,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verify_token)
):
    """Initiate M-Pesa payment via Instasend"""
    
    plan_id = payment_data.get("plan_id")
    phone_number = payment_data.get("phone_number")
    demo_mode = payment_data.get("demo_mode", False)
    
    if plan_id not in SUBSCRIPTION_PLANS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid subscription plan")
    
    plan = SUBSCRIPTION_PLANS[plan_id]
    transaction_id = str(uuid.uuid4())
    
    # DEMO MODE - Perfect for hackathon!
    if demo_mode:
        db = await get_database()
        payment_record = {
            "id": transaction_id,
            "user_id": user_id,
            "plan_id": plan_id,
            "amount": plan["price"],
            "phone_number": phone_number or "254700000000",
            "status": "pending",
            "instasend_transaction_id": f"demo_{transaction_id}",
            "created_at": datetime.utcnow().isoformat()
        }
        
        # CORRECTED: Added await
        await db.table("payments").insert(payment_record).execute()
        
        # Simulate payment processing with background task
        background_tasks.add_task(simulate_payment_success, transaction_id, user_id, plan_id)
        
        return {
            "success": True,
            "transaction_id": transaction_id,
            "message": "🎉 DEMO: M-Pesa payment initiated! Check status in 3 seconds...",
            "amount": plan["price"],
            "plan": plan["name"],
            "demo_mode": True,
            "status_check_url": f"/api/payments/status/{transaction_id}"
        }
    
    # REAL INSTASEND INTEGRATION (CORRECTED: Using httpx for async calls)
    instasend_payload = {
        "amount": plan["price"],
        "phone": phone_number,
        "account_reference": f"STUDY_BUDDY_{user_id}",
        "description": f"AI Study Buddy {plan['name']} Subscription",
        "transaction_id": transaction_id
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://sandbox.instasend.com/api/v1/payment/mpesa-stk-push/",
                json=instasend_payload,
                headers={
                    "Authorization": f"Bearer {settings.instasend_api_key}",
                    "Content-Type": "application/json"
                }
            )
        
        response.raise_for_status() # Raise exception for bad status codes
        instasend_response = response.json()
        
        db = await get_database()
        payment_record = {
            "id": transaction_id,
            "user_id": user_id,
            "plan_id": plan_id,
            "amount": plan["price"],
            "phone_number": phone_number,
            "status": "pending",
            "instasend_transaction_id": instasend_response.get("transaction_id"),
            "created_at": datetime.utcnow().isoformat()
        }
        
        # CORRECTED: Added await
        db.table("payments").insert(payment_record).execute()
        
        return {
            "success": True,
            "transaction_id": transaction_id,
            "message": "Payment initiated! Check your phone for M-Pesa prompt 📱",
            "amount": plan["price"],
            "plan": plan["name"],
            "status_check_url": f"/api/payments/status/{transaction_id}"
        }
            
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Payment initiation failed: {e.response.text}"
        )
    except httpx.RequestError as e:
        # Fallback to demo mode if Instasend is unavailable
        print(f"Instasend request failed: {e}. Falling back to demo mode.")
        return await initiate_payment({**payment_data, "demo_mode": True}, background_tasks, user_id)

@router.get("/status/{transaction_id}")
async def check_payment_status(
    transaction_id: str,
    user_id: str = Depends(verify_token)
):
    """Check payment status"""
    db = await get_database()
    
    # CORRECTED: Added await
    payment_result: PostgrestAPIResponse =  db.table("payments").select("*").eq("id", transaction_id).eq("user_id", user_id).execute()
    
    if not payment_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    
    payment = payment_result.data[0]
    
    return {
        "transaction_id": transaction_id,
        "status": payment["status"],
        "amount": payment["amount"],
        "plan_id": payment["plan_id"],
        "created_at": payment["created_at"],
        "completed_at": payment.get("completed_at")
    }

@router.post("/demo-complete")
async def demo_payment_complete(
    payment_data: Dict,
    user_id: str = Depends(verify_token)
):
    """Complete demo payment instantly (for hackathon demo)"""
    
    plan_id = payment_data.get("plan_id")
    
    if plan_id not in SUBSCRIPTION_PLANS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan")
    
    plan = SUBSCRIPTION_PLANS[plan_id]
    transaction_id = str(uuid.uuid4())
    
    db = await get_database()
    
    # Create completed payment record
    payment_record = {
        "id": transaction_id,
        "user_id": user_id,
        "plan_id": plan_id,
        "amount": plan["price"],
        "phone_number": "254700000000",
        "status": "completed",
        "instasend_transaction_id": f"demo_{transaction_id}",
        "created_at": datetime.utcnow().isoformat(),
        "completed_at": datetime.utcnow().isoformat()
    }
    
    # CORRECTED: Added await
    db.table("payments").insert(payment_record).execute()
    
    # Activate subscription immediately
    await activate_subscription(user_id, plan_id)
    
    return {
        "success": True,
        "message": f"🎉 {plan['name']} activated! Premium features unlocked!",
        "transaction_id": transaction_id,
        "plan": plan["name"],
        "features_unlocked": plan["features"],
        "demo_mode": True
    }

@router.get("/subscription/status")
async def get_subscription_status(user_id: str = Depends(verify_token)):
    """Get user's current subscription status"""
    db = await get_database()
    
    # CORRECTED: Added await
    subscription_result: PostgrestAPIResponse = db.table("subscriptions").select("*").eq("user_id", user_id).eq("active", True).execute()
    
    if subscription_result.data:
        subscription = subscription_result.data[0]
        expires_at = datetime.fromisoformat(subscription["expires_at"])
        days_remaining = (expires_at - datetime.utcnow()).days
        
        return {
            "active": True,
            "plan": subscription["plan_id"],
            "plan_name": SUBSCRIPTION_PLANS[subscription["plan_id"]]["name"],
            "expires_at": subscription["expires_at"],
            "days_remaining": max(0, days_remaining),
            "features": SUBSCRIPTION_PLANS[subscription["plan_id"]]["features"]
        }
    else:
        return {
            "active": False,
            "plan": "free",
            "message": "Upgrade to unlock premium features! 🚀"
        }

@router.get("/usage")
async def get_usage_stats(user_id: str = Depends(verify_token)):
    """Get user's monthly usage for freemium limits"""
    db = await get_database()
    
    # Check subscription with await
    subscription_status = await get_subscription_status(user_id)
    
    # Get this month's AI questions
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # CORRECTED: Added await
    ai_questions_result: PostgrestAPIResponse = db.table("flashcards").select("id").eq("user_id", user_id).eq("ai_generated", True).gte("created_at", month_start.isoformat()).execute()
    
    questions_used = len(ai_questions_result.data) if ai_questions_result.data else 0
    
    if subscription_status["active"]:
        return {
            "ai_questions_used": questions_used,
            "ai_questions_limit": "unlimited",
            "ai_questions_remaining": "unlimited",
            "subscription_active": True,
            "plan": subscription_status["plan"]
        }
    else:
        limit = 50
        remaining = max(0, limit - questions_used)
        
        return {
            "ai_questions_used": questions_used,
            "ai_questions_limit": limit,
            "ai_questions_remaining": remaining,
            "subscription_active": False,
            "upgrade_needed": remaining <= 5,
            "reset_date": (month_start + timedelta(days=32)).replace(day=1).isoformat()
        }

# Background task for simulating payment
async def simulate_payment_success(transaction_id: str, user_id: str, plan_id: str):
    """Simulate M-Pesa payment processing (3 second delay)"""
    await asyncio.sleep(3)  # Simulate processing time
    
    db = await get_database()
    
    # Update payment to completed
    # CORRECTED: Added await
    db.table("payments").update({
        "status": "completed",
        "completed_at": datetime.utcnow().isoformat()
    }).eq("id", transaction_id).execute()
    
    # Activate subscription
    await activate_subscription(user_id, plan_id)

async def activate_subscription(user_id: str, plan_id: str):
    """Activate user subscription"""
    db = await get_database()
    
    plan = SUBSCRIPTION_PLANS[plan_id]
    expires_at = datetime.utcnow() + timedelta(days=plan["duration_days"])
    
    # Deactivate existing subscriptions
    # CORRECTED: Added await
    db.table("subscriptions").update({"active": False}).eq("user_id", user_id).execute()
    
    # Create new subscription
    subscription_data = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "plan_id": plan_id,
        "active": True,
        "started_at": datetime.utcnow().isoformat(),
        "expires_at": expires_at.isoformat()
    }
    
    # CORRECTED: Added await
    db.table("subscriptions").insert(subscription_data).execute()