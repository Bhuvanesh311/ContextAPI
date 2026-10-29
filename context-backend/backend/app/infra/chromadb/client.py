import logging

import chromadb
import httpx

from app.core.config import settings
from app.infra.chromadb.config import chromadb_config

logger = logging.getLogger(__name__)


chroma_client = chromadb.HttpClient(
    host=chromadb_config.host,
    port=chromadb_config.port,
    ssl=chromadb_config.ssl,
)

# chromadb builds its httpx client with timeout=None and exposes no setting,
# so a hung server would block forever. Set it on the underlying session.
_session = getattr(getattr(chroma_client, "_server", None), "_session", None)
if isinstance(_session, httpx.Client):
    _session.timeout = httpx.Timeout(settings.CHROMADB_HTTP_TIMEOUT_SECONDS, connect=5.0)
else:
    logger.warning("Could not set ChromaDB HTTP timeout (client internals changed)")
