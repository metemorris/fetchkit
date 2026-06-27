import responses

from fetchkit.fetchers.arxiv import fetch_posts, ARXIV_API_URL, _build_search_query
from fetchkit.fetchers.arxiv import fetch as fetch_via_protocol
from fetchkit.fetchers.base import FetcherResult
from fetchkit.schemas.fetcher import ArxivFetchConfig, RSSFetchConfig, RSSFeedDescriptor

ATOM_BODY = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <published>2026-06-20T00:00:00Z</published>
    <updated>2026-06-20T00:00:00Z</updated>
    <title>Deep Learning Things</title>
    <summary>An abstract about learning.</summary>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <arxiv:doi>10.1234/example</arxiv:doi>
    <link href="http://arxiv.org/abs/2401.12345v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2401.12345v1" rel="related" type="application/pdf"/>
    <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
    <arxiv:primary_category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>
"""


def test_build_search_query_combines_categories_and_query() -> None:
    cfg = ArxivFetchConfig(categories=["cs.AI", "cs.LG"], query="transformers")
    q = _build_search_query(cfg)
    assert "cat:cs.AI OR cat:cs.LG" in q
    assert "all:transformers" in q
    assert " AND " in q


@responses.activate
def test_fetch_posts_parses_metadata() -> None:
    responses.add(responses.GET, ARXIV_API_URL, body=ATOM_BODY, status=200,
                  content_type="application/atom+xml")
    cfg = ArxivFetchConfig(categories=["cs.LG"], max_items=10)
    posts = fetch_posts(cfg)

    assert len(posts) == 1
    post = posts[0]
    assert post.id == "2401.12345v1"
    assert post.source == "arxiv"
    assert post.title == "Deep Learning Things"
    assert post.author == "Alice Smith, Bob Jones"
    assert post.metadata["authors"] == ["Alice Smith", "Bob Jones"]
    assert post.metadata["categories"] == ["cs.LG", "cs.AI"]
    assert post.metadata["doi"] == "10.1234/example"
    assert post.metadata["pdf_url"] == "http://arxiv.org/pdf/2401.12345v1"
    assert post.metadata["primary_category"] == "cs.LG"
    assert post.url == "http://arxiv.org/pdf/2401.12345v1"
    assert post.created_at is not None


@responses.activate
def test_fetch_protocol_wraps_errors() -> None:
    responses.add(responses.GET, ARXIV_API_URL, status=404)
    result = fetch_via_protocol(ArxivFetchConfig(max_items=5))
    assert isinstance(result, FetcherResult)
    assert result.posts == []
    assert len(result.errors) == 1


def test_fetch_protocol_rejects_wrong_config_type() -> None:
    import pytest
    with pytest.raises(ValueError):
        fetch_via_protocol(RSSFetchConfig(feeds=[RSSFeedDescriptor(url="https://x/y.xml")]))
