import ssl

import certifi


def verified_tls_context() -> ssl.SSLContext:
    """Build a verified TLS context independent of a custom Python prefix."""
    return ssl.create_default_context(cafile=certifi.where())
