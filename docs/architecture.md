# Monero Farm — Architecture

## Overview

Monero Farm (Hydra Head #2) is an XMR mining operation using P2Pool for
decentralized pool mining. All services run via systemd — not Docker Swarm.

## Service Topology

```
  Internet (P2P)
       │
       ▼
  ┌──────────┐     ┌──────────┐     ┌──────────┐
  │ monerod  │────▶│ p2pool   │────▶│ xmrig    │
  │ :18080   │ ZMQ │ :3333    │ str │ (CPU)    │
  │ :18081   │:18082│ :37888  │atum │ :8082 API│
  └──────────┘     └──────────┘     └──────────┘
  (full node)      (pool/sidechain)  (miner)

  All on same host or distributed via fleet (Ansible)
```

## Dependency Chain

monerod must sync → p2pool connects → xmrig mines via stratum.
`restart-all.sh` handles the correct order: stop xmrig → restart monerod → restart p2pool → start xmrig.

## P2Pool Mode Selection

| Fleet hashrate | Pool  | Flag       | P2P Port |
|----------------|-------|------------|----------|
| < 1 KH/s      | nano  | --nano     | 37887    |
| 1 – 10 KH/s   | mini  | --mini     | 37888    |
| > 10 KH/s     | main  | (default)  | 37889    |

## Disk Requirements

- monerod (pruned): ~80-120 GB (grows ~5 GB/month)
- P2Pool state: < 1 GB
- XMRig: negligible

## Security

- monerod RPC: 127.0.0.1 only (restricted)
- XMRig HTTP API: 127.0.0.1 only (port 8082)
- P2Pool stratum: 0.0.0.0 (miners need access)
- UFW rules managed by Ansible base role

## Initial Deploy Date
2026-03-16

## Detected State at Bootstrap
- monerod: running (PID 1803)
- p2pool: running (PID 1811)
- xmrig: not detected
- monerod systemd: true
- p2pool systemd: false
- xmrig systemd: false
- monero user: false
- miner user: false
