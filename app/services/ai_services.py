import requests
import json
import random
from typing import List, Dict
from app.core.config import settings
from app.models.flashcard import QuestionType, DifficultyLevel

class AIService:
    def __init__(self):
        self.hf_api_url = "https://api-inference.huggingface.co/models"
        self.headers = {"Authorization": f"Bearer {settings.huggingface_api_key}"}
        
        # AI Personalities
        self.personalities = {
            "encouraging": {
                "question_prefix": "Great job learning! ",
                "hint_style": "Think about what we just covered: ",
                "celebration": "Amazing work! 🎉"
            },
            "socratic": {
                "question_prefix": "Consider this carefully: ",
                "hint_style": "What do you think would happen if... ",
                "celebration": "Excellent reasoning! 🧠"
            },
            "challenger": {
                "question_prefix": "Here's a tough one: ",
                "hint_style": "Push yourself harder - ",
                "celebration": "Conquered! 💪"
            }
        }
        
    async def generate_questions_from_text(
        self,
        content: str,
        num_questions: int = 5,
        difficulty: DifficultyLevel = DifficultyLevel.MEDIUM,
        personality: str = "encouraging"
    ) -> List[Dict]:
        """Generate questions from study notes using AI"""
        
        # Split content into chunks for better processing
        chunks = self._split_content(content)
        questions = []
        
        for chunk in chunks[:num_questions]:
            question_types = list(QuestionType)
            question_type = random.choice(question_types)
            
            if question_type == QuestionType.MULTIPLE_CHOICE:
                question = await self._generate_mcq(chunk, difficulty, personality)
            elif question_type == QuestionType.FILL_BLANK:
                question = await self._generate_fill_blank(chunk, difficulty, personality)
            elif question_type == QuestionType.TRUE_FALSE:
                question = await self._generate_true_false(chunk, difficulty, personality)
            else:
                question = await self._generate_short_answer(chunk, difficulty, personality)
            
            if question:
                questions.append(question)
        
        return questions[:num_questions]

    async def _generate_mcq(self, content: str, difficulty: DifficultyLevel, personality: str) -> Dict:
        """Generate multiple choice question"""
        prompt = f"""
        Based on this content: "{content}"
        
        Generate a {difficulty.value} difficulty multiple choice question with 4 options.
        Personality: {personality}
        
        Format as JSON:
        {{
            "question": "Question here",
            "correct_answer": "Correct answer",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "explanation": "Brief explanation"
        }}
        """
        
        try:
            response = await self._call_huggingface_api(prompt)
            # Parse and structure the response
            return {
                "question": self._add_personality_touch(response.get("question", ""), personality),
                "answer": response.get("correct_answer", ""),
                "question_type": QuestionType.MULTIPLE_CHOICE,
                "difficulty_level": difficulty,
                "options": response.get("options", []),
                "explanation": response.get("explanation", "")
            }
        except Exception as e:
            # Fallback to template-based generation
            return self._generate_fallback_mcq(content, difficulty, personality)

    async def _generate_fill_blank(self, content: str, difficulty: DifficultyLevel, personality: str) -> Dict:
        """Generate fill-in-the-blank question"""
        # Extract key terms from content
        sentences = content.split('.')
        if not sentences:
            return None
            
        sentence = random.choice([s for s in sentences if len(s.strip()) > 20])
        words = sentence.split()
        
        # Remove important words based on difficulty
        if difficulty == DifficultyLevel.EASY:
            blank_count = 1
        elif difficulty == DifficultyLevel.MEDIUM:
            blank_count = min(2, len(words) // 8)
        else:
            blank_count = min(3, len(words) // 6)
        
        # Create blanks
        important_words = [w for w in words if len(w) > 4 and w.isalpha()]
        if len(important_words) < blank_count:
            return None
            
        blank_words = random.sample(important_words, blank_count)
        question_text = sentence
        answer_text = ", ".join(blank_words)
        
        for word in blank_words:
            question_text = question_text.replace(word, "___", 1)
        
        return {
            "question": self._add_personality_touch(question_text, personality),
            "answer": answer_text,
            "question_type": QuestionType.FILL_BLANK,
            "difficulty_level": difficulty,
            "options": None
        }

    async def _generate_true_false(self, content: str, difficulty: DifficultyLevel, personality: str) -> Dict:
        """Generate true/false question"""
        sentences = [s.strip() for s in content.split('.') if len(s.strip()) > 15]
        if not sentences:
            return None
            
        base_sentence = random.choice(sentences)
        
        # 50% chance of making it false by modifying
        is_true = random.choice([True, False])
        
        if not is_true:
            # Make statement false by changing key words
            words = base_sentence.split()
            if "not" in base_sentence.lower():
                base_sentence = base_sentence.replace("not", "").replace("  ", " ")
            else:
                # Add negation or change numbers/adjectives
                base_sentence = f"It is not true that {base_sentence.lower()}"
        
        return {
            "question": self._add_personality_touch(f"True or False: {base_sentence}", personality),
            "answer": str(is_true),
            "question_type": QuestionType.TRUE_FALSE,
            "difficulty_level": difficulty,
            "options": ["True", "False"]
        }

    async def _generate_short_answer(self, content: str, difficulty: DifficultyLevel, personality: str) -> Dict:
        """Generate short answer question"""
        # Extract key concepts and create questions
        sentences = [s.strip() for s in content.split('.') if len(s.strip()) > 20]
        if not sentences:
            return None
            
        sentence = random.choice(sentences)
        
        # Create question by asking "what", "why", "how"
        question_starters = ["What is", "Why does", "How does", "What causes", "What happens when"]
        starter = random.choice(question_starters)
        
        question = f"{starter} the main concept in: '{sentence[:50]}...'?"
        
        return {
            "question": self._add_personality_touch(question, personality),
            "answer": sentence,
            "question_type": QuestionType.SHORT_ANSWER,
            "difficulty_level": difficulty,
            "options": None
        }

    def _add_personality_touch(self, question: str, personality: str) -> str:
        """Add personality-specific language to questions"""
        if personality in self.personalities:
            prefix = self.personalities[personality]["question_prefix"]
            return f"{prefix}{question}"
        return question

    def _split_content(self, content: str, max_chunk_size: int = 200) -> List[str]:
        """Split content into manageable chunks"""
        sentences = content.split('.')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk + sentence) < max_chunk_size:
                current_chunk += sentence + "."
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + "."
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks

    async def _call_huggingface_api(self, prompt: str) -> Dict:
        """Call Hugging Face API - implement based on your needs"""
        # This is a placeholder - you can integrate with specific HF models
        # For now, we'll rely on the fallback methods
        raise NotImplementedError("Implement HF API call")

    def _generate_fallback_mcq(self, content: str, difficulty: DifficultyLevel, personality: str) -> Dict:
        """Fallback MCQ generation when AI fails"""
        sentences = [s.strip() for s in content.split('.') if len(s.strip()) > 15]
        if not sentences:
            return None
            
        sentence = random.choice(sentences)
        words = sentence.split()
        
        if len(words) < 5:
            return None
            
        # Find a key term to ask about
        key_word = random.choice([w for w in words if len(w) > 4 and w.isalpha()])
        
        question = f"What is the significance of '{key_word}' in the given context?"
        options = [
            sentence,
            "It has no significance",
            "It's a minor detail",
            "It's unrelated to the topic"
        ]
        random.shuffle(options)
        
        return {
            "question": self._add_personality_touch(question, personality),
            "answer": sentence,
            "question_type": QuestionType.MULTIPLE_CHOICE,
            "difficulty_level": difficulty,
            "options": options
        }