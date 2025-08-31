import httpx
from fastapi import APIRouter, HTTPException, Depends, status
from datetime import datetime
import uuid

from app.models.user import UserCreate, UserLogin, UserResponse, Token, UserUpdate
from app.core.security import (
    verify_password, get_password_hash, create_access_token, verify_token
)
from app.core.database import get_database

router = APIRouter()

@router.post("/register", response_model=Token)
async def register_user(user_data: UserCreate):
    """Register a new user and return access token"""
    db = await get_database()
    
    # CORRECTED: Removed 'await' 
    existing_user_by_email =  db.table("users").select("id").eq("email", user_data.email).execute()
    if existing_user_by_email.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered. Try logging in instead"
        )
        
    # CORRECTED: Removed 'await'
    existing_user_by_username =  db.table("users").select("id").eq("username", user_data.username).execute()
    if existing_user_by_username.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username taken! Pick another username"
        )
        
    # Create a new user
    user_id = str(uuid.uuid4())
    hashed_password = get_password_hash(user_data.password)
    
    new_user = {
        "id": user_id,
        "email": user_data.email,
        "username": user_data.username,
        "password_hash": hashed_password,
        "xp_points": 0,
        "level": 1,
        "current_streak": 0,
        "ai_personality": user_data.ai_personality,
        "created_at": datetime.utcnow().isoformat(),
        "last_study_date": None
    }
    
    # CORRECTED: Removed'await'
    result =  db.table("users").insert(new_user).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user account"
        )
        
    # Create access token
    access_token = create_access_token(data={"sub": user_id})
    
    # Return user data without password
    user_response = UserResponse(**{k: v for k, v in new_user.items() if k != "password"})
    
    return Token(access_token=access_token, user=user_response)

@router.post("/login", response_model=Token)
async def login_user(login_data: UserLogin):
    """Login user and return access token"""
    
    db = await get_database()
    
    # CORRECTED: Removed 'await'
    user_result =  db.table("users").select("*").eq("email", login_data.email).execute()
    if not user_result.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
        
    user = user_result.data[0]
    
    if not verify_password(login_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
        
    # Create access token
    access_token = create_access_token(data={"sub": user["id"]})
    
    # Return user data without password
    user_response = UserResponse(**{k: v for k, v in user.items() if k != "password_hash"})
    return Token(access_token=access_token, user=user_response)

@router.get("/me", response_model=UserResponse)
async def get_current_user(user_id: str = Depends(verify_token)):
    """Get current user profile"""
    db = await get_database()
    
    # CORRECTED: Re-added 'await'
    user_result =  db.table("users").select("*").eq("id", user_id).execute()
    if not user_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user = user_result.data[0]
    return UserResponse(**{k: v for k, v in user.items() if k != "password_hash"})

@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    user_id: str = Depends(verify_token)
):
    """Update current user profile"""
    db = await get_database()
    
    # CORRECTED: Removed 'await'
    user_result =  db.table("users").select("*").eq("id", user_id).execute()
    if not user_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Prepare update data (only non-None fields)
    update_data = user_update.model_dump(exclude_unset=True)
    
    if not update_data:
        user = user_result.data[0]
        return UserResponse(**{k: v for k, v in user.items() if k != "password_hash"})
    
    # CORRECTED: Removed'await'
    if "username" in update_data:
        existing_username = db.table("users").select("*").eq("username", update_data["username"]).neq("id", user_id).execute()
        if existing_username.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken!"
            )
    
    # CORRECTED: Removed 'await'
    updated_result =  db.table("users").update(update_data).eq("id", user_id).execute()
    if not updated_result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )
    
    updated_user = updated_result.data[0]
    return UserResponse(**{k: v for k, v in updated_user.items() if k != "password_hash"})