"""Application-wide constants."""

# Model names
GPT4O = "gpt-4o"
GPT4O_MINI = "gpt-4o-mini"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Risk levels
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_CRITICAL = "critical"
RISK_LEVELS = [RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL]

# Message roles
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"

# Governance actions
ACTION_ALLOW = "allow"
ACTION_WARN = "warn"
ACTION_BLOCK = "block"

# Escalation statuses
ESCALATION_PENDING = "pending"
ESCALATION_REVIEWED = "reviewed"
ESCALATION_RESOLVED = "resolved"

# Cache prefixes
CACHE_SEMANTIC = "semantic_cache"
CACHE_SESSION = "session"
CACHE_TOKEN = "token"
CACHE_RATE_LIMIT = "rate_limit"
CACHE_EMBEDDING = "embedding"
CACHE_RESPONSE = "response"

# Token pricing per 1M tokens (USD)
MODEL_PRICING = {
    GPT4O: {"input": 5.0, "output": 15.0},
    GPT4O_MINI: {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
}

# Intent categories for model routing
INTENT_GREETING = "greeting"
INTENT_FAQ = "faq"
INTENT_REASONING = "reasoning"
INTENT_SUMMARIZATION = "summarization"
INTENT_GOVERNANCE = "governance"
INTENT_RISK = "risk"
INTENT_GENERAL = "general"

# File types allowed for upload
ALLOWED_FILE_TYPES = {
    "application/pdf": "pdf",
    "text/plain": "txt",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/markdown": "md",
    "text/csv": "csv",
}

MAX_FILE_SIZE_MB = 50
MAX_CHUNK_SIZE = 4000
CHUNK_OVERLAP = 200

# Hallucination thresholds
HALLUCINATION_LOW = 25.0
HALLUCINATION_MEDIUM = 50.0
HALLUCINATION_HIGH = 75.0

# Celery queue names
QUEUE_AI_PROCESSING = "ai_processing"
QUEUE_EMBEDDINGS = "embeddings"
QUEUE_GOVERNANCE = "governance"
QUEUE_RISK = "risk_assessment"
QUEUE_HALLUCINATION = "hallucination"
QUEUE_VOICE = "voice"
QUEUE_ANALYTICS = "analytics"
QUEUE_CLEANUP = "cleanup"
QUEUE_ESCALATION = "escalation"

# Crawler queue names (independently scalable)
QUEUE_CRAWLER = "crawler"
QUEUE_CRAWLER_FETCH = "crawler_fetch"
QUEUE_CRAWLER_EXTRACT = "crawler_extract"
QUEUE_CRAWLER_EMBED = "crawler_embed"

# Crawler constants
CRAWLER_MAX_PAGES_DEFAULT = 100
CRAWLER_MAX_DEPTH_DEFAULT = 5
CRAWLER_MAX_JS_RENDERS = 20
CRAWLER_FETCH_CONCURRENCY = 20
CRAWLER_DELAY_SECONDS = 0.3
CRAWLER_RECRAWL_INTERVAL_HOURS = 24
CRAWLER_MIN_CONTENT_LENGTH = 30
CRAWLER_EXTRACTION_QUALITY_THRESHOLD = 0.5
CRAWLER_RAW_HTML_PREFIX = "crawler/raw"
