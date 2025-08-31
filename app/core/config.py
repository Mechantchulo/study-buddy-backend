from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database
    supabase_url: str
    supabase_key: str
    
    # Security
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # AI Services
    huggingface_api_key: str
    
    # Instasend Payments
    instasend_api_key: str
    instasend_secret_key: str
    instasend_callback_url: Optional[str] = "https://webhook.site/d86478da-55f3-41e0-ada1-1595eb6bb61e"
    
    # App
    app_name: str = "AI Study Buddy"
    version: str = "1.0.0"
    debug: bool = True
    
    class Config:
        env_file = ".env"

settings = Settings()