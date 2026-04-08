"""Tests for unified_exporter.py — Monero + P2Pool Prometheus exporter."""

import json
import math
import os
from unittest.mock import MagicMock, patch

import pytest

from unified_exporter import (
    MetricStore,
    MoneroP2PoolCollector,
    MoneroRPC,
    _to_number,
    parse_args,
)


# ── _to_number() ──────────────────────────────────────────────────


class TestToNumber:
    def test_int(self):
        assert _to_number(42) == 42.0

    def test_float(self):
        assert _to_number(3.14) == 3.14

    def test_zero(self):
        assert _to_number(0) == 0.0

    def test_negative(self):
        assert _to_number(-100) == -100.0

    def test_bool_true(self):
        assert _to_number(True) == 1.0

    def test_bool_false(self):
        assert _to_number(False) == 0.0

    def test_hex_string(self):
        assert _to_number("0xFF") == 255.0

    def test_hex_string_upper(self):
        assert _to_number("0X1A") == 26.0

    def test_hex_invalid(self):
        assert _to_number("0xZZZZ") is None

    def test_regular_string_returns_none(self):
        assert _to_number("hello") is None

    def test_decimal_string_returns_none(self):
        # unified_exporter intentionally does NOT parse decimal strings
        assert _to_number("42") is None

    def test_none_returns_none(self):
        assert _to_number(None) is None

    def test_list_returns_none(self):
        assert _to_number([1, 2, 3]) is None

    def test_dict_returns_none(self):
        assert _to_number({"a": 1}) is None

    def test_hex_with_whitespace(self):
        assert _to_number("  0xff  ") == 255.0

    def test_large_int(self):
        assert _to_number(1234567890123456) == 1234567890123456.0


# ── MetricStore ───────────────────────────────────────────────────


class TestMetricStore:
    def test_creates_gauge(self):
        store = MetricStore()
        g = store.gauge("test_metric", "A test metric")
        assert g is not None
        assert g.name == "test_metric"

    def test_deduplicates_same_name(self):
        store = MetricStore()
        g1 = store.gauge("test_metric", "First call")
        g2 = store.gauge("test_metric", "Second call")
        assert g1 is g2

    def test_different_names_are_different(self):
        store = MetricStore()
        g1 = store.gauge("metric_a", "A")
        g2 = store.gauge("metric_b", "B")
        assert g1 is not g2

    def test_same_name_different_labels_are_different(self):
        store = MetricStore()
        g1 = store.gauge("metric", "No labels")
        g2 = store.gauge("metric", "With labels", ["chain"])
        assert g1 is not g2

    def test_all_returns_all_metrics(self):
        store = MetricStore()
        store.gauge("a", "A")
        store.gauge("b", "B")
        store.gauge("c", "C")
        all_metrics = list(store.all())
        assert len(all_metrics) == 3

    def test_empty_store(self):
        store = MetricStore()
        assert list(store.all()) == []

    def test_gauge_with_labels(self):
        store = MetricStore()
        g = store.gauge("labeled", "A labeled metric", ["host", "port"])
        g.add_metric(["giga", "11434"], 1.0)
        assert g is not None


# ── MoneroRPC ─────────────────────────────────────────────────────


