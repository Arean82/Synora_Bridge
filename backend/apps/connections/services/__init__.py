"""
Connections domain services â€” Swagger/OpenAPI fetching and URL fixing.

Ports original `bridge_app/services/swagger_utils.py`:
- fetch_swagger_json: fetch a spec from a URL (HTML wrapper extraction supported)
- fix_swagger_urls: resolve relative server URLs against the source
"""
import re
from urllib.parse import urljoin, urlparse

import requests


def fix_swagger_urls(data, source_url):
    """Resolve relative server URLs in an OpenAPI/Swagger spec."""
    parsed = urlparse(source_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    if "servers" in data:
        for server in data["servers"]:
            if server.get("url", "").startswith("/"):
                server["url"] = base_url + server["url"]
    elif "host" not in data:
        data["host"] = parsed.netloc
        if "schemes" not in data:
            data["schemes"] = [parsed.scheme]

    if isinstance(data.get("info"), dict) and data["info"].get("description"):
        desc = data["info"]["description"]
        desc = re.sub(
            r"\[([^\]]+)\]\((/[^)]+)\)",
            lambda m: f"[{m.group(1)}]({base_url}{m.group(2)})",
            desc,
        )
        data["info"]["description"] = desc

    return data


def fetch_swagger_json(url, headers=None, timeout=10):
    """
    Fetch Swagger/OpenAPI JSON from a URL. If the URL returns HTML, attempt to
    extract the spec URL from it. Returns (json_data, actual_url).
    """
    resp = requests.get(url, headers=headers, timeout=timeout)
    if not resp.ok:
        raise ValueError(f"HTTP {resp.status_code}")

    try:
        data = resp.json()
        return fix_swagger_urls(data, url), url
    except ValueError:
        html = resp.text
        match = re.search(r'url:\s*["\']([^"\']+)["\']', html)
        if match:
            spec_url = match.group(1)
            if not spec_url.startswith("http"):
                spec_url = urljoin(url, spec_url)
            spec_resp = requests.get(spec_url, headers=headers, timeout=timeout)
            if not spec_resp.ok:
                raise ValueError(
                    f"Extracted JSON URL {spec_url} but got HTTP {spec_resp.status_code}"
                )
            try:
                data = spec_resp.json()
                return fix_swagger_urls(data, spec_url), spec_url
            except ValueError:
                pass
        raise ValueError(
            "URL does not return valid JSON and no Swagger URL could be extracted."
        )
