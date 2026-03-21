#!/usr/bin/env python3
import argparse
import json
import logging
import os
import re
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from prometheus_client import REGISTRY, start_http_server
from prometheus_client.core import GaugeMetricFamily


LOG = logging.getLogger("monero_p2pool_exporter")


class MoneroRPC:
    """
    Small helper around monerod's RPC interface.

    Supports both /json_rpc (JSON-RPC 2.0) and selected "other" HTTP endpoints.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 5.0,
        username: Optional[str] = None,
        password: Optional[str] = None,
        digest_auth: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.json_rpc_url = self.base_url + "/json_rpc"
        self.timeout = timeout
        self.session = requests.Session()
        if username and password:
            if digest_auth:
                self.auth = HTTPDigestAuth(username, password)
            else:
                self.auth = HTTPBasicAuth(username, password)
        else:
            self.auth = None

    def call(self, method: str, params: Optional[Any] = None) -> Dict[str, Any]:
        """
        Call a JSON-RPC method and return the "result" object (or {}).

        Raises requests.HTTPError / RuntimeError on hard failure.
        """
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": "0",
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        LOG.debug("monerod JSON-RPC call %s(%s)", method, params)
        resp = self.session.post(
            self.json_rpc_url,
            json=payload,
            timeout=self.timeout,
            auth=self.auth,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data and data["error"]:
            raise RuntimeError(f"monerod RPC error on {method}: {data['error']}")
        return data.get("result") or {}

    def post_other(self, endpoint: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Call a non-JSON-RPC endpoint like /get_transaction_pool_stats.

        Uses POST with a JSON body (possibly empty), as in the examples in the docs.
        """
        url = self.base_url + endpoint
        LOG.debug("monerod HTTP RPC POST %s payload=%s", url, payload)
        resp = self.session.post(
            url,
            json=payload or {},
            timeout=self.timeout,
            auth=self.auth,
        )
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            LOG.warning("Non-JSON response from %s", url)
            return {}


class MetricStore:
    """
    Small helper to deduplicate GaugeMetricFamily instances by (name, labelnames).
    """

    def __init__(self) -> None:
        self._metrics: Dict[Tuple[str, Tuple[str, ...]], GaugeMetricFamily] = {}

    def gauge(self, name: str, help_text: str, labelnames: Optional[List[str]] = None) -> GaugeMetricFamily:
        if labelnames is None:
            labelnames = []
        key = (name, tuple(labelnames))
        metric = self._metrics.get(key)
        if metric is None:
            metric = GaugeMetricFamily(name, help_text, labels=labelnames)
            self._metrics[key] = metric
        return metric

    def all(self) -> Iterable[GaugeMetricFamily]:
        return self._metrics.values()


def _to_number(value: Any) -> Optional[float]:
    """
    Convert an int/float/bool or hex string (0x...) to a float for Prometheus.
    """
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        v = value.strip()
        if v.startswith(("0x", "0X")):
            try:
                return float(int(v, 16))
            except ValueError:
                return None
        # don't try to parse decimal strings generically
    return None


