# Ollama default values

DEFAULT_BASE_URL        = "http://localhost:11434"
DEFAULT_MODEL           = "qwen3:4b-instruct"
DEFAULT_TIMEOUT_SECONDS = 60

# API paths
GENERATE_PATH = "/api/generate"
TAGS_PATH     = "/api/tags"     # used for health check (lists local models)
