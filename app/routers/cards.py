from fastapi import APIRouter, HTTPException, Depends, Query, status
from typing import Optional, List, Dict
import uuid
import json
from datetime import datetime, timedelta
from supabase import PostgrestAPIResponse

from app.models.flashcard import (
    FlashcardCreate, FlashcardResponse, AnswerSubmission,
    StudySessionResult, DifficultyLevel, QuestionType
)

from app.core.security import verify_token
from app.core.database import get_database
from app.services.gamification_service import GamificationService

router = APIRouter()
gamification_service = GamificationService()


@router.post("/create", response_model=FlashcardResponse)
async def create_flashcard(
    flashcard_data: FlashcardCreate,
    user_id: str = Depends(verify_token)
):
    """Create a manual flashcard"""
    db = await get_database()
    
    flashcard_id = str(uuid.uuid4())
    
    new_flashcard = {
        "id": flashcard_id,
        "user_id": user_id,
        "question": flashcard_data.question,
        "answer": flashcard_data.answer,
        "question_type": flashcard_data.question_type.value,
        "difficulty_level": flashcard_data.difficulty_level.value,
        "deck_name": flashcard_data.deck_name or "Default",
        # Pass options directly, Supabase client handles JSON serialization
        "options": flashcard_data.options,
        "ai_generated": False,
        "performance_score": 0.0,
        "times_reviewed": 0,
        "created_at": datetime.utcnow().isoformat()
    }
    
    result: PostgrestAPIResponse =  db.table("flashcards").insert(new_flashcard).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create flashcard"
        )
        
    response_data = result.data[0]
    
    # Pydantic model handles data from DB, including list conversion for options
    response = FlashcardResponse(**response_data)
        
    return response


@router.get("/my-cards", response_model=List[FlashcardResponse])
async def get_user_flashcards(
    user_id: str = Depends(verify_token),
    deck_name: Optional[str] = Query(None),
    difficulty: Optional[DifficultyLevel] = Query(None),
    limit: int = Query(50, le=100)
):
    """Get user's flashcards with optional filtering"""
    db = await get_database()
    
    query = db.table("flashcards").select("*").eq("user_id", user_id)
    
    if deck_name:
        query = query.eq("deck_name", deck_name)
    if difficulty:
        query = query.eq("difficulty_level", difficulty.value)
        
    result: PostgrestAPIResponse = await query.limit(limit).order("created_at", desc=True).execute()
    
    flashcards = []
    if result.data:
        for card_data in result.data:
            # Pydantic model handles the data and type casting
            card = FlashcardResponse(**card_data)
            flashcards.append(card)
        
    return flashcards


@router.get("/study-session", response_model=Dict)
async def get_study_session(
    user_id: str = Depends(verify_token),
    deck_name: Optional[str] = Query(None),
    count: int = Query(10, le=50)
):
    """Get flashcards for study session (optimized for spaced repetition)"""
    
    db = await get_database()
    
    now = datetime.utcnow().isoformat()
    
    query = db.table("flashcards").select("*").eq("user_id", user_id)
    
    if deck_name:
        query = query.eq("deck_name", deck_name)
        
    # Get cards that need review first
    due_cards: PostgrestAPIResponse = await query.lte("next_review", now).limit(count).execute()
        
    cards_needed = count - len(due_cards.data) if due_cards.data else count
    all_cards = []
    
    if due_cards.data:
        all_cards.extend(due_cards.data)
    
    # Fill remaining with new/random cards if needed
    if cards_needed > 0:
        remaining_query = db.table("flashcards").select("*").eq("user_id", user_id)
        if deck_name:
            remaining_query = remaining_query.eq("deck_name", deck_name)
        
        remaining_cards: PostgrestAPIResponse = await remaining_query.is_("next_review", "null").limit(cards_needed).execute()
        if remaining_cards.data:
            all_cards.extend(remaining_cards.data)
    
    # Convert to response format
    flashcards = [FlashcardResponse(**card_data) for card_data in all_cards]
    
    return {
        "flashcards": flashcards,
        "session_id": str(uuid.uuid4()),
        "total_cards": len(flashcards)
    }


