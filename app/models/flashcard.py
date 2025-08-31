from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum

class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    FILL_BLANK = "fill_blank"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    
class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    
class FlashcardCreate(BaseModel):
    question: str
    answer: str
    question_type: QuestionType
    difficulty_level: DifficultyLevel
    deck_name: Optional[str] = "Default"
    options: Optional[List[str]] = "None" #for multiple choices
    
    
class FlashcardResponse(BaseModel):
    id: str
    user_id: str
    question: str
    answer: str
    question_type: QuestionType
    difficulty_level: DifficultyLevel
    deck_name: str
    options: Optional[List[str]] = None
    ai_generated: bool
    performance_score: float = 0.0
    times_reviewed: int = 0
    last_reviewed: Optional[datetime] = None
    next_review: Optional[datetime] = None
    created_at: datetime
    
class StudyNotesInput(BaseModel):
    content: str
    subject: Optional[str] = "General"
    num_questions: int = 5
    difficulty_preference: DifficultyLevel = DifficultyLevel.MEDIUM
    
class AnswerSubmission(BaseModel):
    flashcard_id: str
    user_answer: str
    time_taken: int # seconds
    
class StudySessionResult(BaseModel):
    correct: bool
    xp_earned: str
    explanation: Optional[str] = None    