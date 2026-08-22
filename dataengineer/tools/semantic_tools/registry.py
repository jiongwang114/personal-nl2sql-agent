
"""Re-export from datus-semantic-core for backward compatibility."""

from datus_semantic_core.registry import (  # noqa: F401
    AdapterMetadata,
    SemanticAdapterRegistry,
    semantic_adapter_registry,
)

__all__ = ["AdapterMetadata", "SemanticAdapterRegistry", "semantic_adapter_registry"]