class TestMoneroRPC:
    def test_init_no_auth(self):
        rpc = MoneroRPC("http://127.0.0.1:18081")
        assert rpc.base_url == "http://127.0.0.1:18081"
        assert rpc.json_rpc_url == "http://127.0.0.1:18081/json_rpc"
        assert rpc.auth is None

    def test_init_digest_auth(self):
        rpc = MoneroRPC(
            "http://127.0.0.1:18081",
            username="user",
            password="pass",
            digest_auth=True,
        )
        from requests.auth import HTTPDigestAuth
        assert isinstance(rpc.auth, HTTPDigestAuth)

    def test_init_basic_auth(self):
        rpc = MoneroRPC(
            "http://127.0.0.1:18081",
            username="user",
            password="pass",
            digest_auth=False,
        )
        from requests.auth import HTTPBasicAuth
        assert isinstance(rpc.auth, HTTPBasicAuth)

    def test_init_strips_trailing_slash(self):
        rpc = MoneroRPC("http://127.0.0.1:18081/")
        assert rpc.base_url == "http://127.0.0.1:18081"

    def test_init_no_auth_when_only_username(self):
        rpc = MoneroRPC("http://127.0.0.1:18081", username="user")
        assert rpc.auth is None

    @patch("unified_exporter.requests.Session")
    def test_call_success(self, mock_session_cls):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "jsonrpc": "2.0",
            "id": "0",
            "result": {"height": 100},
        }
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        rpc = MoneroRPC("http://127.0.0.1:18081")
        result = rpc.call("get_info")
        assert result == {"height": 100}

    @patch("unified_exporter.requests.Session")
    def test_call_rpc_error(self, mock_session_cls):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "jsonrpc": "2.0",
            "id": "0",
            "error": {"code": -1, "message": "Method not found"},
        }
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        rpc = MoneroRPC("http://127.0.0.1:18081")
        with pytest.raises(RuntimeError, match="monerod RPC error"):
            rpc.call("bad_method")

    @patch("unified_exporter.requests.Session")
    def test_call_empty_result(self, mock_session_cls):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"jsonrpc": "2.0", "id": "0"}
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        rpc = MoneroRPC("http://127.0.0.1:18081")
        result = rpc.call("get_info")
        assert result == {}

    @patch("unified_exporter.requests.Session")
    def test_post_other_success(self, mock_session_cls):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "OK"}
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        rpc = MoneroRPC("http://127.0.0.1:18081")
        result = rpc.post_other("/get_net_stats")
        assert result == {"status": "OK"}

    @patch("unified_exporter.requests.Session")
    def test_post_other_non_json(self, mock_session_cls):
        mock_resp = MagicMock()
        mock_resp.json.side_effect = ValueError("No JSON")
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        rpc = MoneroRPC("http://127.0.0.1:18081")
        result = rpc.post_other("/some_endpoint")
        assert result == {}


# ── Collector: _sanitize_p2pool_name ──────────────────────────────


class TestSanitizeName:
    def setup_method(self):
        rpc = MagicMock()
        self.collector = MoneroP2PoolCollector(rpc)

    def test_basic_path(self):
        assert self.collector._sanitize_p2pool_name("local/stratum_hashrate_15m") == "p2pool_local_stratum_hashrate_15m"

    def test_special_chars_replaced(self):
        name = self.collector._sanitize_p2pool_name("path-with.special/chars")
        assert "-" not in name
        assert "." not in name
        assert name.startswith("p2pool_")

    def test_double_underscores_collapsed(self):
        name = self.collector._sanitize_p2pool_name("a__b___c")
        assert "__" not in name

    def test_leading_digit_prefixed(self):
        name = self.collector._sanitize_p2pool_name("123_metric")
        assert name.startswith("p2pool_v_")

    def test_empty_string(self):
        name = self.collector._sanitize_p2pool_name("")
        assert name == "p2pool_value"

    def test_os_sep_handled(self):
        name = self.collector._sanitize_p2pool_name(f"a{os.sep}b{os.sep}c")
        assert name == "p2pool_a_b_c"


# ── Collector: _flatten_p2pool_json ───────────────────────────────


class TestFlattenP2PoolJson:
    def setup_method(self):
        rpc = MagicMock()
        self.collector = MoneroP2PoolCollector(rpc)

    def test_flat_dict(self):
        result = self.collector._flatten_p2pool_json("stats", {"hashrate": 1000, "miners": 50})
        assert result == {"stats_hashrate": 1000, "stats_miners": 50}

    def test_nested_dict(self):
        result = self.collector._flatten_p2pool_json("pool", {
            "statistics": {"hashRate": 12500000, "miners": 450}
        })
        assert result == {
            "pool_statistics_hashRate": 12500000,
            "pool_statistics_miners": 450,
        }

    def test_list_ignored(self):
        result = self.collector._flatten_p2pool_json("data", {
            "count": 5,
            "items": [1, 2, 3],
        })
        assert result == {"data_count": 5}

    def test_bool_preserved(self):
        result = self.collector._flatten_p2pool_json("status", {"online": True, "syncing": False})
        assert result == {"status_online": True, "status_syncing": False}

    def test_string_preserved(self):
        result = self.collector._flatten_p2pool_json("info", {"version": "v4.14"})
        assert result == {"info_version": "v4.14"}

    def test_empty_dict(self):
        result = self.collector._flatten_p2pool_json("empty", {})
        assert result == {}

    def test_deeply_nested(self):
        result = self.collector._flatten_p2pool_json("a", {"b": {"c": {"d": 42}}})
        assert result == {"a_b_c_d": 42}

    def test_none_value_ignored(self):
        result = self.collector._flatten_p2pool_json("x", {"a": None, "b": 1})
        assert result == {"x_b": 1}


