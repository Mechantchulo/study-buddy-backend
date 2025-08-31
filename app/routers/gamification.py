from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Dict
from datetime import datetime, timedelta
from supabase import PostgrestAPIResponse

from app.models.achievement import LeaderboardEntry, StudySession
from app.core.security import verify_token
from app.core.database import get_database
from app.services.gamification_service import GamificationService

router = APIRouter()
gamification_service = GamificationService()

@router.get("/profile")
async def get_user_game_profile(user_id: str = Depends(verify_token)):
    """Get complete gamification profile for user"""
    db = await get_database()
    
    # Get user stats with await
    user_result: PostgrestAPIResponse =  db.table("users").select("username, xp_points, level, current_streak, avatar_url").eq("id", user_id).execute()
    if not user_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    user = user_result.data[0]
    
    # Get user achievements with await
    achievements = await gamification_service.get_user_achievements(user_id)
    
    # Get recent study sessions with await
    sessions_result: PostgrestAPIResponse =  db.table("study_sessions").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(5).execute()
    
    # Calculate statistics
    sessions_data = sessions_result.data if sessions_result.data else []
    total_sessions = len(sessions_data)
    total_cards_studied = sum([session.get("cards_studied", 0) for session in sessions_data])
    
    # Avoid division by zero
    avg_accuracy = sum([session.get("accuracy_rate", 0) for session in sessions_data]) / max(total_sessions, 1)
    
    return {
        "user": user,
        "stats": {
            "total_sessions": total_sessions,
            "total_cards_studied": total_cards_studied,
            "average_accuracy": round(avg_accuracy, 2),
            "achievements_count": len(achievements)
        },
        "achievements": achievements,
        "recent_sessions": sessions_data
    }

@router.get("/leaderboard", response_model=List[LeaderboardEntry])
async def get_leaderboard(limit: int = 10):
    """Get global leaderboard"""
    # The gamification service handles the await internally
    leaderboard_data = await gamification_service.get_leaderboard(limit)
    
    return [
        LeaderboardEntry(
            user_id=entry["user_id"],
            username=entry["username"],
            xp_points=entry["xp_points"],
            level=entry["level"],
            rank=entry["rank"],
            avatar_url=entry.get("avatar_url")
        )
        for entry in leaderboard_data
    ]

@router.get("/achievements")
async def get_user_achievements(user_id: str = Depends(verify_token)):
    """Get all user achievements with progress tracking"""
    achievements = await gamification_service.get_user_achievements(user_id)
    
    # Get progress toward unearned badges
    db = await get_database()
    # Corrected: Added await to the user query
    user_result: PostgrestAPIResponse =  db.table("users").select("*").eq("id", user_id).execute()
    user = user_result.data[0] if user_result.data else {}
    
    earned_badges = [achievement["badge_type"] for achievement in achievements]
    
    # Calculate progress for unearned badges
    badge_progress = []
    
    # Corrected: Added await to the study sessions query
    sessions_result: PostgrestAPIResponse =  db.table("study_sessions").select("correct_answers").eq("user_id", user_id).execute()
    
    for badge_type, requirements in gamification_service.badge_requirements.items():
        if badge_type.value in earned_badges:
            continue
        
        progress = 0
        requirement = requirements["requirement"]
        
        if requirements["type"] == "streak":
            progress = user.get("current_streak", 0)
        elif requirements["type"] == "correct_answers":
            progress = sum([s.get("correct_answers", 0) for s in sessions_result.data])
        
        badge_progress.append({
            "badge_type": badge_type.value,
            "progress": min(progress, requirement),
            "requirement": requirement,
            "percentage": min((progress / requirement) * 100, 100) if requirement > 0 else 0
        })
    
    return {
        "earned_achievements": achievements,
        "progress_toward_badges": badge_progress
    }

@router.post("/session/start")
async def start_study_session(user_id: str = Depends(verify_token)):
    """Start a new study session"""
    # Corrected: Added await
    session_id = await gamification_service.start_study_session(user_id)
    
    return {
        "session_id": session_id,
        "start_time": datetime.utcnow().isoformat(),
        "message": "Study session started! Let's learn! 🚀"
    }

@router.post("/session/end")
async def end_study_session(
    session_data: Dict,
    user_id: str = Depends(verify_token)
):
    """End study session and calculate rewards"""
    # Corrected: Added await
    session_summary = await gamification_service.end_study_session(
        user_id=user_id,
        session_id=session_data["session_id"],
        cards_studied=session_data["cards_studied"],
        correct_answers=session_data["correct_answers"],
        session_duration=session_data["session_duration"]
    )
    
    return {
        "message": "Study session completed! 🎉",
        **session_summary
    }

@router.get("/stats/weekly")
async def get_weekly_stats(user_id: str = Depends(verify_token)):
    """Get user's weekly study statistics"""
    db = await get_database()
    
    # Get sessions from last 7 days with await
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    sessions_result: PostgrestAPIResponse = db.table("study_sessions").select("*").eq("user_id", user_id).gte("created_at", week_ago).execute()
    
    sessions_data = sessions_result.data if sessions_result.data else []
    
    # Calculate daily stats
    daily_stats = {}
    for session in sessions_data:
        date = datetime.fromisoformat(session["created_at"]).date().isoformat()
        if date not in daily_stats:
            daily_stats[date] = {
                "date": date,
                "sessions": 0,
                "cards_studied": 0,
                "xp_earned": 0,
                "accuracy": []
            }
        
        daily_stats[date]["sessions"] += 1
        daily_stats[date]["cards_studied"] += session.get("cards_studied", 0)
        daily_stats[date]["xp_earned"] += session.get("xp_earned", 0)
        daily_stats[date]["accuracy"].append(session.get("accuracy_rate", 0))
    
    # Calculate average accuracy for each day
    for date_stats in daily_stats.values():
        if date_stats["accuracy"]:
            date_stats["avg_accuracy"] = sum(date_stats["accuracy"]) / len(date_stats["accuracy"])
        else:
            date_stats["avg_accuracy"] = 0
        del date_stats["accuracy"]  # Remove raw accuracy list
    
    return {
        "weekly_stats": list(daily_stats.values()),
        "total_week_xp": sum([day["xp_earned"] for day in daily_stats.values()]),
        "total_week_cards": sum([day["cards_studied"] for day in daily_stats.values()])
    }

@router.post("/challenge/create")
async def create_challenge(
    challenge_data: Dict,
    user_id: str = Depends(verify_token)
):
    """Create a study challenge for friends"""
    return {
        "message": "Challenge feature coming soon! 🎯",
        "challenge_id": "placeholder",
        "status": "created"
    }