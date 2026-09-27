# Changelog

All notable changes to monero-farm. Dates are UTC.

## [2026-09-27] — Unreleased

### Changed
- **Mining stack is OFF by default, durably** (task-18040). P2Pool (all
  configured sidechains), monerod, and both P2Pool exporters are now driven by
  explicit flags that default to disabled: `p2pool_run_enabled`, `monerod_run_enabled`,
  and `exporters_run_enabled`. XMRig no longer autostarts: `xmrig_autostart` now
  defaults to `false`.

  Authority: operator instruction to shut down P2Pool, disable the node, and
  stop the miners. The live shutdown was performed separately; this change makes
  it survive IaC application.

  A disabled service is **enforced into `stopped` + `disabled` on every run**
  rather than skipped, so a later playbook run cannot re-enable what was
  deliberately taken down. This is the property that makes the shutdown durable.

  Binaries, systemd units, configuration and chain data are still deployed.
  Nothing is deleted, and the change is fully reversible.

### Added
- `ansible/group_vars/all/mining_shutdown.yml` — the tracked, commented
  statement of the operator state, with the explicit re-enable command.