# ── Collector: _map_get_info ──────────────────────────────────────


class TestMapGetInfo:
    def setup_method(self):
        rpc = MagicMock()
        self.collector = MoneroP2PoolCollector(rpc)

    def test_all_numeric_fields(self, sample_get_info):
        store = MetricStore()
        self.collector._map_get_info(sample_get_info, store)
        metrics = {m.name: m for m in store.all()}

        assert "monero_height" in metrics
        assert "monero_target_height" in metrics
        assert "monero_difficulty" in metrics
        assert "monero_tx_count" in metrics
        assert "monero_tx_pool_size" in metrics
        assert "monero_database_size_bytes" in metrics
        assert "monero_free_space_bytes" in metrics
        assert "monero_incoming_connections" in metrics
        assert "monero_outgoing_connections" in metrics

    def test_boolean_flags(self, sample_get_info):
        store = MetricStore()
        self.collector._map_get_info(sample_get_info, store)
        metrics = {m.name: m for m in store.all()}

        assert "monero_synchronized" in metrics
        assert "monero_busy_syncing" in metrics
        assert "monero_offline" in metrics
        assert "monero_restricted_rpc" in metrics

    def test_empty_info(self):
        store = MetricStore()
        self.collector._map_get_info({}, store)
        assert list(store.all()) == []

    def test_partial_info(self):
        store = MetricStore()
        self.collector._map_get_info({"height": 100}, store)
        metrics = {m.name: m for m in store.all()}
        assert "monero_height" in metrics
        assert "monero_difficulty" not in metrics


# ── Collector: _map_block_header ──────────────────────────────────


class TestMapBlockHeader:
    def setup_method(self):
        rpc = MagicMock()
        self.collector = MoneroP2PoolCollector(rpc)

    def test_all_fields(self, sample_block_header):
        store = MetricStore()
        header = sample_block_header["block_header"]
        self.collector._map_block_header(header, store, metric_prefix="monero_last_block_")
        metrics = {m.name: m for m in store.all()}

        assert "monero_last_block_height" in metrics
        assert "monero_last_block_reward" in metrics
        assert "monero_last_block_num_txes" in metrics
        assert "monero_last_block_orphan_status" in metrics

    def test_orphan_true(self):
        store = MetricStore()
        self.collector._map_block_header(
            {"orphan_status": True},
            store,
            metric_prefix="test_",
        )
        metrics = {m.name: m for m in store.all()}
        assert "test_orphan_status" in metrics


# ── Collector: _map_connections ───────────────────────────────────


class TestMapConnections:
    def setup_method(self):
        rpc = MagicMock()
        self.collector = MoneroP2PoolCollector(rpc)

    def test_connection_counts(self, sample_connections):
        store = MetricStore()
        self.collector._map_connections(sample_connections, store)
        metrics = {m.name: m for m in store.all()}

        assert "monero_connections" in metrics
        assert "monero_connections_incoming" in metrics
        assert "monero_connections_outgoing" in metrics
        assert "monero_connections_state" in metrics

    def test_empty_connections(self):
        store = MetricStore()
        self.collector._map_connections({"connections": []}, store)
        metrics = {m.name: m for m in store.all()}
        assert "monero_connections" in metrics

    def test_no_connections_key(self):
        store = MetricStore()
        self.collector._map_connections({}, store)
        assert list(store.all()) == []


# ── Collector: _map_bans ─────────────────────────────────────────


class TestMapBans:
    def setup_method(self):
        rpc = MagicMock()
        self.collector = MoneroP2PoolCollector(rpc)

    def test_ban_counts(self, sample_bans):
        store = MetricStore()
        self.collector._map_bans(sample_bans, store)
        metrics = {m.name: m for m in store.all()}

        assert "monero_bans_total" in metrics
        assert "monero_bans_active" in metrics
        assert "monero_bans_max_seconds" in metrics

    def test_no_bans(self):
        store = MetricStore()
        self.collector._map_bans({"bans": []}, store)
        metrics = {m.name: m for m in store.all()}
        assert "monero_bans_total" in metrics

    def test_missing_bans_key(self):
        store = MetricStore()
        self.collector._map_bans({}, store)
        assert list(store.all()) == []


