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

### Fixed
- **The mining gate no longer fails every correctly-configured host, and no
  longer swallows shutdown errors** (task-18040, review REQUEST_CHANGES on
  PR #14). Two defects in the XMRig play's `pre_tasks`, both of which broke
  every host in `miners` / `cluster_miners`:

  1. The admission assert ran **unconditionally**, so a host with mining
     disabled — the intended state on every host — failed the play and was
     excluded from every Fleet Hardening play that followed. Hardening
     (security, sudoers, nfs_swarm) silently never ran on those hosts. The
     assert is now scoped to the install path only, and the clean-shutdown
     path completes normally.

  2. The shutdown convergence task carried `failed_when: false`, which hid
     real failures (permission denied, a unit that refuses to stop) behind a
     clean-looking run while the miner kept running. That suppression is
     removed: a real error now fails the play. Two guards were added so
     removing it does not turn the common cases into noise —
     a presence probe (`systemctl list-unit-files xmrig.service`) makes an
     absent unit a clean skip instead of a fatal, and a post-condition
     assertion reads `systemctl is-active xmrig` back and fails closed if the
     unit is still active under `mining_enabled: false`.

  Start authorization is unchanged: the load-bearing gate is still
  `when: mining_enabled` on the `xmrig` role, and nothing in the shutdown path
  can start a miner. No wallet address, key, or host name was added; this
  repository is public.

### Added
- `ansible/group_vars/all/mining_shutdown.yml` — the tracked, commented
  statement of the operator state, with the explicit re-enable command.
