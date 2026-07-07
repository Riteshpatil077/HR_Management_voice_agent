# ADR 002: Transactional Outbox Pattern

## Status
Accepted

## Context
In our microservice architecture, services often need to update their local database and publish a domain event to a message broker (RabbitMQ) simultaneously. For example, the `InterviewService` creates an interview record and publishes an `InterviewScheduled` event.

Using a dual-write approach (write to DB, then publish to RabbitMQ) is flawed because if the broker is down, the DB commits but the event is lost, leading to system inconsistency.

## Decision
We will implement the **Transactional Outbox Pattern**.

1. Every microservice database will contain an `outbox_events` table.
2. The `UnitOfWork` (UoW) intercepts all emitted domain events during a transaction.
3. When the UoW commits, it saves the business entities AND the serialized domain events into the `outbox_events` table in a single atomic database transaction.
4. An async background worker (`OutboxRelayWorker`), running within the FastAPI lifecycle of each service, continuously polls the `outbox_events` table.
5. The worker publishes the events to RabbitMQ and marks them as processed in the database.

## Consequences

### Positive
- **Guaranteed At-Least-Once Delivery**: No events are lost if RabbitMQ crashes or network partitions occur.
- **Consistency**: The business state and event state are always perfectly aligned.

### Negative
- **Latency**: There is a slight delay (polling interval) between the transaction committing and the event hitting the broker.
- **Idempotency Requirement**: Because the outbox guarantees at-least-once delivery, consumers MUST be implemented idempotently (which we handle via the `IdempotencyStore`).
