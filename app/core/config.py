"""Application configuration."""
from pydantic_settings import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Settings
    APP_NAME: str = "Enterprise AI Agent Platform"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Server Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = False

    # Database Settings
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/ai_agent_db"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40

    # Redis Settings
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_EXPIRY: int = 3600
    CACHE_TTL: int = 3600

    # JWT Settings
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # OpenAI Settings
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_MINI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDINGS_MODEL: str = "text-embedding-3-small"

    # AI Provider: openai (production) | groq (development)
    AI_PROVIDER: str = "openai"

    # Groq AI (Development only — ignored when AI_PROVIDER=openai)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    GROQ_SMART_MODEL: str = "llama-3.3-70b-versatile"

    # Embedding Provider: openai (production) | local (development)
    # Automatically set to "local" when AI_PROVIDER=groq
    EMBEDDING_PROVIDER: str = "openai"
    LOCAL_EMBEDDING_MODEL: str = "sentence-transformers/all-mpnet-base-v2"

    # Celery Settings
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    CELERY_TASK_SERIALIZER: str = "json"

    # Governance Settings
    ENABLE_COST_CONTROL: bool = True
    MAX_COST_PER_REQUEST: float = 10.0
    MONTHLY_BUDGET_LIMIT: float = 500.0
    ENABLE_RISK_ASSESSMENT: bool = True
    ENABLE_USAGE_TRACKING: bool = True
    ENABLE_GOVERNANCE: bool = True
    ENABLE_HALLUCINATION_CHECK: bool = True
    HALLUCINATION_THRESHOLD: float = 60.0
    RISK_ESCALATION_THRESHOLD: int = 70

    # Monitoring Settings
    ENABLE_MONITORING: bool = True
    SENTRY_DSN: Optional[str] = None

    # CORS Settings
    CORS_ORIGINS: List[str] = ["*"]
    CORS_CREDENTIALS: bool = True
    CORS_METHODS: List[str] = ["*"]
    CORS_HEADERS: List[str] = ["*"]

    # Embedding Settings
    EMBEDDING_DIMENSION: int = 384
    SIMILARITY_THRESHOLD: float = 0.7
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60

    # AWS S3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "ai-agent-platform"

    # Webhook Secrets
    SLACK_SIGNING_SECRET: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""
    INSTAGRAM_VERIFY_TOKEN: str = ""
    INSTAGRAM_ACCESS_TOKEN: str = ""
    MESSENGER_ACCESS_TOKEN: str = ""
    MESSENGER_VERIFY_TOKEN: str = ""
    MESSENGER_ORG_ID: str = ""
    MESSENGER_AGENT_ID: str = ""
    MESSENGER_CONVERSATION_ID: str = ""
    WHATSAPP_ORG_ID: str = ""
    WHATSAPP_AGENT_ID: str = ""
    WEBHOOK_SECRET: str = ""

    # Voice
    WHISPER_MODEL: str = "whisper-1"
    TTS_MODEL: str = "tts-1"
    TTS_VOICE: str = "alloy"

    # Token budgets
    MAX_CONTEXT_TOKENS: int = 8000
    MAX_OUTPUT_TOKENS: int = 2000
    SUMMARY_THRESHOLD_MESSAGES: int = 20

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # SaaS billing URLs
    BILLING_SUCCESS_URL: str = "https://app.example.com/billing/success"
    BILLING_CANCEL_URL: str = "https://app.example.com/billing/cancel"
    BILLING_PORTAL_RETURN_URL: str = "https://app.example.com/billing"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
