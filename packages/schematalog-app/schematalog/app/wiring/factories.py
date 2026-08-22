"""FastAPI dependencies over the composed application."""

from fastapi import Request

from schematalog.app.application.schema import SchemaService


def get_service(request: Request) -> SchemaService:
    """FastAPI dependency returning a `SchemaService` over the app's schema repository."""
    return SchemaService(request.app.state.schemas)
