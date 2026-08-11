"""
GraphQL source service — querying and introspecting external GraphQL endpoints.

Ports original `bridge_app/services/graphql_service.py` fetch/introspect helpers.
The dynamic Strawberry schema generation lives in apps.pull (Phase 4).
"""
import requests


def fetch_from_graphql_source(url, query, auth_token=None):
    """Execute a GraphQL query against an external source; return data dict."""
    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    response = requests.post(url, json={"query": query}, headers=headers, timeout=15)
    response.raise_for_status()
    result = response.json()
    if "errors" in result:
        raise ValueError(f"GraphQL Source returned errors: {result['errors']}")
    return result.get("data", {})


INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    types { ...FullType }
  }
}
fragment FullType on __Type {
  kind
  name
  fields(includeDeprecated: true) {
    name
    args { ...InputValue }
    type { ...TypeRef }
  }
  inputFields { ...InputValue }
  interfaces { ...TypeRef }
  enumValues(includeDeprecated: true) { name }
  possibleTypes { ...TypeRef }
}
fragment InputValue on __InputValue {
  name
  type { ...TypeRef }
}
fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType {
        kind
        name
      }
    }
  }
}
"""


def introspect_graphql_endpoint(url, auth_token=None):
    """Fetch the introspection schema from an external GraphQL endpoint."""
    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    response = requests.post(
        url, json={"query": INTROSPECTION_QUERY}, headers=headers, timeout=15
    )
    response.raise_for_status()
    return response.json()
