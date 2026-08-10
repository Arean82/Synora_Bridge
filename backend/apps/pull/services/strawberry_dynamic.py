"""
Dynamic Strawberry schema generation for Pull GraphQL mode.

The schema is built at request time from a template's field mappings, so a
user can create a brand-new GraphQL endpoint instantly with zero code — every
type and resolver is generated on the fly.

Implementation follows the canonical Strawberry `create_type` API
(strawberry.tools.create_type in the official strawberry repository):
- each mapped target becomes a field on a dynamically created type
- nested object/list structures are built recursively (dot/bracket notation)
- leaf/nested resolvers read from `root` — the resolved parent value that
  Strawberry passes down automatically; the root Query field injects the
  transformed payload dict from context
"""
import re
from typing import Callable

import strawberry
from strawberry.tools import create_type
from strawberry.types.info import Info

from apps.core.services.data_transform import build_nested_payload


def _make_field(key: str, value: dict, name: str) -> Callable:
    """Build one dynamic field; recursively creates nested types.

    The resolver's return annotation must be the actual type, so the
    function is defined inside this closure after `ftype` is computed —
    the pattern validated against strawberry 0.323.
    """
    if "_type" in value:
        ftype = str
    else:
        ftype = _make_type(f"{name}_{key}", value)
    if value.get("_is_list"):
        ftype = list[ftype]  # type: ignore[valid-type]

    def resolver(root: object, info: Info) -> ftype:  # type: ignore[valid-type,misc]  (dynamic pattern)
        if isinstance(root, dict):
            return root.get(key)
        return None

    resolver.__name__ = key  # python_name follows the function name
    return strawberry.field(name=key)(resolver)  # type: ignore[return-value]


def _make_type(name: str, schema_dict: dict) -> type:
    """Build a Strawberry type from a nested schema dict."""
    fields = [
        _make_field(key, value, name)
        for key, value in schema_dict.items()
        if not key.startswith("_")
    ]
    return create_type(name=name, fields=fields)  # type: ignore[arg-type]


def build_schema_dict(field_mapping: list[dict]) -> dict:
    """
    Convert a template's field_mapping into a nested schema dict.

    Example mapping: [{"source": "source_0.gps_lat", "target": "gps[0].latitude"}]
    becomes: {"gps": {"_is_list": True, "latitude": {"_is_list": False, "_type": "String"}}}
    """
    schema: dict = {}

    def _segments(target: str):
        parts = target.split(".")
        for idx, part in enumerate(parts):
            m = re.match(r"(.+)\[(\d*)\]", part)
            name = m.group(1) if m else part
            is_list = bool(m)
            yield name, is_list, idx == len(parts) - 1

    for mapping in field_mapping or []:
        target = mapping.get("target")
        if not target:
            continue
        current = schema
        for i, (name, is_list, is_last) in enumerate(_segments(target)):
            if name not in current:
                current[name] = {"_is_list": is_list, "_type": "String"} if is_last else {"_is_list": is_list}
            if not is_last:
                current = current[name]

    return schema


def _payload_type_name(slug: str) -> str:
    """Sanitize a template slug into a valid GraphQL type name."""
    parts = [p for p in re.split(r"[^a-zA-Z0-9]", slug) if p]
    return "".join(p.capitalize() for p in parts) + "Payload"


def _resolve_destination(template, dest_slug=None):
    """Pick the destination by slug, or fall back to the first."""
    destinations = template.destinations or []
    if not destinations:
        return {"name": "default", "field_mapping": []}
    if dest_slug:
        for dest in destinations:
            slug = re.sub(r"[^a-z0-9]", "_", (dest.get("name") or "").lower())
            if slug == dest_slug:
                return dest
        # Unknown slug: fall back to the first destination (original behavior).
    return destinations[0]


def build_graphql_schema(template, dest_slug=None):
    """Build a full Strawberry schema for a template's GraphQL pull endpoint."""
    dest = _resolve_destination(template, dest_slug)
    mapping = dest.get("field_mapping", [])

    schema_dict = build_schema_dict(mapping)
    if not schema_dict:
        schema_dict = {"data": {"_is_list": False, "_type": "String"}}

    PayloadType = _make_type(_payload_type_name(template.slug), schema_dict)

    @strawberry.type
    class Query:
        data: PayloadType  # type: ignore[valid-type,misc]

        @strawberry.field
        def data(self, info: Info) -> PayloadType:  # type: ignore[valid-type,misc]
            return info.context["payload"]

    return strawberry.Schema(query=Query)  # type: ignore[arg-type]


def execute_graphql(template, query, variables=None, dest_slug=None):
    """Fetch sources, transform, and execute a GraphQL query against the
    template's dynamic schema (optionally for one destination). Returns
    (data, errors)."""
    from apps.jobs.tasks import fetch_all_sources

    dest = _resolve_destination(template, dest_slug)
    mapping = dest.get("field_mapping", [])
    aggregated = fetch_all_sources(template)
    result_payload = build_nested_payload(mapping, aggregated)

    schema = build_graphql_schema(template, dest_slug)
    result = schema.execute_sync(
        query,
        variable_values=variables or {},
        context_value={"payload": result_payload},
    )
    return result.data, result.errors
