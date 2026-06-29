"""Exceptions raised by the discovery subpackage."""


class DiscoveryError(Exception):
    """Base class for all discovery errors."""


class DiscoveryBackendUnavailable(DiscoveryError):
    """Raised when a requested ranker backend's optional dependencies are missing.

    The default (lexical) ranker has no extra dependencies, so this only fires
    when an embedding backend is explicitly requested without the
    ``discovery-embeddings`` extra installed. The message carries the pip install
    line needed to enable it.
    """
