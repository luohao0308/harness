"""Agent API package with compatibility exports."""

# ruff: noqa: I001

from .router import router

# Import endpoint modules in route-specificity order so the single-segment
# ``/{agent_id}`` detail route stays after top-level collection routes.
from . import agent_crud as agent_crud  # noqa: E402,F401
from . import agent_settings as agent_settings  # noqa: E402,F401
from . import agent_knowledge as agent_knowledge  # noqa: E402,F401
from . import agent_messages as agent_messages  # noqa: E402,F401
from . import agent_runs as agent_runs  # noqa: E402,F401
from . import agent_chat as agent_chat  # noqa: E402,F401
from . import agent_cli as agent_cli  # noqa: E402,F401
from . import agent_context as agent_context  # noqa: E402,F401
from . import agent_manifest as agent_manifest  # noqa: E402,F401
from . import agent_get as agent_get  # noqa: E402,F401
from ._grounding_helpers import _normalize_grounding_citations  # noqa: E402
from ._workspace_chat_helpers import _create_workspace_chat_run  # noqa: E402
from .common import AuditedModelGateway  # noqa: E402
from .common import ingest_knowledge_source  # noqa: E402

__all__ = [
    "router",
    "AuditedModelGateway",
    "ingest_knowledge_source",
    "_create_workspace_chat_run",
    "_normalize_grounding_citations",
]