@router.post("/answer", response_model=StudySessionResult)
async def submit_answer(
    answer_data: AnswerSubmission,
    user_id: str = Depends(verify_token)
):
    """Submit answer and get immediate feedback with XP calculation"""
    db = await get_database()
    
    # Get flashcard
    card_result: PostgrestAPIResponse =  db.table("flashcards").select("*").eq("id", answer_data.flashcard_id).eq("user_id", user_id).execute()
    if not card_result.data:
        raise HTTPException(
            status_code=404,
            detail="Flashcard not found! 🃏❌"
        )
    
    card = card_result.data[0]
    
    # Check if answer is correct
    correct_answer = card["answer"].lower().strip()
    user_answer = answer_data.user_answer.lower().strip()
    
    is_correct = False
    
    if card.get("question_type") == QuestionType.MULTIPLE_CHOICE.value:
        if card.get("options"):
            options = card["options"]
            # Check if the user's answer is one of the valid options and matches the correct answer
            is_correct = user_answer == correct_answer
    else:
        is_correct = user_answer == correct_answer or user_answer in correct_answer
    
    # Get user current stats for XP calculation
    user_result: PostgrestAPIResponse =  db.table("users").select("current_streak, xp_points").eq("id", user_id).execute()
    current_streak = user_result.data[0].get("current_streak", 0) if user_result.data else 0
    
    # Calculate XP
    xp_calc = await gamification_service.calculate_xp(
        correct=is_correct,
        difficulty=DifficultyLevel(card["difficulty_level"]),
        time_taken=answer_data.time_taken,
        current_streak=current_streak
    )
    
    # Update flashcard performance
    new_performance = card.get("performance_score", 0.0)
    times_reviewed = card.get("times_reviewed", 0) + 1
    
    if is_correct:
        new_performance = min(new_performance + 0.1, 1.0)
    else:
        new_performance = max(new_performance - 0.1, 0.0)
    
    # Calculate next review date (spaced repetition)
    next_review = calculate_next_review_date(new_performance, times_reviewed)
    
    # Update flashcard
    update_card_data = {
        "performance_score": new_performance,
        "times_reviewed": times_reviewed,
        "last_reviewed": datetime.utcnow().isoformat(),
        "next_review": next_review.isoformat()
    }
    
    await db.table("flashcards").update(update_card_data).eq("id", answer_data.flashcard_id).execute()
    
    # Update user progress
    progress_update = await gamification_service.update_user_progress(
        user_id=user_id,
        xp_earned=xp_calc.total_xp,
        correct=is_correct
    )
    
    return StudySessionResult(
        correct=is_correct,
        xp_earned=xp_calc.total_xp,
        explanation=f"The correct answer is: {card['answer']}" if not is_correct else "Perfect! 🎯"
    )


@router.get("/decks", response_model=Dict)
async def get_user_decks(user_id: str = Depends(verify_token)):
    """Get all deck names for the user"""
    db = await get_database()
    
    # Optimized query: get all decks and their counts in a single pass
    result: PostgrestAPIResponse = db.table("flashcards").select("deck_name").eq("user_id", user_id).execute()
    
    deck_counts = {}
    if result.data:
        for card in result.data:
            deck_name = card["deck_name"]
            deck_counts[deck_name] = deck_counts.get(deck_name, 0) + 1
            
    decks = []
    for deck_name, count in deck_counts.items():
        decks.append({
            "name": deck_name,
            "card_count": count,
            "created_at": datetime.utcnow().isoformat()
        })
    
    return {"decks": decks}


@router.delete("/{flashcard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flashcard(
    flashcard_id: str,
    user_id: str = Depends(verify_token)
):
    """Delete a flashcard"""
    db = await get_database()
    
    # Verify ownership
    card_result: PostgrestAPIResponse =  db.table("flashcards").select("id").eq("id", flashcard_id).eq("user_id", user_id).execute()
    if not card_result.data:
        raise HTTPException(
            status_code=404,
            detail="Flashcard not found! 🃏❌"
        )
    
    # Delete the card
    await db.table("flashcards").delete().eq("id", flashcard_id).execute()
    
    return {"message": "Flashcard deleted successfully! 🗑️✅"}


def calculate_next_review_date(performance_score: float, times_reviewed: int) -> datetime:
    """Calculate next review date using spaced repetition algorithm"""
    base_interval = 1  # days
    
    # Performance factor (better performance = longer intervals)
    performance_factor = 1 + (performance_score * 2)
    
    # Review factor (more reviews = longer intervals)
    review_factor = 1 + (times_reviewed * 0.5)
    
    # Calculate interval
    interval_days = base_interval * performance_factor * review_factor
    interval_days = min(interval_days, 30)  # Cap at 30 days
    
    return datetime.utcnow() + timedelta(days=interval_days)