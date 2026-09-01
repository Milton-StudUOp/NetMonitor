import json

from sqlalchemy import JSON, Text
from sqlalchemy.types import TypeDecorator


class PortableJSON(TypeDecorator):
    """Native JSON where supported, transparently serialized CLOB on Oracle."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(Text()) if dialect.name == "oracle" else dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None: return None
        return json.dumps(value, ensure_ascii=False) if dialect.name == "oracle" else value

    def process_result_value(self, value, dialect):
        if value is None: return None
        return json.loads(value) if dialect.name == "oracle" and isinstance(value, str) else value
