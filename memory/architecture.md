# Monero Farm — Architecture Decisions

## AD-001: systemd over Docker Swarm
- **Decision**: All services managed by systemd, not Docker Swarm
- **Rationale**: Same as Ollama on GIGA — CPU affinity matters for RandomX, cgroup interference from Swarm hurts performance
- **Date**: 2026-03-05

## AD-002: XMRig HTTP API on port 8082
- **Decision**: Override default port 8080 → 8082
- **Rationale**: Port 8080 used by OpenWebUI on GIGA gateway. Avoids collision when monero-farm runs on same host.
- **Date**: 2026-03-05

## AD-003: P2Pool mini as default
- **Decision**: Start with P2Pool mini chain
- **Rationale**: Single-node fleet with consumer CPU; nano is too small for even modest hashrate, main requires >10 KH/s
- **Date**: 2026-03-05

## AD-004: Ansible fleet management
- **Decision**: Use Ansible for fleet provisioning and config management
- **Rationale**: Consistent with AI Server conventions; fleet may grow beyond single node
- **Date**: 2026-03-05

## AD-005: No shared services with Hydra AI stack
- **Decision**: Monero Farm does not use Ollama, ChromaDB, Redis, or Traefik
- **Rationale**: Mining is pure infrastructure — no AI inference or vector DB needed. Only future shared service is Prometheus (monitoring).
- **Date**: 2026-03-05
