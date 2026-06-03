from app.tools.adapter_registry import AdapterRegistry, adapter_metadata, adapter_snapshot
from app.tools.adapters import ensure_builtin_adapters_registered, register_builtin_adapters
from app.tools.adapters.github_adapter import GitHubAdapter


def test_adapter_registry_register_get_and_list() -> None:
    registry = AdapterRegistry()
    register_builtin_adapters(registry)

    adapter = registry.get("github.list_issues")

    assert adapter is not None
    assert adapter.server_label == "github"
    assert adapter.method == "list_issues"
    assert "github.list_issues" in {item.slug for item in registry.list_for_server("github")}
    assert registry.list_all() == sorted(registry.list_all(), key=lambda item: item.slug)


def test_adapter_registry_rejects_duplicate_slug() -> None:
    registry = AdapterRegistry()
    adapter = GitHubAdapter(
        slug="github.list_issues",
        method="list_issues",
        description="List issues",
        input_schema={},
        output_schema={},
    )

    registry.register(adapter)

    try:
        registry.register(adapter)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate adapter slug should fail")


def test_adapter_metadata_includes_reproducible_hashes() -> None:
    registry = AdapterRegistry()
    register_builtin_adapters(registry)
    adapter = registry.get("slack.search_messages")
    assert adapter is not None

    snapshot = adapter_snapshot(adapter)
    metadata = adapter_metadata(adapter)

    assert snapshot["slug"] == "slack.search_messages"
    assert snapshot["adapter_sha256"] == metadata["adapter_sha256"]
    assert len(snapshot["adapter_sha256"]) == 64
    assert len(snapshot["input_schema_sha256"]) == 64
    assert metadata["input_schema"]["type"] == "object"


def test_ensure_builtin_adapters_registered_is_idempotent() -> None:
    registry = AdapterRegistry()

    ensure_builtin_adapters_registered(registry)
    first_slugs = [adapter.slug for adapter in registry.list_all()]
    ensure_builtin_adapters_registered(registry)
    second_slugs = [adapter.slug for adapter in registry.list_all()]

    assert first_slugs
    assert second_slugs == first_slugs


def test_ensure_builtin_adapters_registered_tolerates_existing_builtin() -> None:
    registry = AdapterRegistry()
    registry.register(
        GitHubAdapter(
            slug="github.list_issues",
            method="list_issues",
            description="List issues",
            input_schema={},
            output_schema={},
        )
    )

    ensure_builtin_adapters_registered(registry)

    assert registry.get("github.list_issues") is not None
    assert registry.get("slack.search_messages") is not None
