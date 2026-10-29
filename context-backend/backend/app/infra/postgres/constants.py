# ==========================================
# PostgreSQL Defaults
# ==========================================

DEFAULT_SCHEMA = "public"

# ==========================================
# Connection Pool
# ==========================================

DEFAULT_POOL_SIZE = 10
DEFAULT_MAX_OVERFLOW = 20
DEFAULT_POOL_TIMEOUT = 30
DEFAULT_POOL_RECYCLE = 1800

# ==========================================
# Connection
# ==========================================

DEFAULT_CONNECT_TIMEOUT = 10

# ==========================================
# Health Check
# ==========================================

HEALTH_CHECK_QUERY = "SELECT 1;"