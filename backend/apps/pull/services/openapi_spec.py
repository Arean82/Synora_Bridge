"""
Dynamic OpenAPI spec generator for Pull REST endpoints.

Ports original `bridge_app/services/swagger_service.py`, producing specs in
Swagger 2.0 / OpenAPI 3.0.3 / 3.1.0 / 3.2.0 on the fly from a template's
field mappings. Structure follows the official OpenAPI Specification
(3.2.0 spec per the official OpenAPI Specification repository, versions/3.2.0.md).

Note: OAS 3.2.0 keeps the same top-level document shape as 3.1.0 for simple
object responses (openapi field, info, servers, paths, components); 3.2.0
bases schemas on JSON Schema 2020-12, which changes nothing for the
string-typed object properties this generator emits.
"""
import json

from apps.configs.models import Template

SUPPORTED_OPENAPI_VERSIONS = ["2.0", "3.0.3", "3.1.0", "3.2.0"]


def _dest_slug(name) -> str:
    slug = (name or "default").lower().replace(" ", "_").replace("-", "_")
    return "".join(c for c in slug if c.isalnum() or c == "_")


def generate_pull_endpoint_spec(template: Template, requested_version="3.2.0"):
    """Generate an OpenAPI/Swagger spec for a template's pull endpoints."""
    t_dict = _to_dict(template)
    destinations = t_dict.get("destinations") or [{"name": "default", "field_mapping": []}]

    if requested_version not in SUPPORTED_OPENAPI_VERSIONS:
        requested_version = "3.2.0"
    is_v2 = requested_version.startswith("2.")

    links_md = "\n\n**Available API Versions:**\n"
    for v in SUPPORTED_OPENAPI_VERSIONS[::-1]:
        if v == requested_version:
            continue
        label = "Swagger" if v == "2.0" else "OpenAPI"
        links_md += (
            f"- [View {label} {v}](/api/v1/bridge/pull/{template.slug}/docs?version={v})\n"
        )
    base_description = "Auto-generated API Gateway for Template: " + template.name + links_md

    spec = {}
    if is_v2:
        spec.update(
            {
                "swagger": "2.0",
                "info": {"title": template.name, "description": base_description, "version": "1.0.0"},
                "basePath": "/",
            }
        )
    else:
        spec.update(
            {
                "openapi": requested_version,
                "info": {"title": template.name, "description": base_description, "version": "1.0.0"},
                "servers": [{"url": "/"}],
            }
        )

    spec["paths"] = {}
    for dest in destinations:
        d_slug = _dest_slug(dest.get("name"))
        properties = {}
        for mapping in dest.get("field_mapping", []):
            target = mapping.get("target")
            if target:
                properties[target] = {"type": "string"}

        path = f"/api/v1/bridge/pull/{template.slug}/{d_slug}"
        method = dest.get("method", template.pull_method or "get").lower()

        if is_v2:
            endpoint_def = {
                "summary": f"Fetch and transform data for {dest.get('name', 'Client')}",
                "description": "Pulls data from configured sources and translates it into the mapped schema.",
                "produces": ["application/json"],
                "responses": {
                    "200": {
                        "description": "Successful operation",
                        "schema": {"type": "object", "properties": properties},
                    },
                    "401": {"description": "Unauthorized"},
                },
            }
        else:
            endpoint_def = {
                "summary": f"Fetch and transform data for {dest.get('name', 'Client')}",
                "description": "Pulls data from configured sources and translates it into the mapped schema.",
                "responses": {
                    "200": {
                        "description": "Successful operation",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "properties": properties}
                            }
                        },
                    },
                    "401": {"description": "Unauthorized"},
                },
            }
        spec["paths"][path] = {method: endpoint_def}

    # Auth requirements when a client token is configured.
    client_creds = t_dict.get("client_credentials") or {}
    if client_creds.get("token"):
        if is_v2:
            spec["securityDefinitions"] = {
                "Bearer": {
                    "type": "apiKey",
                    "name": "Authorization",
                    "in": "header",
                    "description": "Format: Bearer <token>",
                }
            }
        else:
            spec["components"] = {
                "securitySchemes": {
                    "Bearer": {"type": "http", "scheme": "bearer"}
                }
            }
        for _path, methods in spec["paths"].items():
            for _method in methods:
                spec["paths"][_path][_method]["security"] = [{"Bearer": []}]

    return spec


def _to_dict(template: Template) -> dict:
    """Lightweight template serialization for spec generation (avoids cycles)."""
    return {
        "destinations": template.destinations or [],
        "client_credentials": template.client_credentials or {},
    }


def get_swagger_ui_html(title, template_slug, requested_version="3.2.0"):
    """Render Swagger UI configured for a template's generated spec."""
    spec_url = f"/api/v1/bridge/pull/{template_slug}/spec?version={requested_version}"
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>{title} - Swagger UI</title>
      <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
    </head>
    <body>
      <div id="swagger-ui"></div>
      <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js" crossorigin></script>
      <script>
        window.onload = () => {{
          window.ui = SwaggerUIBundle({{
            url: window.location.origin + '{spec_url}',
            dom_id: '#swagger-ui',
            deepLinking: true,
            presets: [
              SwaggerUIBundle.presets.apis,
              SwaggerUIBundle.SwaggerUIStandalonePreset
            ],
            layout: "BaseLayout",
          }});
        }};
      </script>
    </body>
    </html>
    """
