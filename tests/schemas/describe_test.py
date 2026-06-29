import json

from fetchkit import __version__
from fetchkit.schemas.describe import build_schema_document
from fetchkit.schemas.fetcher import _BUILTIN_TYPES


def test_document_has_top_level_sections() -> None:
    doc = build_schema_document()
    assert doc["version"] == __version__
    assert set(doc) == {"version", "config", "http", "fetchers", "post", "discovery"}


def test_discovery_section_describes_capability() -> None:
    doc = build_schema_document()
    discovery = doc["discovery"]
    assert discovery["maps_to_fetcher"] == "rss"
    assert set(discovery["candidate_sources"]) == {"catalog", "autodiscovery", "external"}
    assert "auto" in discovery["ranker_backends"]
    assert isinstance(discovery["catalog_version"], int)
    # The FeedMatch schema is embedded so agents learn the result shape.
    assert discovery["feed_match"]["type"] == "object"
    assert "url" in discovery["feed_match"]["properties"]


def test_all_builtin_fetchers_are_described() -> None:
    doc = build_schema_document()
    assert set(doc["fetchers"]) == set(_BUILTIN_TYPES)
    # Each entry is a real JSON Schema object with properties.
    for schema in doc["fetchers"].values():
        assert schema["type"] == "object"
        assert "properties" in schema


def test_document_is_json_serializable() -> None:
    # The whole point is that an agent can parse this off stdout.
    json.dumps(build_schema_document())


def test_field_descriptions_flow_through() -> None:
    doc = build_schema_document()
    # Descriptions attached via Field(...) on the models must reach the schema.
    rss_props = doc["fetchers"]["rss"]["properties"]
    assert "Disabled" in rss_props["allow_local_files"]["description"]
    assert doc["post"]["properties"]["source"]["description"]
