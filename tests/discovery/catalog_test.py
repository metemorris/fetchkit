"""Integrity tests for the shipped catalog and the catalog loader."""

from pathlib import Path

from fetchkit.discovery.catalog import load_catalog

FIXTURE = str(Path(__file__).parent.parent / "testdata" / "discovery" / "catalog_fixture.json")


def test_shipped_catalog_loads_and_is_valid() -> None:
    catalog = load_catalog()
    assert isinstance(catalog.catalog_version, int)
    assert catalog.catalog_version >= 1
    assert len(catalog.entries) > 0


def test_shipped_catalog_has_unique_ids_and_urls() -> None:
    entries = load_catalog().entries
    ids = [e.id for e in entries]
    urls = [e.url for e in entries]
    assert len(ids) == len(set(ids)), "duplicate catalog id"
    assert len(urls) == len(set(urls)), "duplicate catalog url"


def test_shipped_catalog_urls_are_http() -> None:
    for entry in load_catalog().entries:
        assert entry.url.startswith(("http://", "https://")), entry.id


def test_shipped_catalog_entries_have_retrieval_text() -> None:
    # Descriptions drive ranking quality, so none may be empty.
    for entry in load_catalog().entries:
        assert entry.name.strip()
        assert entry.description.strip()


def test_load_catalog_with_override_path() -> None:
    catalog = load_catalog(FIXTURE)
    assert catalog.catalog_version == 7
    assert len(catalog.entries) == 6
    assert any(e.id == "rust-blog" for e in catalog.entries)
