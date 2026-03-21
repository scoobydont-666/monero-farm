# Monero Farm — Memory

## Key Facts
- Project: Hydra Head #2
- Location: /opt/monero-farm/
- Services: monerod (full node) + P2Pool (decentralized pool) + XMRig (CPU miner)
- Management: systemd (NOT Docker Swarm)
- P2Pool mode: mini (current — adjust based on fleet hashrate)
- XMRig HTTP API: port 8082 (NOT 8080)
- Blockchain data: /var/lib/monero (~200 GB headroom needed)

## Service Users
- monero: runs monerod and p2pool
- miner: runs xmrig

## Fleet
- 1 node deployed (update ansible/inventory/hosts.yml with your IPs)
- Add miners to ansible/inventory/hosts.yml

## Bootstrap Date
2026-03-16

## Wallet Address
TODO_YOUR_PRIMARY_ADDRESS — must be set before mining begins

## Tax Treatment
- Mining rewards: ordinary income at FMV on receipt (IRS Notice 2014-21)
- Cost basis: HIFO recommended
- Source of truth: monero-wallet-rpc get_transfers
