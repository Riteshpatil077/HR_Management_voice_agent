# ADR 003: Event-Driven Autoscaling with KEDA

## Status
Accepted

## Context
The platform must handle bursty workloads, specifically the asynchronous processing of call transcripts and analytics via the `AnalyticsService` and asynchronous webhook processing in the `VoiceService`. 

Standard Kubernetes Horizontal Pod Autoscaler (HPA) relies on CPU/Memory metrics. CPU utilization is a lagging indicator for message queues; a massive influx of RabbitMQ messages might not spike CPU immediately if pods are processing slowly, resulting in unacceptable queue depth and processing latency.

## Decision
We will use **KEDA (Kubernetes Event-driven Autoscaling)** instead of the standard HPA for asynchronous workers.

We have deployed `ScaledObject` resources that connect directly to RabbitMQ using TriggerAuthentications referencing Vault-provisioned credentials.

## Consequences

### Positive
- **Proactive Scaling**: Pods scale up immediately based on the RabbitMQ queue length (e.g., scale 1 pod per 10 pending messages).
- **Scale to Zero**: For non-critical background tasks during off-peak hours, KEDA allows us to scale deployments down to zero replicas, saving compute costs.
- **Graceful Scale Down**: KEDA allows configuring scale-down stabilization windows to prevent thrashing.

### Negative
- **Operational Complexity**: Adds another component (KEDA operator) to the cluster that must be monitored and maintained.
