from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from app.routers import auth, ai, cards, gamification, payments
# Create FastAPI instance
app = FastAPI(
    title="AI Study Buddy",
    description="AI-powered gamified flashcard learning platform",
    version="1.0.0"
)

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(ai.router, prefix="/ai", tags=["AI"])
app.include_router(cards.router, prefix="/cards", tags=["Cards"])
app.include_router(gamification.router, prefix="/gamification", tags=["Gamification"])
app.include_router(payments.router, prefix="/payments", tags=["Payments"])

@app.get("/")
async def root():
    return {
        "message": "Welcome to AI Study Buddy API! 🧠✨",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "ready_to_learn"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "services": {
            "database": "ready",
            "ai": "ready", 
            "gamification": "active"
        }
    }

# Basic test endpoints
@app.get("/api/test")
async def test_endpoint():
    return {"message": "API is working! 🚀"}

@app.get("/api/plans")
async def get_plans():
    return {
        "plans": {
            "pro": {
                "name": "Pro Learner",
                "price": 500,
                "features": ["Unlimited AI questions", "Analytics"]
            },
            "premium": {
                "name": "Premium Scholar", 
                "price": 1000,
                "features": ["Everything in Pro", "Group study"]
            }
        }
    }

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0", 
        port=8000,
        reload=True
    )