# ── Collector: _map_pool_stats ────────────────────────────────────


class TestMapPoolStats:
    def setup_method(self):
        rpc = MagicMock()
        self.collector = MoneroP2PoolCollector(rpc)

    def test_pool_stats(self):
        store = MetricStore()
        self.collector._map_pool_stats(
            {"pool_stats": {"txs_total": 12, "fee_total": 50000, "bytes_total": 120000}},
            store,
        )
        metrics = {m.name: m for m in store.all()}
        assert "monero_txpool_backlog_txs" in metrics
        assert "monero_txpool_backlog_total_fee" in metrics
        assert "monero_txpool_backlog_total_weight" in metrics

    def test_missing_pool_stats(self):
        store = MetricStore()
        self.collector._map_pool_stats({}, store)
        assert list(store.all()) == []


# ── Collector: _map_fee_estimate ──────────────────────────────────


class TestMapFeeEstimate:
    def setup_method(self):
        rpc = MagicMock()
        self.collector = MoneroP2PoolCollector(rpc)

    def test_base_fee(self):
        store = MetricStore()
        self.collector._map_fee_estimate({"fee": 20000}, store)
        metrics = {m.name: m for m in store.all()}
        assert "monero_fee_estimate" in metrics

    def test_fee_tiers(self):
        store = MetricStore()
        self.collector._map_fee_estimate(
            {"fee": 20000, "fees": [20000, 80000, 320000, 4000000]},
            store,
        )
        metrics = {m.name: m for m in store.all()}
        assert "monero_fee_estimate" in metrics
        assert "monero_fee_estimate_tier" in metrics


# ── Collector: _map_net_stats ─────────────────────────────────────


class TestMapNetStats:
    def setup_method(self):
        rpc = MagicMock()
        self.collector = MoneroP2PoolCollector(rpc)

    def test_net_stats(self):
        store = MetricStore()
        self.collector._map_net_stats(
            {"start_time": 1765500000, "total_bytes_in": 1000000, "total_bytes_out": 500000},
            store,
        )
        metrics = {m.name: m for m in store.all()}
        assert "monero_net_start_time" in metrics
        assert "monero_net_total_bytes_in" in metrics
        assert "monero_net_total_bytes_out" in metrics


# ── Collector: _map_limit ─────────────────────────────────────────


class TestMapLimit:
    def setup_method(self):
        rpc = MagicMock()
        self.collector = MoneroP2PoolCollector(rpc)

    def test_bandwidth_limits(self):
        store = MetricStore()
        self.collector._map_limit({"limit_down": 8192, "limit_up": 2048}, store)
        metrics = {m.name: m for m in store.all()}
        assert "monero_limit_down_kbps" in metrics
        assert "monero_limit_up_kbps" in metrics


# ── Collector: _map_miner_data ────────────────────────────────────


class TestMapMinerData:
    def setup_method(self):
        rpc = MagicMock()
        self.collector = MoneroP2PoolCollector(rpc)

    def test_miner_data(self):
        store = MetricStore()
        self.collector._map_miner_data(
            {
                "height": 3563500,
                "difficulty": "0x5166170AB0",
                "median_weight": 300000,
                "already_generated_coins": 18400000000000000000,
                "tx_backlog": [{"fee": 100}, {"fee": 200}],
            },
            store,
        )
        metrics = {m.name: m for m in store.all()}
        assert "monero_miner_height" in metrics
        assert "monero_miner_difficulty" in metrics
        assert "monero_miner_tx_backlog_txs" in metrics


# ── Collector: _collect_p2pool_tree ───────────────────────────────


