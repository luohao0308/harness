from app.tools.adapter_registry import REGISTRY, AdapterRegistry
from app.tools.adapters.github_adapter import register_github_adapters
from app.tools.adapters.sandbox_file_adapter import register_sandbox_file_adapters
from app.tools.adapters.slack_adapter import register_slack_adapters


def register_builtin_adapters(registry: AdapterRegistry) -> None:
    register_github_adapters(registry)
    register_slack_adapters(registry)
    register_sandbox_file_adapters(registry)


def ensure_builtin_adapters_registered(registry: AdapterRegistry = REGISTRY) -> None:
    if not registry.list_all():
        register_builtin_adapters(registry)


__all__ = [
    "ensure_builtin_adapters_registered",
    "register_builtin_adapters",
    "register_github_adapters",
    "register_sandbox_file_adapters",
    "register_slack_adapters",
]
