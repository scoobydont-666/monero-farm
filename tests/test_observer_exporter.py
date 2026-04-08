"""Tests for p2pool_observer_exporter.py — P2Pool mini observer Prometheus exporter."""

import math
from unittest.mock import patch, MagicMock

import pytest

from p2pool_observer_exporter import (
    ATOMIC_UNITS_PER_XMR,
    LAST_PAYOUT_MAIN_HEIGHT,
    LAST_PAYOUT_REWARD_RAW,
    LAST_PAYOUT_REWARD_XMR,
    LAST_PAYOUT_SIDE_HEIGHT,
    LAST_PAYOUT_TS,
    LAST_SHARE_HEIGHT,
    LAST_SHARE_TS,
    MINER_ID,
    WINDOW_LAST_HEIGHT,
    WINDOW_SHARES,
    WINDOW_UNCLES,
    _to_float,
    _to_timestamp,
    fetch_json,
    update_miner_metrics,
    update_payout_metrics,
)


# ── _to_float() ──────────────────────────────────────────────────


class TestToFloat:
    def test_int(self):
        assert _to_float(42) == 42.0

    def test_float(self):
        assert _to_float(3.14) == 3.14

    def test_zero(self):
        assert _to_float(0) == 0.0

    def test_none_returns_nan(self):
        assert math.isnan(_to_float(None))

    def test_string_number(self):
        assert _to_float("123") == 123.0

    def test_string_float(self):
        assert _to_float("3.14") == 3.14

    def test_string_invalid(self):
        assert math.isnan(_to_float("not_a_number"))

    def test_bool_true(self):
        assert _to_float(True) == 1.0

    def test_bool_false(self):
        assert _to_float(False) == 0.0

    def test_large_int(self):
        assert _to_float(5041918014) == 5041918014.0


# ── _to_timestamp() ──────────────────────────────────────────────


class TestToTimestamp:
    def test_int_passthrough(self):
        assert _to_timestamp(1765504951) == 1765504951.0

    def test_float_passthrough(self):
        assert _to_timestamp(1765504951.5) == 1765504951.5

    def test_none_returns_nan(self):
        assert math.isnan(_to_timestamp(None))

    def test_iso_string_utc(self):
        ts = _to_timestamp("2025-01-01T00:00:00Z")
        assert ts > 0
        assert not math.isnan(ts)

    def test_iso_string_with_offset(self):
        ts = _to_timestamp("2025-01-01T00:00:00+00:00")
        assert ts > 0

    def test_invalid_string(self):
        assert math.isnan(_to_timestamp("not-a-date"))

    def test_zero(self):
        assert _to_timestamp(0) == 0.0


# ── update_miner_metrics() ───────────────────────────────────────


class TestUpdateMinerMetrics:
    def test_basic_miner_info(self, sample_miner_info):
        address = "4TESTADDR"
        update_miner_metrics(address, sample_miner_info)

        assert MINER_ID.labels(address)._value.get() == 28916.0
        assert LAST_SHARE_HEIGHT.labels(address)._value.get() == 12464190.0
        assert LAST_SHARE_TS.labels(address)._value.get() == 1765504951.0

    def test_window_shares(self, sample_miner_info):
        address = "4TESTADDR"
        update_miner_metrics(address, sample_miner_info)

        # Window 0: shares=0
        assert WINDOW_SHARES.labels(address, "0")._value.get() == 0.0
        # Window 1: shares=220
        assert WINDOW_SHARES.labels(address, "1")._value.get() == 220.0
        # Window 1: uncles=5
        assert WINDOW_UNCLES.labels(address, "1")._value.get() == 5.0

    def test_empty_shares_list(self):
        address = "4EMPTYADDR"
        update_miner_metrics(address, {
            "id": 1,
            "shares": [],
            "last_share_height": 0,
            "last_share_timestamp": 0,
        })
        assert MINER_ID.labels(address)._value.get() == 1.0

    def test_missing_fields(self):
        """Should not crash on partial data."""
        address = "4PARTIAL"
        update_miner_metrics(address, {})
        # Should not raise

    def test_non_dict_share_entries_skipped(self):
        address = "4BADSHARE"
        update_miner_metrics(address, {
            "id": 99,
            "shares": ["bad", None, 42],
            "last_share_height": 100,
        })
        assert MINER_ID.labels(address)._value.get() == 99.0


# ── update_payout_metrics() ──────────────────────────────────────


class TestUpdatePayoutMetrics:
    def test_basic_payout(self, sample_payouts):
        address = "4PAYADDR"
        update_payout_metrics(address, sample_payouts)

        assert LAST_PAYOUT_TS.labels(address)._value.get() == 1765483184.0
        assert LAST_PAYOUT_MAIN_HEIGHT.labels(address)._value.get() == 3563428.0
        assert LAST_PAYOUT_SIDE_HEIGHT.labels(address)._value.get() == 12462049.0
        assert LAST_PAYOUT_REWARD_RAW.labels(address)._value.get() == 5041918014.0

    def test_reward_xmr_conversion(self, sample_payouts):
        address = "4PAYXMR"
        update_payout_metrics(address, sample_payouts)
        expected_xmr = 5041918014 / ATOMIC_UNITS_PER_XMR
        assert abs(LAST_PAYOUT_REWARD_XMR.labels(address)._value.get() - expected_xmr) < 1e-10

    def test_empty_payouts(self):
        address = "4NOPAY"
        update_payout_metrics(address, [])
        assert math.isnan(LAST_PAYOUT_TS.labels(address)._value.get())
        assert math.isnan(LAST_PAYOUT_REWARD_RAW.labels(address)._value.get())

    def test_none_payouts(self):
        address = "4NONEPAY"
        update_payout_metrics(address, None)
        assert math.isnan(LAST_PAYOUT_TS.labels(address)._value.get())

    def test_non_list_payouts(self):
        address = "4BADPAY"
        update_payout_metrics(address, "not_a_list")
        assert math.isnan(LAST_PAYOUT_TS.labels(address)._value.get())

    def test_non_dict_first_entry(self):
        """Should not crash if first payout entry is not a dict."""
        address = "4BADFIRST"
        update_payout_metrics(address, ["not_a_dict"])
        # Should not raise


# ── fetch_json() ─────────────────────────────────────────────────


class TestFetchJson:
    @patch("p2pool_observer_exporter.requests.get")
    def test_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"height": 100}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_json("http://example.com/api")
        assert result == {"height": 100}
        mock_get.assert_called_once_with("http://example.com/api", timeout=10)

    @patch("p2pool_observer_exporter.requests.get")
    def test_http_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.HTTPError("404")
        with pytest.raises(requests.HTTPError):
            fetch_json("http://example.com/bad")

    @patch("p2pool_observer_exporter.requests.get")
    def test_timeout(self, mock_get):
        import requests
        mock_get.side_effect = requests.Timeout("timeout")
        with pytest.raises(requests.Timeout):
            fetch_json("http://example.com/slow")
