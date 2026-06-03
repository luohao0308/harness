"""Knowledge/RAG public API with compatibility exports."""

# ruff: noqa: F401,F403,I001
from app.knowledge_coze import get_coze_retrieval_adapter
from app.knowledge_dify import get_dify_retrieval_adapter, resolve_connector_secret_ref
from app.knowledge_web import get_web_research_adapter, resolve_web_research_api_key

from .common import *
from .connectors import *
from .settings import *
from .lifecycle import *
from .rag import *

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
