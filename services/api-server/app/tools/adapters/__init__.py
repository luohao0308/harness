from app.tools.adapter_registry import REGISTRY, AdapterRegistry
from app.tools.adapters.code_interpreter_adapter import register_code_interpreter_adapters
from app.tools.adapters.github_adapter import register_github_adapters
from app.tools.adapters.linear_adapter import register_linear_adapters
from app.tools.adapters.notion_adapter import register_notion_adapters
from app.tools.adapters.sandbox_file_adapter import register_sandbox_file_adapters
from app.tools.adapters.slack_adapter import register_slack_adapters


def register_builtin_adapters(registry: AdapterRegistry) -> None:
    register_github_adapters(registry)
    register_slack_adapters(registry)
    register_notion_adapters(registry)
    register_linear_adapters(registry)
    register_code_interpreter_adapters(registry)
    register_sandbox_file_adapters(registry)


def _builtin_adapter_templates() -> list:
    registry = AdapterRegistry()
    register_builtin_adapters(registry)
    return registry.list_all()


def ensure_builtin_adapters_registered(registry: AdapterRegistry = REGISTRY) -> None:
    missing = [
        adapter for adapter in _builtin_adapter_templates() if registry.get(adapter.slug) is None
    ]
    for adapter in missing:
        registry.register(adapter)


__all__ = [
    "ensure_builtin_adapters_registered",
    "register_builtin_adapters",
    "register_code_interpreter_adapters",
    "register_github_adapters",
    "register_linear_adapters",
    "register_notion_adapters",
    "register_sandbox_file_adapters",
    "register_slack_adapters",
]
