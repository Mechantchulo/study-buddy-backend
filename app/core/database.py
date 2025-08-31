from supabase import create_client, Client
from app.core.config import settings


#initializing Supabase client
supabase: Client = create_client(settings.supabase_url, settings.supabase_key)

class Database:
    def __init__(self):
        self.client = supabase
        
    async def get_client(self) -> Client:
        return self.client
    
# Dependency for getting database client
async def get_database() -> Client:
    return supabase