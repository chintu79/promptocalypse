from typing import Any, Optional
from pydantic import BaseModel, Field


# Request Models
class RegisterRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=2,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_\- ]+$",
        description="Participant full name or handle (2-50 chars)",
    )
    email: Optional[str] = Field(
        None,
        description="Participant registered email address",
    )


class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Unique participant ID")
    prompt: str = Field(
        ...,
        max_length=1000,
        description="Prompt payload to send to the target LLM (capped at 1000 characters)",
    )


class SubmitKeyRequest(BaseModel):
    user_id: str = Field(..., description="Unique participant ID")
    level: int = Field(..., description="The level this key is for")
    key: str = Field(..., description="Extracted secret flag key")


# Response Models
class RegisterResponse(BaseModel):
    user_id: str
    username: str
    email: Optional[str] = None
    active_level: int = 1
    cleared_levels: list[int] = []
    start_time: str
    total_prompts: int = 0
    failed_attempts: int = 0
    completed: bool = False


class ChatResponse(BaseModel):
    reply: str
    latency_ms: Optional[int] = None
    cooldown_seconds: float = 3.0
    status: Optional[str] = None


class SubmitKeyResponse(BaseModel):
    status: str
    unlocked_level: Optional[int] = None
    message: str
    penalty_points: Optional[int] = None
    final_score: Optional[float] = None
    completion_time: Optional[str] = None
    stats: Optional[dict[str, Any]] = None


class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    current_level: int
    completed: bool
    final_score: float
    total_prompts: int
    total_chars: int
    duration_seconds: Optional[int] = None
    status: str = "In Progress"


class UserStateResponse(BaseModel):
    user_id: str
    username: str
    email: Optional[str] = None
    current_level: int
    start_time: str
    completed_at: Optional[str] = None
    total_prompts: int = 0
    total_chars: int = 0
    failed_attempts: int = 0
    final_score: float = 0.0
    is_disqualified: bool = False
    completed: bool = False


# Health & Readiness Diagnostic Response Models (Issue #26)
class HealthDatabaseStatus(BaseModel):
    status: str
    latency_ms: Optional[int] = None
    journal_mode: Optional[str] = None
    error: Optional[str] = None


class HealthProviderStatus(BaseModel):
    status: str
    name: str = "groq"
    model: str = ""
    latency_ms: Optional[int] = None
    cached: bool = False
    checked_at: str
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    database: HealthDatabaseStatus
    provider: HealthProviderStatus
    timestamp: str

class ScenarioResponse(BaseModel):
    level: int
    target: str
    scenario: str
    attack_vector: str
