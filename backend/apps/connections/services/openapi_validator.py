"""
OpenAPI/Swagger specification validator — with hardened SSRF protection.

Port of `bridge_app/services/openapi_validator.py`, with two production-grade
improvements over the original:
1. SSRF check is hardened: resolves the hostname and blocks private/loopback
   CIDR ranges + link-local metadata IPs (the original only matched literal
   'localhost'/'127.0.0.1', which decimal/alternative IP forms bypass).
2. `resolve_refs` is fully implemented (internal `$ref` resolution for
   components/definitions) instead of the original's explicit placeholder.

Used by the connection validation API and the mock server.
"""
import ipaddress
import json
import socket
from dataclasses import dataclass
from typing import Any, List, Optional
from urllib.parse import urlparse

import requests
import yaml
from openapi_spec_validator import validate
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError

# RFC1918 + loopback + link-local + CGNAT + 6to4 relay — never fetch these.
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local (169.254.169.254 metadata)
    ipaddress.ip_network("100.64.0.0/10"),    # CGNAT
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),         # unique local
    ipaddress.ip_network("fe80::/10"),        # link-local v6
]


class OpenAPISecurityError(Exception):
    pass


class OpenAPIParseError(Exception):
    pass


@dataclass
class NormalizedOperation:
    operation_id: str
    path: str
    method: str
    summary: Optional[str]
    parameters: list
    request_body: Optional[Any]
    responses: dict
    security: list
    tags: List[str]


