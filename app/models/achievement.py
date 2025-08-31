from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum

class BadgeType(str, Enum):
    FIRE_SCHOLAR = "fire_scholar"        # 7-day streak
    KNOWLEDGE_WIZARD = "knowledge_wizard"  # 100 correct answers
    SPEED_DEMON = "speed_demon"          # 10 questions in 60 seconds
    PERFECTIONIST = "perfectionist"      # 100% accuracy on 20+ questions
    FIRST_STEPS = "first_steps"          # First question answered
    EARLY_BIRD = "early_bird"            # Study before 8 AM
    NIGHT_OWL = "night_owl"              # Study after 10 PM
    COMEBACK_KID = "comeback_kid"        # Return after 7+ day break

class Achievement(BaseModel):
    id: str
    user_id: str
    badge_type: BadgeType
    earned_at: datetime
    description: str

class LeaderboardEntry(BaseModel):
    user_id: str
    username: str
    xp_points: int
    level: int
    rank: int
    avatar_url: Optional[str] = None

class StudySession(BaseModel):
    id: str
    user_id: str
    cards_studied: int
    correct_answers: int
    accuracy_rate: float
    session_duration: int  # seconds
    xp_earned: int
    created_at: datetime

class XPCalculation(BaseModel):
    base_xp: int = 10
    difficulty_multiplier: float
    accuracy_bonus: float
    speed_bonus: float
    streak_bonus: float
    total_xp: int