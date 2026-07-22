import os
from functools import lru_cache
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from ml import AIRanker
import uvicorn

app = FastAPI(title="SmartFeed AI API")


@lru_cache(maxsize=1)
def get_ranker() -> AIRanker:
    return AIRanker()


@app.on_event("startup")
async def warm_ranker() -> None:
    # Keep AIRanker as a process-wide singleton so the model and caches
    # are initialized once and then reused across requests.
    get_ranker()

# --- Pydantic Schemas for Validation ---
class Video(BaseModel):
    video_id: str
    title: str
    description: Optional[str] = ""
    channel: str

class RankRequest(BaseModel):
    # Preferred format: {"interests": ["Programming", "AI", "Startups"]}
    # Also accepts {"selected_topics": [...]}.
    interests: Optional[List[str]] = None
    selected_topics: Optional[List[str]] = None
    videos: List[Video]

    def topic_names(self) -> List[str]:
        return self.selected_topics or self.interests or []

# --- API Endpoints ---
@app.get("/")
async def root():
    return {
        "service": "SmartFeed AI API",
        "status": "ok"
    }


@app.get("/health")
async def health_check():
    groq_configured = bool(os.getenv("GROQ_API_KEY"))

    try:
        get_ranker()
        model_status = "ready"
    except Exception as error:
        model_status = f"unavailable: {error}"

    return {
        "service": "SmartFeed AI API",
        "status": "ok",
        "groq_configured": groq_configured,
        "model_status": model_status
    }


@app.post("/api/v1/rank-feed")
async def rank_feed(request: RankRequest):
    try:
        ranker = get_ranker()
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI ranker is not available. "
                f"Check model downloads and GROQ_API_KEY. Error: {error}"
            )
        ) from error

    # Convert Pydantic objects to standard dictionaries for the ML engine
    videos_dict = [v.model_dump() for v in request.videos]

    # Performance note for the frontend:
    # - send only newly discovered videos
    # - never resend previously processed videos
    # - reuse existing rankings
    # - merge new rankings into existing ones
    #
    # The current backend contract already supports incremental ranking.

    # Process through the AI pipeline
    ranked_results = ranker.rank_videos(videos_dict, request.topic_names())
    
    return {"ranked_videos": ranked_results}

# To run the server directly
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=True
    )
