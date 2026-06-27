import pytest
from pydantic import ValidationError
from fetchkit.schemas.contracts import register_contract, get_contract_model, validate_data


def test_contract_registration() -> None:
    register_contract("test.int", int)
    assert get_contract_model("test.int") is int

    assert validate_data(42, int) == 42
    with pytest.raises(ValidationError):
        validate_data("not an int", int)


def test_get_unknown_contract() -> None:
    assert get_contract_model("unknown") is None


def test_contract_registration_rejects_conflicting_overwrite() -> None:
    register_contract("test.overwrite", list[int])
    with pytest.raises(ValueError, match="already registered"):
        register_contract("test.overwrite", list[str])


def test_contract_registration_allows_idempotent_reregistration() -> None:
    register_contract("test.same", list[int])
    register_contract("test.same", list[int])
