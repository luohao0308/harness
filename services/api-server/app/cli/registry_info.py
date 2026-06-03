from __future__ import annotations

import json

from app.tools.adapter_registry import REGISTRY, adapter_metadata
from app.tools.adapters import ensure_builtin_adapters_registered


def main() -> None:
    ensure_builtin_adapters_registered(REGISTRY)
    payload = {
        "adapter_count": len(REGISTRY.list_all()),
        "adapters": [adapter_metadata(adapter) for adapter in REGISTRY.list_all()],
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
