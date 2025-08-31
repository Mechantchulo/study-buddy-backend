from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, status
from typing import List, Optional
import json
import uuid
from datetime import datetime
from supabase import PostgrestAPIResponse

from app.models.flashcard import StudyNotesInput, FlashcardResponse, FlashcardCreate, DifficultyLevel
from app.services.ai_services import AIService
from app.core.security import verify_token
from app.core.database import get_database

router = APIRouter()
ai_service = AIService()

# Background task function
async def check_ai_generation_achievements(user_id: str, questions_generated: int):
    """Check if user earned achievements for AI question generation"""
    from app.services.gamification_service import GamificationService
    
    gamification = GamificationService()
    await gamification.check_badge_eligibility(user_id)

@router.post("/generate-questions", response_model=List[FlashcardResponse])
async def generate_questions_from_notes(
    notes_input: StudyNotesInput,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verify_token)
):
    """Generate AI-powered questions from study notes"""
    
    try:
        db = await get_database()
        
        # Get user's AI personality preference with proper error handling
        user_result: PostgrestAPIResponse =  db.table("users").select("ai_personality").eq("id", user_id).execute()
        
        personality = "encouraging"
        if user_result.data:
            personality = user_result.data[0].get("ai_personality", "encouraging")
        
        # Generate questions using AI
        questions = await ai_service.generate_questions_from_text(
            content=notes_input.content,
            num_questions=notes_input.num_questions,
            difficulty=notes_input.difficulty_preference,
            personality=personality
        )
        
        if not questions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Couldn't generate questions from this content. Try adding more detailed notes! 📝"
            )
        
        # Prepare and save generated flashcards to database
        flashcards = []
        for q in questions:
            # Pydantic model ensures data is correct before insertion
            flashcard_data = FlashcardCreate(
                user_id=user_id,
                question=q["question"],
                answer=q["answer"],
                question_type=q["question_type"], # Pydantic will handle enum conversion
                difficulty_level=q["difficulty_level"], # Pydantic will handle enum conversion
                deck_name=notes_input.subject,
                options=q.get("options", []), # The model handles serialization of lists
                ai_generated=True
            )
            
            # Insert into database
            insert_result: PostgrestAPIResponse =  db.table("flashcards").insert(flashcard_data.model_dump()).execute()
            
            if insert_result.data:
                # Retrieve the newly created flashcard from the response and use it to create a Pydantic model
                # This ensures the `options` field is a proper list
                created_card = insert_result.data[0]
                flashcard_response = FlashcardResponse(**created_card)
                flashcards.append(flashcard_response)
        
        # Background task: Check for achievements
        background_tasks.add_task(check_ai_generation_achievements, user_id, len(flashcards))
        
        return flashcards
        
    except Exception as e:
        print(f"Error in generate_questions_from_notes: {e}") # Debugging print
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI generation failed: {str(e)} "
        )

@router.post("/regenerate-question/{flashcard_id}")
async def regenerate_single_question(
    flashcard_id: str,
    user_id: str = Depends(verify_token)
):
    """Regenerate a single question with different AI approach"""
    
    db = await get_database()
    
    # Get existing flashcard
    card_result: PostgrestAPIResponse =  db.table("flashcards").select("*").eq("id", flashcard_id).eq("user_id", user_id).execute()
    
    if not card_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flashcard not found! "
        )
    
    card = card_result.data[0]
    
    # Get user personality
    user_result: PostgrestAPIResponse =  db.table("users").select("ai_personality").eq("id", user_id).execute()
    personality = user_result.data[0].get("ai_personality", "encouraging") if user_result.data else "encouraging"
    
    # Generate new question from same source content
    try:
        new_questions = await ai_service.generate_questions_from_text(
            content=f"Key concept: {card['answer']}. Context: {card['question']}",
            num_questions=1,
            difficulty=DifficultyLevel(card["difficulty_level"]),
            personality=personality
        )
        
        if new_questions:
            new_q = new_questions[0]
            
            # Update the flashcard
            update_data = {
                "question": new_q["question"],
                "answer": new_q["answer"],
                "options": new_q.get("options", []),
                "question_type": new_q["question_type"].value
            }
            
            updated_result: PostgrestAPIResponse =  db.table("flashcards").update(update_data).eq("id", flashcard_id).execute()
            
            if updated_result.data:
                updated_card = updated_result.data[0]
                response = FlashcardResponse(**updated_card)
                return response
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to regenerate question "
        )
        
    except Exception as e:
        print(f"Error in regenerate_single_question: {e}") # Debugging print
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Regeneration failed: {str(e)}"
        )