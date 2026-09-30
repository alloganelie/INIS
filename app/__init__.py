import defusedxml

defusedxml.defuse_stdlib()

# The XML hardening below must be active before any application module is
# imported; the ``.env`` bootstrap comes with it so that every entry point
# (uvicorn, Alembic, scripts, pytest) sees the same development configuration.
from app.core.env import bootstrap_environment

bootstrap_environment()

