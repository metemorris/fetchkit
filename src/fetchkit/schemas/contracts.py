"""Lightweight, internal contract registry.

This is an internal utility — not part of fetchkit's public API. It maps a string
``contract_id`` to a Pydantic model/type so callers that want to validate fetched
data against a named schema can do so. fetchkit itself does not require it; the
canonical schema is simply ``list[Post]``.
"""

from typing import Any, Optional
from pydantic import TypeAdapter

# Registry mapping contract_id (e.g., "posts") to a Pydantic model class or type.
CONTRACT_REGISTRY: dict[str, Any] = {}


def register_contract(contract_id: str, model: Any) -> None:
    """Register a Pydantic model or type for a given contract ID.

    Idempotent re-registration of the same model is allowed; registering a
    different model under an existing ID raises ``ValueError``.
    """
    existing = CONTRACT_REGISTRY.get(contract_id)
    if existing is not None and existing != model:
        raise ValueError(
            f"Contract '{contract_id}' is already registered with a different model"
        )
    CONTRACT_REGISTRY[contract_id] = model


def get_contract_model(contract_id: str) -> Optional[Any]:
    """Return the model registered for a contract ID, or None."""
    return CONTRACT_REGISTRY.get(contract_id)


def validate_data(data: Any, model: Any) -> Any:
    """Validate ``data`` against a Pydantic model or type.

    Returns the validated data (with defaults/conversions applied). Raises
    ``pydantic.ValidationError`` if validation fails.
    """
    return TypeAdapter(model).validate_python(data)
