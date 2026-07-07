# ADR 001: Clean Architecture & Domain-Driven Design

## Status
Accepted

## Context
The HR Voice Agent platform involves complex business logic across multiple bounded contexts (Voice processing, HR management, Interviews, Onboarding, Analytics). We need a structural pattern that:
1. Isolates business rules from external frameworks (FastAPI, SQLAlchemy).
2. Makes the codebase highly testable without spinning up databases.
3. Allows replacing infrastructure components (e.g., swapping OpenAI for Anthropic) without touching domain logic.

## Decision
We will strictly adopt **Clean Architecture** (Ports and Adapters) combined with **Domain-Driven Design (DDD)**.

The codebase for each microservice will be structured as follows:
- `domain/`: Contains pure Python objects (Entities, Value Objects, Aggregates) and domain exceptions. No external dependencies allowed.
- `application/`: Contains Use Cases (Commands/Queries) that orchestrate domain logic using Interfaces (Ports).
- `infrastructure/`: Contains Concrete Implementations (Adapters) for databases (SQLAlchemy Repositories), external APIs, and message brokers.
- `api/`: Contains FastAPI routers, dependency injection, and HTTP presentation logic.

## Consequences

### Positive
- **Testability**: Use cases can be tested in milliseconds using in-memory repositories.
- **Maintainability**: Clear boundaries prevent "Big Ball of Mud" architectures.
- **Flexibility**: We successfully implemented the `IntegrationFactory` which hot-swaps LLM/TTS providers purely via infrastructure adapters, keeping the core voice pipeline ignorant of the provider specifics.

### Negative
- **Boilerplate**: Higher initial overhead. Developers must map between Domain Models and SQLAlchemy ORM models, and between HTTP Pydantic models and Domain Models.
- **Learning Curve**: Requires developers to understand DDD aggregates and inversion of control.
