from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    ai_personality: Optional[str] = "encouraging"
    

class UserLogin(BaseModel):
    email: EmailStr
    password: str
    

class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    xp_points: int = 0
    level: int = 1
    current_streak: int = 0
    ai_personality: str
    avatar_url: Optional[str] = None
    created_at: datetime
    

class UserUpdate(BaseModel):
    username: Optional[str] = None
    ai_personality: Optional[str] = None
    avatar_url: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    