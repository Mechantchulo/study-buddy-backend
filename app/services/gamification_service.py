from typing import List, Dict, Optional
from datetime import datetime, timedelta
import uuid
from app.models.achievement import BadgeType, XPCalculation
from app.models.flashcard import DifficultyLevel
from app.core.database import get_database

class GamificationService:
    def __init__(self):
        self.level_thresholds = [0, 100, 250, 500, 1000, 2000, 4000, 8000, 15000, 30000]
        self.badge_requirements = {
            BadgeType.FIRST_STEPS: {"type": "first_answer", "requirement": 1},
            BadgeType.FIRE_SCHOLAR: {"type": "streak", "requirement": 7},
            BadgeType.KNOWLEDGE_WIZARD: {"type": "correct_answers", "requirement": 100},
            BadgeType.SPEED_DEMON: {"type": "speed_round", "requirement": 10},
            BadgeType.PERFECTIONIST: {"type": "perfect_accuracy", "requirement": 20},
            BadgeType.EARLY_BIRD: {"type": "early_study", "requirement": 5},
            BadgeType.NIGHT_OWL: {"type": "late_study", "requirement": 5},
            BadgeType.COMEBACK_KID: {"type": "return_after_break", "requirement": 7}
        }

    async def calculate_xp(
        self,
        correct: bool,
        difficulty: DifficultyLevel,
        time_taken: int,
        current_streak: int,
        accuracy_rate: float = 1.0
    ) -> XPCalculation:
        """Calculate XP earned for a question"""
        
        if not correct:
            return XPCalculation(
                base_xp=0,
                difficulty_multiplier=0,
                accuracy_bonus=0,
                speed_bonus=0,
                streak_bonus=0,
                total_xp=0
            )
        
        base_xp = 10
        
        # Difficulty multiplier
        difficulty_multipliers = {
            DifficultyLevel.EASY: 1.0,
            DifficultyLevel.MEDIUM: 1.5,
            DifficultyLevel.HARD: 2.0
        }
        difficulty_mult = difficulty_multipliers[difficulty]
        
        # Speed bonus (faster = more points, but cap at reasonable time)
        if time_taken < 5:  # Very fast
            speed_bonus = 1.5
        elif time_taken < 10:  # Fast
            speed_bonus = 1.2
        elif time_taken < 20:  # Normal
            speed_bonus = 1.0
        else:  # Slow
            speed_bonus = 0.8
        
        # Accuracy bonus
        accuracy_bonus = min(accuracy_rate * 1.2, 1.5)
        
        # Streak bonus
        streak_bonus = min(1 + (current_streak * 0.1), 2.0)
        
        total_xp = int(base_xp * difficulty_mult * speed_bonus * accuracy_bonus * streak_bonus)
        
        return XPCalculation(
            base_xp=base_xp,
            difficulty_multiplier=difficulty_mult,
            accuracy_bonus=accuracy_bonus,
            speed_bonus=speed_bonus,
            streak_bonus=streak_bonus,
            total_xp=total_xp
        )

    async def update_user_progress(self, user_id: str, xp_earned: int, correct: bool) -> Dict:
        """Update user's XP, level, and streak"""
        db = await get_database()
        
        # Get current user stats
        user_result = db.table("users").select("*").eq("id", user_id).execute()
        if not user_result.data:
            raise ValueError("User not found")
        
        user = user_result.data[0]
        current_xp = user.get("xp_points", 0)
        current_level = user.get("level", 1)
        current_streak = user.get("current_streak", 0)
        last_study = user.get("last_study_date")
        
        # Update XP
        new_xp = current_xp + xp_earned
        
        # Calculate new level
        new_level = self._calculate_level(new_xp)
        level_up = new_level > current_level
        
        # Update streak
        today = datetime.now().date()
        if last_study:
            last_study_date = datetime.fromisoformat(last_study).date()
            if today == last_study_date:
                # Same day, keep streak
                new_streak = current_streak
            elif today == last_study_date + timedelta(days=1):
                # Next day, increment streak
                new_streak = current_streak + 1 if correct else 0
            else:
                # Broke streak
                new_streak = 1 if correct else 0
        else:
            # First study session
            new_streak = 1 if correct else 0
        
        # Update user in database
        update_data = {
            "xp_points": new_xp,
            "level": new_level,
            "current_streak": new_streak,
            "last_study_date": today.isoformat()
        }
        
        db.table("users").update(update_data).eq("id", user_id).execute()
        
        return {
            "xp_earned": xp_earned,
            "total_xp": new_xp,
            "level": new_level,
            "level_up": level_up,
            "streak": new_streak,
            "streak_broken": new_streak < current_streak
        }

    async def check_badge_eligibility(self, user_id: str) -> List[BadgeType]:
        """Check if user earned any new badges"""
        db = await get_database()
        new_badges = []
        
        # Get user stats
        user_result = db.table("users").select("*").eq("id", user_id).execute()
        user = user_result.data[0] if user_result.data else None
        
        if not user:
            return new_badges
        
        # Get existing badges
        existing_badges_result = db.table("achievements").select("badge_type").eq("user_id", user_id).execute()
        existing_badges = [badge["badge_type"] for badge in existing_badges_result.data]
        
        # Check each badge requirement
        for badge_type, requirements in self.badge_requirements.items():
            if badge_type.value in existing_badges:
                continue  # User already has this badge
            
            earned = False
            
            if requirements["type"] == "first_answer":
                # Check if user has answered any question
                answers_result = db.table("study_sessions").select("id").eq("user_id", user_id).execute()
                earned = len(answers_result.data) >= requirements["requirement"]
            
            elif requirements["type"] == "streak":
                earned = user.get("current_streak", 0) >= requirements["requirement"]
            
            elif requirements["type"] == "correct_answers":
                # Count total correct answers from study sessions
                sessions_result = db.table("study_sessions").select("correct_answers").eq("user_id", user_id).execute()
                total_correct = sum([session.get("correct_answers", 0) for session in sessions_result.data])
                earned = total_correct >= requirements["requirement"]
            
            elif requirements["type"] == "speed_round":
                # Check for recent speed achievements (10 questions in under 60 seconds)
                recent_sessions = db.table("study_sessions").select("*").eq("user_id", user_id).gte("created_at", (datetime.now() - timedelta(days=7)).isoformat()).execute()
                
                for session in recent_sessions.data:
                    if (session.get("cards_studied", 0) >= 10 and 
                        session.get("session_duration", 999) <= 60):
                        earned = True
                        break
            
            elif requirements["type"] == "perfect_accuracy":
                # Check for 100% accuracy on 20+ questions in a session
                sessions_result = db.table("study_sessions").select("*").eq("user_id", user_id).execute()
                
                for session in sessions_result.data:
                    if (session.get("cards_studied", 0) >= 20 and 
                        session.get("accuracy_rate", 0) == 1.0):
                        earned = True
                        break
            
            elif requirements["type"] == "early_study":
                # Check for studying before 8 AM (need to track study times)
                early_sessions = db.table("study_sessions").select("created_at").eq("user_id", user_id).execute()
                early_count = 0
                
                for session in early_sessions.data:
                    study_time = datetime.fromisoformat(session["created_at"]).time()
                    if study_time.hour < 8:
                        early_count += 1
                
                earned = early_count >= requirements["requirement"]
            
            elif requirements["type"] == "late_study":
                # Check for studying after 10 PM
                late_sessions = db.table("study_sessions").select("created_at").eq("user_id", user_id).execute()
                late_count = 0
                
                for session in late_sessions.data:
                    study_time = datetime.fromisoformat(session["created_at"]).time()
                    if study_time.hour >= 22:
                        late_count += 1
                
                earned = late_count >= requirements["requirement"]
            
            elif requirements["type"] == "return_after_break":
                # Check if user returned after 7+ day break
                sessions_result = db.table("study_sessions").select("created_at").eq("user_id", user_id).order("created_at", desc=True).limit(2).execute()
                
                if len(sessions_result.data) >= 2:
                    latest = datetime.fromisoformat(sessions_result.data[0]["created_at"])
                    previous = datetime.fromisoformat(sessions_result.data[1]["created_at"])
                    break_duration = (latest - previous).days
                    earned = break_duration >= requirements["requirement"]
            
            if earned:
                # Award the badge
                await self._award_badge(user_id, badge_type)
                new_badges.append(badge_type)
        
        return new_badges

    async def _award_badge(self, user_id: str, badge_type: BadgeType):
        """Award a badge to user"""
        db = await get_database()
        
        badge_descriptions = {
            BadgeType.FIRST_STEPS: "Answered your first question! Welcome to the journey! 🚀",
            BadgeType.FIRE_SCHOLAR: "7-day study streak! You're on fire! 🔥",
            BadgeType.KNOWLEDGE_WIZARD: "100 correct answers! True wisdom achieved! 🧙‍♂️",
            BadgeType.SPEED_DEMON: "10 questions in 60 seconds! Lightning fast! ⚡",
            BadgeType.PERFECTIONIST: "Perfect accuracy on 20+ questions! Flawless! 🎯",
            BadgeType.EARLY_BIRD: "5 early morning study sessions! Rise and grind! 🌅",
            BadgeType.NIGHT_OWL: "5 late night study sessions! Burning the midnight oil! 🦉",
            BadgeType.COMEBACK_KID: "Returned after a week break! Welcome back, champion! 🏆"
        }
        
        achievement_data = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "badge_type": badge_type.value,
            "earned_at": datetime.utcnow().isoformat(),
            "description": badge_descriptions.get(badge_type, "Achievement unlocked!")
        }
        
        db.table("achievements").insert(achievement_data).execute()

    def _calculate_level(self, xp_points: int) -> int:
        """Calculate user level based on XP"""
        for level, threshold in enumerate(self.level_thresholds):
            if xp_points < threshold:
                return max(1, level)
        return len(self.level_thresholds)  # Max level

    async def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Get top users for leaderboard"""
        db = await get_database()
        
        result = db.table("users").select(
            "id, username, xp_points, level, avatar_url"
        ).order("xp_points", desc=True).limit(limit).execute()
        
        leaderboard = []
        for rank, user in enumerate(result.data, 1):
            leaderboard.append({
                "rank": rank,
                "user_id": user["id"],
                "username": user["username"],
                "xp_points": user["xp_points"],
                "level": user["level"],
                "avatar_url": user.get("avatar_url")
            })
        
        return leaderboard

    async def get_user_achievements(self, user_id: str) -> List[Dict]:
        """Get all achievements for a user"""
        db = await get_database()
        
        result = db.table("achievements").select("*").eq("user_id", user_id).order("earned_at", desc=True).execute()
        
        return result.data

    async def start_study_session(self, user_id: str) -> str:
        """Start a new study session and return session ID"""
        session_id = str(uuid.uuid4())
        
        # Store session start time in memory or cache
        # For hackathon, we'll track this in the session response
        
        return session_id

    async def end_study_session(
        self, 
        user_id: str, 
        session_id: str,
        cards_studied: int,
        correct_answers: int,
        session_duration: int
    ) -> Dict:
        """End study session and calculate final rewards"""
        db = await get_database()
        
        accuracy_rate = correct_answers / cards_studied if cards_studied > 0 else 0
        xp_earned = correct_answers * 10  # Base calculation
        
        # Save study session
        session_data = {
            "id": session_id,
            "user_id": user_id,
            "cards_studied": cards_studied,
            "correct_answers": correct_answers,
            "accuracy_rate": accuracy_rate,
            "session_duration": session_duration,
            "xp_earned": xp_earned,
            "created_at": datetime.utcnow().isoformat()
        }
        
        db.table("study_sessions").insert(session_data).execute()
        
        # Check for new badges
        new_badges = await self.check_badge_eligibility(user_id)
        
        return {
            "session_summary": {
                "cards_studied": cards_studied,
                "accuracy_rate": accuracy_rate,
                "xp_earned": xp_earned,
                "duration": session_duration
            },
            "new_badges": [badge.value for badge in new_badges],
            "performance_message": self._get_performance_message(accuracy_rate, cards_studied)
        }

    def _get_performance_message(self, accuracy_rate: float, cards_studied: int) -> str:
        """Generate encouraging performance message"""
        if accuracy_rate >= 0.9 and cards_studied >= 10:
            return "🔥 INCREDIBLE! You're a study machine! Keep this momentum going!"
        elif accuracy_rate >= 0.8:
            return "🌟 Excellent work! You're really mastering this material!"
        elif accuracy_rate >= 0.7:
            return "👍 Good job! You're making solid progress!"
        elif accuracy_rate >= 0.5:
            return "📚 Keep practicing! Every question brings you closer to mastery!"
        else:
            return "💪 Don't give up! Learning takes time - you've got this!"