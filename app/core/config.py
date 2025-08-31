from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    #Database
    supabase_url: str
    supabase_key: str
    
    #security
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    #AI services
    huggingface_api_key: str
    
    #Payments
    instasend_api_key: str
    instasend_secret_key: str
    
    #App
    app_names: str = "Study Buddy"
    version: str = "1.0.0"
    debug: bool = True
    
    class Config:
        env_file = ".env"
        
settings = Settings()