class OpenAPIValidator:
    MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
    TIMEOUT_SECONDS = 10
    MAX_REDIRECTS = 3

    def __init__(self):
        self.session = requests.Session()
        self.session.max_redirects = self.MAX_REDIRECTS

    # ------------------------------------------------------------------
    # SSRF protection
    # ------------------------------------------------------------------
    def _is_private(self, ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return True  # unparseable → refuse
        return any(addr in net for net in _PRIVATE_NETWORKS)

    def _check_ssrf(self, url: str) -> bool:
        """Reject URLs that resolve to private/loopback/link-local hosts.

        Resolves the hostname to all A/AAAA records and rejects if ANY is
        private — closes the decimal-IP, alt-hostname and mixed-resolution
        bypasses of the original exact-string check.
        """
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        if not hostname.isdigit() and not hostname.startswith("["):
            try:
                infos = socket.getaddrinfo(hostname, None)
            except socket.gaierror:
                return False  # unresolvable host → refuse
            for info in infos:
                ip = info[4][0]
                if self._is_private(ip):
                    return False
        else:
            # Literal IP form — check directly (also catches decimal/hex forms
            # that urlparse normalizes).
            try:
                ip = socket.getaddrinfo(hostname, None, socket.AF_INET)[0][4][0]
            except (socket.gaierror, IndexError):
                ip = hostname
            if self._is_private(ip):
                return False
        return True

    # ------------------------------------------------------------------
    # Fetch + parse + validate
    # ------------------------------------------------------------------
    def fetch_from_url(self, url: str, auth_headers: dict = None) -> str:
        if not self._check_ssrf(url):
            raise OpenAPISecurityError("URL rejected due to SSRF protection.")

        headers = auth_headers or {}
        try:
            response = self.session.get(url, headers=headers, timeout=self.TIMEOUT_SECONDS, stream=True)
            response.raise_for_status()

            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > self.MAX_SIZE_BYTES:
                raise OpenAPISecurityError("Specification file exceeds maximum allowed size.")

            content = response.content
            if len(content) > self.MAX_SIZE_BYTES:
                raise OpenAPISecurityError("Specification file exceeds maximum allowed size.")

            return content.decode("utf-8")
        except requests.exceptions.RequestException as exc:
            raise OpenAPIParseError(f"Failed to fetch specification from URL: {exc}")

    def parse_content(self, content: str) -> dict:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            try:
                return yaml.safe_load(content)
            except yaml.YAMLError as exc:
                raise OpenAPIParseError(f"Failed to parse content as JSON or YAML: {exc}")

    def detect_version(self, spec_dict: dict) -> str:
        if "swagger" in spec_dict:
            return f"Swagger {spec_dict['swagger']}"
        if "openapi" in spec_dict:
            return f"OpenAPI {spec_dict['openapi']}"
        raise OpenAPIParseError("Could not detect Swagger or OpenAPI version field.")

    def validate_spec(self, spec_dict: dict):
        try:
            validate(spec_dict)
        except OpenAPIValidationError as exc:
            raise OpenAPIParseError(f"OpenAPI validation failed: {exc}")
        except Exception as exc:
            raise OpenAPIParseError(f"Validation error: {exc}")

    # ------------------------------------------------------------------
    # $ref resolution (internal only — external refs rejected)
    # ------------------------------------------------------------------
    def resolve_refs(self, spec_dict: dict, depth: int = 0) -> dict:
        """Resolve internal `$ref` pointers (#/components/schemas/X etc.).

        External (http/file) refs are rejected — they would reintroduce the
        SSRF surface. Cycles are capped by depth to prevent runaway recursion.
        """
        if depth > 20:
            raise OpenAPIParseError("$ref resolution exceeded max depth (possible cycle).")

        if isinstance(spec_dict, list):
            return [self.resolve_refs(item, depth + 1) for item in spec_dict]

        if not isinstance(spec_dict, dict):
            return spec_dict

        resolved = {}
        for key, value in spec_dict.items():
            if key == "$ref" and isinstance(value, str):
                if value.startswith("http://") or value.startswith("https://") or value.startswith("file:"):
                    raise OpenAPIParseError("External $ref values are not allowed (SSRF protection).")
                if not value.startswith("#/"):
                    raise OpenAPIParseError(f"Unsupported $ref: {value}")
                target = self._resolve_pointer(spec_dict, value.lstrip("#/"))
                if target is None:
                    raise OpenAPIParseError(f"Unresolvable $ref: {value}")
                return self.resolve_refs(target, depth + 1)
            resolved[key] = self.resolve_refs(value, depth + 1)
        return resolved

    @staticmethod
    def _resolve_pointer(document: dict, pointer: str) -> Any:
        """Resolve a JSON-pointer path against the document root."""
        current = document
        for part in pointer.split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                return None
        return current

    # ------------------------------------------------------------------
    # Normalize + analyze
    # ------------------------------------------------------------------
    def normalize(self, resolved_spec: dict) -> List[NormalizedOperation]:
        operations = []
        paths = resolved_spec.get("paths", {})
        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, details in methods.items():
                if method.lower() not in ("get", "post", "put", "delete", "patch", "options", "head"):
                    continue
                op_id = details.get("operationId", f"{method}_{path}")
                operations.append(
                    NormalizedOperation(
                        operation_id=op_id,
                        path=path,
                        method=method.upper(),
                        summary=details.get("summary"),
                        parameters=details.get("parameters", []),
                        request_body=details.get("requestBody"),
                        responses=details.get("responses", {}),
                        security=details.get("security", []),
                        tags=details.get("tags", []),
                    )
                )
        return operations

    def analyze(self, spec_dict: dict, normalized_ops: List[NormalizedOperation]) -> dict:
        info = spec_dict.get("info", {})
        version = self.detect_version(spec_dict)

        schema_count = 0
        if "components" in spec_dict and "schemas" in spec_dict["components"]:
            schema_count = len(spec_dict["components"]["schemas"])
        elif "definitions" in spec_dict:  # Swagger 2.0
            schema_count = len(spec_dict["definitions"])

        return {
            "success": True,
            "title": info.get("title", "Unknown API"),
            "api_version": info.get("version", "Unknown"),
            "spec_version": version,
            "operation_count": len(normalized_ops),
            "schema_count": schema_count,
        }

    def process_and_validate(self, content: str = None, url: str = None, auth_headers: dict = None) -> dict:
        try:
            if url:
                content = self.fetch_from_url(url, auth_headers)
            if not content:
                raise OpenAPIParseError("No specification content provided.")

            spec_dict = self.parse_content(content)
            self.detect_version(spec_dict)
            self.validate_spec(spec_dict)

            resolved = self.resolve_refs(spec_dict)
            normalized_ops = self.normalize(resolved)

            return self.analyze(resolved, normalized_ops)
        except (OpenAPISecurityError, OpenAPIParseError) as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            return {"success": False, "error": f"An unexpected error occurred: {exc}"}
