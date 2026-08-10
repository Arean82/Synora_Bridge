"""
Modular feature apps for Synora Bridge.

Each domain (core, configs, connections, jobs, pull, realtime, observability)
is a self-contained Django app owning its models, services, API routers, and
URLs. New features are added as new apps, not by growing existing ones.
"""