class MoneroP2PoolCollector:
    """
    Prometheus collector that scrapes:

      * monerod via JSON-RPC (/json_rpc) and selected HTTP RPC endpoints
      * P2Pool JSON API files under api-mini/ and api-main/
    """

    _p2pool_name_re = re.compile(r"[^a-zA-Z0-9_]")

    def __init__(
        self,
        monero_rpc: MoneroRPC,
        p2pool_mini_dir: str = "/opt/p2pool/api-mini",
        p2pool_main_dir: str = "/opt/p2pool/api-main",
    ) -> None:
        self.rpc = monero_rpc
        self.p2pool_mini_dir = p2pool_mini_dir
        self.p2pool_main_dir = p2pool_main_dir

    # -----------------------
    # Prometheus entry point
    # -----------------------

    def collect(self) -> Iterable[GaugeMetricFamily]:
        store = MetricStore()

        # Monero metrics
        self._collect_monero_metrics(store)

        # P2Pool metrics from JSON files
        self._collect_p2pool_tree("mini", self.p2pool_mini_dir, store)
        self._collect_p2pool_tree("main", self.p2pool_main_dir, store)

        yield from store.all()

    # ------------------
    # Monero collection
    # ------------------

    def _safe_call(self, method: str, params: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        try:
            return self.rpc.call(method, params=params)
        except Exception as e:
            LOG.warning("RPC %s failed: %s", method, e)
            return None

    def _collect_monero_metrics(self, store: MetricStore) -> None:
        # "up" metric for JSON-RPC basic health
        up_metric = store.gauge(
            "monero_rpc_up",
            "Whether the Monero JSON-RPC endpoint is reachable (1) or not (0)",
        )

        info = None
        try:
            info = self.rpc.call("get_info")
            up_metric.add_metric([], 1.0)
        except Exception as e:
            LOG.error("Failed to call monerod get_info: %s", e)
            up_metric.add_metric([], 0.0)
            return

        # --- get_info base metrics ---
        self._map_get_info(info, store)

        # --- get_last_block_header ---
        last_header = self._safe_call("get_last_block_header")
        if last_header and isinstance(last_header.get("block_header"), dict):
            self._map_block_header(
                last_header["block_header"],
                store,
                metric_prefix="monero_last_block_",
            )

        # --- get_block_count ---
        block_count = self._safe_call("get_block_count")
        if block_count:
            val = _to_number(block_count.get("count"))
            if val is not None:
                store.gauge(
                    "monero_blockchain_height",
                    "Number of blocks in the longest chain known to this node",
                ).add_metric([], val)

        # --- sync_info ---
        sync_info = self._safe_call("sync_info")
        if sync_info:
            self._map_sync_info(sync_info, store)

        # --- get_version ---
        version = self._safe_call("get_version")
        if version:
            v = _to_number(version.get("version"))
            if v is not None:
                store.gauge(
                    "monero_daemon_version",
                    "Monerod version as an integer",
                ).add_metric([], v)
            is_release = version.get("release")
            if isinstance(is_release, bool):
                store.gauge(
                    "monero_daemon_release",
                    "Whether this daemon is a release build (1) or not (0)",
                ).add_metric([], 1.0 if is_release else 0.0)

        # --- hard_fork_info ---
        hf = self._safe_call("hard_fork_info")
        if hf:
            self._map_hard_fork_info(hf, store)

        # --- get_fee_estimate ---
        fee_est = self._safe_call("get_fee_estimate")
        if fee_est:
            self._map_fee_estimate(fee_est, store)

        # --- get_transaction_pool_stats (replaces get_txpool_backlog which returns binary) ---
        try:
            pool_stats = self.rpc.post_other("/get_transaction_pool_stats")
            if pool_stats:
                self._map_pool_stats(pool_stats, store)
        except Exception as e:
            LOG.warning("get_transaction_pool_stats failed: %s", e)

        # --- get_miner_data ---
        miner_data = self._safe_call("get_miner_data")
        if miner_data:
            self._map_miner_data(miner_data, store)

        # --- get_alternate_chains ---
        alt = self._safe_call("get_alternate_chains")
        if alt:
            self._map_alternate_chains(alt, store)

        # --- get_connections ---
        connections = self._safe_call("get_connections")
        if connections:
            self._map_connections(connections, store)

        # --- get_bans ---
        bans = self._safe_call("get_bans")
        if bans:
            self._map_bans(bans, store)

        # --- HTTP "Other RPC methods" that are useful for metrics ---

        # /get_transaction_pool_stats
        try:
            txpool_stats = self.rpc.post_other("/get_transaction_pool_stats")
            self._map_txpool_stats(txpool_stats, store)
        except Exception as e:
            LOG.warning("/get_transaction_pool_stats failed: %s", e)

        # /get_net_stats
        try:
            net_stats = self.rpc.post_other("/get_net_stats")
            self._map_net_stats(net_stats, store)
        except Exception as e:
            LOG.warning("/get_net_stats failed: %s", e)

        # /get_limit
        try:
            limit = self.rpc.post_other("/get_limit")
            self._map_limit(limit, store)
        except Exception as e:
            LOG.warning("/get_limit failed: %s", e)

    def _map_get_info(self, info: Dict[str, Any], store: MetricStore) -> None:
        """
        Map get_info result to a set of monero_* metrics.
        """
        height = _to_number(info.get("height"))
        if height is not None:
            store.gauge("monero_height", "Current block height of this node").add_metric([], height)

        target_height = _to_number(info.get("target_height"))
        if target_height is not None:
            store.gauge("monero_target_height", "Target height this node is syncing towards").add_metric([], target_height)

        difficulty = _to_number(info.get("difficulty"))
        if difficulty is not None:
            store.gauge("monero_difficulty", "Current network difficulty (LSB 64 bits)").add_metric([], difficulty)

        tx_count = _to_number(info.get("tx_count"))
        if tx_count is not None:
            store.gauge("monero_tx_count", "Total number of transactions in the blockchain").add_metric([], tx_count)

        tx_pool_size = _to_number(info.get("tx_pool_size"))
        if tx_pool_size is not None:
            store.gauge("monero_tx_pool_size", "Number of transactions in the mempool").add_metric([], tx_pool_size)

        db_size = _to_number(info.get("database_size"))
        if db_size is not None:
            store.gauge("monero_database_size_bytes", "Size of the blockchain database on disk in bytes").add_metric([], db_size)

        free_space = _to_number(info.get("free_space"))
        if free_space is not None:
            store.gauge("monero_free_space_bytes", "Free disk space available in the blockchain data directory").add_metric([], free_space)

        incoming = _to_number(info.get("incoming_connections_count"))
        if incoming is not None:
            store.gauge("monero_incoming_connections", "Number of incoming P2P connections").add_metric([], incoming)

        outgoing = _to_number(info.get("outgoing_connections_count"))
        if outgoing is not None:
            store.gauge("monero_outgoing_connections", "Number of outgoing P2P connections").add_metric([], outgoing)

        alt_blocks = _to_number(info.get("alt_blocks_count"))
        if alt_blocks is not None:
            store.gauge("monero_alt_blocks_count", "Number of known alternate (fork) blocks").add_metric([], alt_blocks)

        white_peers = _to_number(info.get("white_peerlist_size"))
        if white_peers is not None:
            store.gauge("monero_white_peerlist_size", "Size of white peer list").add_metric([], white_peers)

        grey_peers = _to_number(info.get("grey_peerlist_size"))
        if grey_peers is not None:
            store.gauge("monero_grey_peerlist_size", "Size of grey peer list").add_metric([], grey_peers)

        for key, metric_name in [
            ("synchronized", "monero_synchronized"),
            ("busy_syncing", "monero_busy_syncing"),
            ("offline", "monero_offline"),
            ("restricted", "monero_restricted_rpc"),
            ("testnet", "monero_testnet"),
            ("stagenet", "monero_stagenet"),
        ]:
            val = info.get(key)
            if isinstance(val, bool):
                store.gauge(
                    metric_name,
                    f"{key.replace('_', ' ').capitalize()} flag from get_info",
                ).add_metric([], 1.0 if val else 0.0)

    def _map_block_header(self, header: Dict[str, Any], store: MetricStore, metric_prefix: str) -> None:
        """
        Map a block_header structure (from get_last_block_header or similar) to metrics.
        """
        fields = {
            "height": "Block height",
            "difficulty": "Block difficulty (LSB 64 bits)",
            "cumulative_difficulty": "Cumulative difficulty up to this block",
            "reward": "Coinbase reward for this block (atomic units)",
            "block_weight": "Block weight",
            "block_size": "Block size in bytes",
            "num_txes": "Number of non-coinbase txes in this block",
            "timestamp": "Block timestamp (UNIX epoch)",
        }
        for key, help_text in fields.items():
            val = _to_number(header.get(key))
            if val is not None:
                store.gauge(metric_prefix + key, help_text).add_metric([], val)

        orphan = header.get("orphan_status")
        if isinstance(orphan, bool):
            store.gauge(
                metric_prefix + "orphan_status",
                "Whether the block is considered orphan (1) or not (0)",
            ).add_metric([], 1.0 if orphan else 0.0)

    def _map_sync_info(self, sync_info: Dict[str, Any], store: MetricStore) -> None:
        """
        Map sync_info result into aggregate metrics.
        """
        height = _to_number(sync_info.get("height"))
        if height is not None:
            store.gauge("monero_sync_height", "Height reported by sync_info").add_metric([], height)

        target = _to_number(sync_info.get("target_height"))
        if target is not None:
            store.gauge("monero_sync_target_height", "Target height reported by sync_info").add_metric([], target)

        peers = sync_info.get("peers")
        if isinstance(peers, list):
            store.gauge("monero_sync_peers", "Number of peers in sync_info").add_metric([], float(len(peers)))

        spans = sync_info.get("spans")
        if isinstance(spans, list):
            store.gauge("monero_sync_spans", "Number of spans in sync_info").add_metric([], float(len(spans)))

    def _map_hard_fork_info(self, hf: Dict[str, Any], store: MetricStore) -> None:
        """
        Map hard_fork_info result to metrics.
        """
        for key in ["earliest_height", "state", "threshold", "version", "votes", "voting", "window"]:
            val = _to_number(hf.get(key))
            if val is not None:
                store.gauge(f"monero_hard_fork_{key}", f"hard_fork_info field {key}").add_metric([], val)

        enabled = hf.get("enabled")
        if isinstance(enabled, bool):
            store.gauge(
                "monero_hard_fork_enabled",
                "Whether the current hard fork is enabled",
            ).add_metric([], 1.0 if enabled else 0.0)

    def _map_fee_estimate(self, fee_est: Dict[str, Any], store: MetricStore) -> None:
        """
        Map get_fee_estimate result to metrics.
        """
        fee = _to_number(fee_est.get("fee"))
        if fee is not None:
            store.gauge(
                "monero_fee_estimate",
                "Base fee estimate in atomic units per kB/byte (see docs)",
            ).add_metric([], fee)

        # Some nodes return fee estimates per priority in a 'fees' array.
        fees = fee_est.get("fees")
        if isinstance(fees, list):
            metric = store.gauge(
                "monero_fee_estimate_tier",
                "Fee estimate per priority tier (index-based, not wallet priority)",
                ["tier"],
            )
            for idx, f in enumerate(fees):
                v = _to_number(f)
                if v is not None:
                    metric.add_metric([str(idx)], v)

    def _map_pool_stats(self, data: Dict[str, Any], store: MetricStore) -> None:
        """
        Map /get_transaction_pool_stats result to metrics.
        Replaces _map_txpool_backlog which broke on binary data in get_txpool_backlog.
        """
        ps = data.get("pool_stats")
        if not isinstance(ps, dict):
            return

        num_txes = _to_number(ps.get("txs_total"))
        if num_txes is not None:
            store.gauge(
                "monero_txpool_backlog_txs",
                "Number of transactions in txpool",
            ).add_metric([], num_txes)

        fee_total = _to_number(ps.get("fee_total"))
        if fee_total is not None:
            store.gauge(
                "monero_txpool_backlog_total_fee",
                "Total fee of transactions in txpool (atomic units)",
            ).add_metric([], fee_total)

        bytes_total = _to_number(ps.get("bytes_total"))
        if bytes_total is not None:
            store.gauge(
                "monero_txpool_backlog_total_weight",
                "Total size of transactions in txpool (bytes)",
            ).add_metric([], bytes_total)

    def _map_miner_data(self, miner_data: Dict[str, Any], store: MetricStore) -> None:
        """
        Map get_miner_data result to metrics.
        """
        fields = {
            "height": "Height returned by get_miner_data",
            "difficulty": "Network difficulty from get_miner_data (may be hex string)",
            "median_weight": "Median block weight",
            "already_generated_coins": "Total coins generated (atomic units)",
        }
        for key, help_text in fields.items():
            val = _to_number(miner_data.get(key))
            if val is not None:
                store.gauge(f"monero_miner_{key}", help_text).add_metric([], val)

        tx_backlog = miner_data.get("tx_backlog")
        if isinstance(tx_backlog, list):
            store.gauge(
                "monero_miner_tx_backlog_txs",
                "Number of transactions in miner_data.tx_backlog",
            ).add_metric([], float(len(tx_backlog)))

    def _map_alternate_chains(self, alt: Dict[str, Any], store: MetricStore) -> None:
        """
        Map get_alternate_chains result to metrics.
        """
        chains = alt.get("chains")
        if isinstance(chains, list):
            store.gauge(
                "monero_alternate_chains",
                "Number of alternate chains",
            ).add_metric([], float(len(chains)))

    def _map_connections(self, connections: Dict[str, Any], store: MetricStore) -> None:
        """
        Map get_connections result to aggregate metrics.
        """
        conns = connections.get("connections")
        if not isinstance(conns, list):
            return

        total = len(conns)
        incoming = 0
        by_state: Dict[str, int] = {}

        for c in conns:
            if not isinstance(c, dict):
                continue
            if c.get("incoming"):
                incoming += 1
            state = c.get("state")
            if isinstance(state, str):
                by_state[state] = by_state.get(state, 0) + 1

        store.gauge(
            "monero_connections",
            "Total number of P2P connections (get_connections)",
        ).add_metric([], float(total))
        store.gauge(
            "monero_connections_incoming",
            "Incoming P2P connections (get_connections)",
        ).add_metric([], float(incoming))
        store.gauge(
            "monero_connections_outgoing",
            "Outgoing P2P connections (get_connections)",
        ).add_metric([], float(total - incoming))

        if by_state:
            metric = store.gauge(
                "monero_connections_state",
                "Number of P2P connections by state (get_connections)",
                ["state"],
            )
            for state, count in by_state.items():
                metric.add_metric([state], float(count))

    def _map_bans(self, bans: Dict[str, Any], store: MetricStore) -> None:
        """
        Map get_bans result to metrics.
        """
        entries = bans.get("bans")
        if not isinstance(entries, list):
            return

        total = len(entries)
        banned_count = 0
        max_seconds = 0.0

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("banned"):
                banned_count += 1
            secs = _to_number(entry.get("seconds"))
            if secs is not None and secs > max_seconds:
                max_seconds = secs

        store.gauge("monero_bans_total", "Number of ban entries").add_metric([], float(total))
        store.gauge("monero_bans_active", "Number of active bans (banned=true)").add_metric([], float(banned_count))
        store.gauge("monero_bans_max_seconds", "Maximum remaining ban seconds among bans").add_metric([], max_seconds)

    def _map_txpool_stats(self, txpool_stats: Dict[str, Any], store: MetricStore) -> None:
        """
        Map /get_transaction_pool_stats result.
        """
        pool = txpool_stats.get("pool_stats")
        if not isinstance(pool, dict):
            return

        mapping = {
            "bytes_total": "Total size in bytes of all transactions in the mempool",
            "bytes_max": "Maximum allowed mempool size in bytes",
            "txs_total": "Number of transactions in the mempool",
            "txs_max": "Maximum allowed number of transactions in the mempool",
        }
        for key, help_text in mapping.items():
            val = _to_number(pool.get(key))
            if val is not None:
                store.gauge(f"monero_txpool_{key}", help_text).add_metric([], val)

    def _map_net_stats(self, net_stats: Dict[str, Any], store: MetricStore) -> None:
        """
        Map /get_net_stats result.
        """
        mapping = {
            "start_time": "Time when these net stats started to be collected (UNIX epoch)",
            "total_bytes_in": "Total bytes received by this node (since start_time)",
            "total_bytes_out": "Total bytes sent by this node (since start_time)",
        }
        for key, help_text in mapping.items():
            val = _to_number(net_stats.get(key))
            if val is not None:
                store.gauge(f"monero_net_{key}", help_text).add_metric([], val)

    def _map_limit(self, limit: Dict[str, Any], store: MetricStore) -> None:
        """
        Map /get_limit result.
        """
        down = _to_number(limit.get("limit_down"))
        up = _to_number(limit.get("limit_up"))
        if down is not None:
            store.gauge("monero_limit_down_kbps", "Download bandwidth limit (kB/s)").add_metric([], down)
        if up is not None:
            store.gauge("monero_limit_up_kbps", "Upload bandwidth limit (kB/s)").add_metric([], up)

    # ------------------
    # P2Pool collection
    # ------------------

    def _sanitize_p2pool_name(self, key_path: str) -> str:
        """
        Convert a P2Pool key path like 'local/p2p_connections'
        into a Prometheus-safe metric name 'p2pool_local_p2p_connections'.
        """
        name = (
            key_path
            .replace(os.sep, "_")
            .replace("/", "_")
            .replace("-", "_")
            .replace(".", "_")
        )
        name = self._p2pool_name_re.sub("_", name)
        name = re.sub(r"_+", "_", name).strip("_")
        if not name:
            name = "value"
        if not (name[0].isalpha() or name[0] == "_"):
            name = f"v_{name}"
        return f"p2pool_{name.lower()}"

    def _flatten_p2pool_json(self, prefix: str, obj: Any) -> Dict[str, Any]:
        """
        Flatten a JSON-like structure into key_path -> value.

        - prefix is usually the relative file path without extension (e.g. 'local/p2p')
        - dict keys are appended with '_' to prefix
        - lists are ignored (to avoid exploding metric cardinality)
        """
        out: Dict[str, Any] = {}

        def _walk(pfx: str, val: Any):
            if isinstance(val, dict):
                for k, v in val.items():
                    key = f"{pfx}_{k}" if pfx else str(k)
                    _walk(key, v)
            elif isinstance(val, (int, float, bool, str)):
                # value will be run through _to_number() later
                if pfx:
                    out[pfx] = val
            elif isinstance(val, list):
                # intentionally ignore lists for now
                return
            else:
                return

        _walk(prefix, obj)
        return out

    def _collect_p2pool_tree(self, chain: str, root_dir: str, store: MetricStore) -> None:
        """
        Walk all files under root_dir (mini/main data-api tree), try to parse them as JSON,
        and export numeric fields as Prometheus metrics.

        Metric naming matches your previous exporter:

            p2pool_<sanitized_path>{chain="mini|main"}

        Example:
            /opt/p2pool/api-mini/local/stratum  ->
            key_path 'local/stratum_hashrate_15m' ->
            metric 'p2pool_local_stratum_hashrate_15m{chain="mini"}'
        """
        if not root_dir or not os.path.isdir(root_dir):
            LOG.debug("P2Pool %s directory %s does not exist, skipping", chain, root_dir)
            return

        now = time.time()

        for dirpath, _, filenames in os.walk(root_dir):
            for fname in filenames:
                # IMPORTANT: do NOT filter on .json; P2Pool uses files like 'stats', 'stratum', 'p2p'
                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(full_path, root_dir)

                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    LOG.debug("Skipping non-JSON or unreadable file %s: %s", full_path, e)
                    continue

                base = os.path.splitext(rel_path)[0]  # e.g. 'pool/stats', 'local/stratum'
                flat = self._flatten_p2pool_json(base, data)

                for key_path, raw_value in flat.items():
                    value = _to_number(raw_value)
                    if value is None:
                        continue

                    metric_name = self._sanitize_p2pool_name(key_path)
                    metric = store.gauge(
                        metric_name,
                        f"P2Pool metric from {rel_path}, field {key_path}",
                        ["chain"],
                    )
                    metric.add_metric([chain], value)

                    # auto-generate *_age_seconds for timestamp-ish fields
                    lower_name = metric_name.lower()
                    if not (lower_name.endswith("_time") or lower_name.endswith("_timestamp")):
                        continue
                    if not (1e9 < value < 4e9):  # rough unix time sanity check
                        continue

                    base_name = metric_name
                    for suffix in ("_time", "_timestamp"):
                        if base_name.endswith(suffix):
                            base_name = base_name[: -len(suffix)]
                            break

                    age_metric_name = f"{base_name}_age_seconds"
                    age_metric = store.gauge(
                        age_metric_name,
                        f"Age in seconds since {key_path}",
                        ["chain"],
                    )
                    age_metric.add_metric([chain], max(0.0, now - value))


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prometheus exporter for Monero + P2Pool")
    parser.add_argument(
        "--listen-address",
        default="127.0.0.1",
        help="Address to listen on (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=18096,
        help="Port to listen on for /metrics (default: 18096)",
    )
    parser.add_argument(
        "--monero-rpc-url",
        default="http://127.0.0.1:18081",
        help="Base URL for monerod RPC (default: http://127.0.0.1:18081)",
    )
    parser.add_argument(
        "--monero-rpc-username",
        default=None,
        help="Username for monerod RPC (if --rpc-login is enabled)",
    )
    parser.add_argument(
        "--monero-rpc-password",
        default=None,
        help="Password for monerod RPC (if --rpc-login is enabled)",
    )
    parser.add_argument(
        "--monero-rpc-no-digest",
        action="store_true",
        help="Use HTTP basic auth instead of digest (default: digest if credentials are given)",
    )
    parser.add_argument(
        "--p2pool-mini-dir",
        default="/opt/p2pool/api-mini",
        help="Path to P2Pool mini JSON API directory (default: /opt/p2pool/api-mini)",
    )
    parser.add_argument(
        "--p2pool-main-dir",
        default="/opt/p2pool/api-main",
        help="Path to P2Pool main JSON API directory (default: /opt/p2pool/api-main)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING...)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    rpc = MoneroRPC(
        base_url=args.monero_rpc_url,
        timeout=5.0,
        username=args.monero_rpc_username,
        password=args.monero_rpc_password,
        digest_auth=not args.monero_rpc_no_digest,
    )

    collector = MoneroP2PoolCollector(
        monero_rpc=rpc,
        p2pool_mini_dir=args.p2pool_mini_dir,
        p2pool_main_dir=args.p2pool_main_dir,
    )
    REGISTRY.register(collector)

    LOG.info("Starting exporter on %s:%d", args.listen_address, args.listen_port)
    start_http_server(port=args.listen_port, addr=args.listen_address)

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        LOG.info("Shutting down (KeyboardInterrupt)")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

