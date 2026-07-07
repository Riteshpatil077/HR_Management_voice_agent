# ADR 004: HashiCorp Vault for Secrets and PKI

## Status
Accepted

## Context
Enterprise security requirements mandate:
1. Strict rotation of application secrets (database passwords, LLM API keys).
2. Encryption of PII at rest (candidates' phone numbers, SSNs).
3. Zero-trust networking within the Kubernetes cluster (mTLS between all pods).
4. No long-lived static credentials anywhere in the CI/CD pipeline or cluster.

## Decision
We utilize **HashiCorp Vault** as the central security control plane, integrated via Kubernetes ServiceAccount (IRSA) authentication.

Specifically:
- **Vault PKI Engine**: Deployed as an internal Certificate Authority (Root + Intermediate). It automatically issues short-lived (72h) TLS certificates to the Kong API Gateway and microservices to enable strict mTLS.
- **Vault Transit Engine**: Used as Encryption-as-a-Service (EaaS). Microservices do not manage encryption keys; they send PII to the Vault Transit endpoint for encryption before writing to PostgreSQL, and for decryption upon reading.
- **Vault Database Engine**: Generates short-lived, dynamic PostgreSQL credentials for the microservices. If compromised, the credentials expire automatically.

## Consequences

### Positive
- **Security Posture**: Unparalleled enterprise security. Eliminates static secrets from ConfigMaps, GitHub Actions, and Git repositories.
- **Compliance**: Satisfies SOC2 and HIPAA requirements for PII encryption at rest and in transit.

### Negative
- **Dependency**: Vault becomes a strict Tier 0 dependency. If Vault is down, microservices cannot authenticate to the database or decrypt PII. We mitigated this by deploying Vault in a Highly Available (HA) raft cluster across 3 Availability Zones.
