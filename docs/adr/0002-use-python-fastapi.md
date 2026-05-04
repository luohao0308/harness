# ADR 0002: Use Python 3.11 And FastAPI

## Status

accepted

## Context

The platform is Python-native and requires async APIs, type validation, OpenAPI generation, SSE endpoints, metrics integration and strong ecosystem support.

## Decision

The backend uses Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0 and Alembic.

## Consequences

- API contracts are generated through FastAPI.
- Pydantic models define request and response schemas.
- SQLAlchemy models define database ownership.
- Alembic owns schema migrations.