class TestCollectP2PoolTree:
    def setup_method(self):
        rpc = MagicMock()
        self.collector = MoneroP2PoolCollector(rpc)

    def test_reads_json_files(self, p2pool_api_dirs):
        mini_dir, main_dir = p2pool_api_dirs
        store = MetricStore()
        self.collector._collect_p2pool_tree("mini", mini_dir, store)
        metrics = {m.name: m for m in store.all()}
        assert len(metrics) > 0
        # Should have stratum metrics
        assert any("stratum" in name for name in metrics)

    def test_nonexistent_dir_skipped(self):
        store = MetricStore()
        self.collector._collect_p2pool_tree("mini", "/nonexistent/path", store)
        assert list(store.all()) == []

    def test_non_json_files_skipped(self, tmp_path):
        d = tmp_path / "api"
        d.mkdir()
        (d / "binary_file").write_bytes(b"\x00\x01\x02\x03")
        store = MetricStore()
        self.collector._collect_p2pool_tree("test", str(d), store)
        assert list(store.all()) == []

    def test_timestamp_age_metric(self, tmp_path):
        d = tmp_path / "api"
        d.mkdir()
        import time
        # Field name must end with _time or _timestamp to trigger age metric
        (d / "stats").write_text(json.dumps({
            "last_block_found_time": int(time.time()) - 60,
        }))
        store = MetricStore()
        self.collector._collect_p2pool_tree("mini", str(d), store)
        metrics = {m.name: m for m in store.all()}
        # Should create an age_seconds metric for timestamp fields
        age_metrics = [n for n in metrics if "age_seconds" in n]
        assert len(age_metrics) >= 1


# ── Collector: collect() integration ──────────────────────────────


class TestCollectIntegration:
    def test_full_collect_with_mocked_rpc(self, mock_rpc, sample_get_info, p2pool_api_dirs):
        mini_dir, main_dir = p2pool_api_dirs
        mock_rpc.call.side_effect = lambda method, **kwargs: {
            "get_info": sample_get_info,
            "get_last_block_header": {
                "block_header": {"height": 100, "reward": 600000000000}
            },
            "get_block_count": {"count": 3563500},
            "sync_info": {"height": 3563500, "target_height": 3563500, "peers": []},
            "get_version": {"version": 196614, "release": True},
            "hard_fork_info": {"version": 16, "enabled": True},
            "get_fee_estimate": {"fee": 20000},
            "get_miner_data": {"height": 3563500},
            "get_alternate_chains": {"chains": []},
            "get_connections": {"connections": []},
            "get_bans": {"bans": []},
        }.get(method, {})
        mock_rpc.post_other.return_value = {}

        collector = MoneroP2PoolCollector(
            monero_rpc=mock_rpc,
            p2pool_mini_dir=mini_dir,
            p2pool_main_dir=main_dir,
        )
        metrics = list(collector.collect())
        assert len(metrics) > 10  # Should produce many metrics

        metric_names = {m.name for m in metrics}
        assert "monero_rpc_up" in metric_names
        assert "monero_height" in metric_names

    def test_collect_rpc_down(self, p2pool_api_dirs):
        """When monerod is unreachable, should still collect P2Pool metrics."""
        mini_dir, main_dir = p2pool_api_dirs
        rpc = MagicMock()
        rpc.call.side_effect = Exception("Connection refused")
        rpc.post_other.side_effect = Exception("Connection refused")

        collector = MoneroP2PoolCollector(
            monero_rpc=rpc,
            p2pool_mini_dir=mini_dir,
            p2pool_main_dir=main_dir,
        )
        metrics = list(collector.collect())
        metric_names = {m.name for m in metrics}

        # Should have rpc_up = 0
        assert "monero_rpc_up" in metric_names
        # Should still have P2Pool metrics from JSON files
        assert any("p2pool" in name for name in metric_names)


# ── parse_args ────────────────────────────────────────────────────


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.listen_address == "127.0.0.1"
        assert args.listen_port == 18096
        assert args.monero_rpc_url == "http://127.0.0.1:18081"
        assert args.p2pool_mini_dir == "/opt/p2pool/api-mini"
        assert args.p2pool_main_dir == "/opt/p2pool/api-main"

    def test_custom_port(self):
        args = parse_args(["--listen-port", "9999"])
        assert args.listen_port == 9999

    def test_custom_rpc_url(self):
        args = parse_args(["--monero-rpc-url", "http://10.0.0.1:18081"])
        assert args.monero_rpc_url == "http://10.0.0.1:18081"

    def test_auth_flags(self):
        args = parse_args([
            "--monero-rpc-username", "user",
            "--monero-rpc-password", "pass",
            "--monero-rpc-no-digest",
        ])
        assert args.monero_rpc_username == "user"
        assert args.monero_rpc_password == "pass"
        assert args.monero_rpc_no_digest is True
