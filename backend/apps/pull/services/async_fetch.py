"""
Async source fetching — httpx-based concurrent fetch for pull endpoints.

Scale item #3: pull endpoints use asyncio + httpx so many upstream sources
are fetched concurrently per request without a thread pool. Fallback stays
synchronous (the Celery push path uses the thread-based fetch in tasks.py).
"""
import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


async def _fetch_one(client: httpx.AsyncClient, idx, src):
    src_url = src.get("url")
    if not src_url:
        return {}
    src_auth = src.get("auth_token")
    src_method = src.get("method", "GET").upper()
    source_type = src.get("source_type", "rest")

    local = {}
    try:
        if source_type == "graphql":
            query = src.get("graphql_query")
            headers = {"Content-Type": "application/json"}
            if src_auth:
                headers["Authorization"] = f"Bearer {src_auth}"
            res = await client.post(src_url, json={"query": query}, headers=headers, timeout=15)
            res.raise_for_status()
            result = res.json()
            if "errors" in result:
                logger.warning("GraphQL source %s returned errors: %s", src_url, result["errors"])
                return {}
            data = result.get("data", {})
        else:
            headers = {}
            if src_auth:
                headers["Authorization"] = f"Bearer {src_auth}"
            res = await client.request(src_method, src_url, headers=headers, timeout=15)
            if res.status_code != 200:
                logger.warning("Source %s (%s %s) returned %s", idx, src_method, src_url, res.status_code)
                return {}
            data = res.json()

        src_data = data[0] if isinstance(data, list) else data
        if isinstance(src_data, dict):
            for k, v in src_data.items():
                local[f"source_{idx}.{k}"] = v
    except Exception:
        logger.exception("Async fetch failed for source %s (%s)", idx, src_url)

    return local


async def _fetch_all_async(sources):
    async with httpx.AsyncClient(follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_fetch_one(client, idx, src) for idx, src in enumerate(sources)]
        )
    aggregated = {}
    for r in results:
        aggregated.update(r)
    return aggregated


def fetch_all_sources_async(sources):
    """Fetch all sources concurrently (async); returns flat aggregate dict."""
    if not sources:
        return {}
    return asyncio.run(_fetch_all_async(sources))
