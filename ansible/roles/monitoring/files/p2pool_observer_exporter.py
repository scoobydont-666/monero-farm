#!/usr/bin/env python3
"""
p2pool_observer_exporter.py

Prometheus exporter that scrapes miner stats and payouts from
https://mini.p2pool.observer and exposes them as Prometheus metrics.

Metrics exposed (per miner address):

From /api/miner_info/<address>:
  - p2pool_mini_miner_id
  - p2pool_mini_miner_last_share_height
  - p2pool_mini_miner_last_share_timestamp
  - p2pool_mini_miner_window_shares{window_index}
  - p2pool_mini_miner_window_uncles{window_index}
  - p2pool_mini_miner_window_last_height{window_index}

From /api/payouts/<address>?search_limit=N:
  (based on the most recent payout: element 0 of the array)
  - p2pool_mini_last_payout_timestamp
  - p2pool_mini_last_payout_main_height
  - p2pool_mini_last_payout_side_height
  - p2pool_mini_last_payout_including_height
  - p2pool_mini_last_payout_reward_raw
  - p2pool_mini_last_payout_reward_xmr  (coinbase_reward / 1e12)
"""

import argparse
import logging
import time
from typing import Any, Dict

import requests
from prometheus_client import Gauge, start_http_server

LOG = logging.getLogger("p2pool_observer_exporter")

MINER_INFO_URL_TEMPLATE = "https://mini.p2pool.observer/api/miner_info/{address}"
PAYOUTS_URL_TEMPLATE = (
    "https://mini.p2pool.observer/api/payouts/{address}?search_limit={limit}"
)

ATOMIC_UNITS_PER_XMR = 1e12

# ------------------------
# Metric definitions
# ------------------------

MINER_ID = Gauge(
    "p2pool_mini_miner_id",
    "P2Pool mini miner numeric id",
    ["address"],
)

LAST_SHARE_HEIGHT = Gauge(
    "p2pool_mini_miner_last_share_height",
    "Last share height seen for this miner on sidechain",
    ["address"],
)

LAST_SHARE_TS = Gauge(
    "p2pool_mini_miner_last_share_timestamp",
    "Timestamp of last share for this miner (Unix seconds)",
    ["address"],
)

WINDOW_SHARES = Gauge(
    "p2pool_mini_miner_window_shares",
    "Shares in window index for this miner",
    ["address", "window_index"],
)

WINDOW_UNCLES = Gauge(
    "p2pool_mini_miner_window_uncles",
    "Uncles in window index for this miner",
    ["address", "window_index"],
)

WINDOW_LAST_HEIGHT = Gauge(
    "p2pool_mini_miner_window_last_height",
    "Last height reported in this window index for this miner",
    ["address", "window_index"],
)

LAST_PAYOUT_TS = Gauge(
    "p2pool_mini_last_payout_timestamp",
    "Timestamp of last payout for this miner (Unix seconds)",
    ["address"],
)

LAST_PAYOUT_MAIN_HEIGHT = Gauge(
    "p2pool_mini_last_payout_main_height",
    "Mainchain height of last payout for this miner",
    ["address"],
)

LAST_PAYOUT_SIDE_HEIGHT = Gauge(
    "p2pool_mini_last_payout_side_height",
    "Sidechain height of last payout for this miner",
    ["address"],
)

LAST_PAYOUT_INCLUDING_HEIGHT = Gauge(
    "p2pool_mini_last_payout_including_height",
    "Sidechain including_height of last payout for this miner",
    ["address"],
)

LAST_PAYOUT_REWARD_RAW = Gauge(
    "p2pool_mini_last_payout_reward_raw",
    "Raw coinbase_reward of last payout (atomic units)",
    ["address"],
)

LAST_PAYOUT_REWARD_XMR = Gauge(
    "p2pool_mini_last_payout_reward_xmr",
    "Coinbase_reward of last payout expressed in XMR (reward / 1e12)",
    ["address"],
)

# ------------------------
# Helpers
# ------------------------


def fetch_json(url: str) -> Any:
    LOG.debug("Fetching URL: %s", url)
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _to_float(value: Any) -> float:
    if value is None:
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _to_timestamp(value: Any) -> float:
    """
    Convert to Unix seconds (best-effort).

    For these APIs, timestamps are already integers like 1765504951,
    so we mostly just cast to float. This function also handles
    ISO-8601 strings, just in case.
    """
    if value is None:
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        from datetime import datetime

        try:
            s = value.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            return dt.timestamp()
        except Exception:
            return float("nan")

    return float("nan")


# ------------------------
# Mapping functions
# ------------------------


def update_miner_metrics(address: str, data: Dict[str, Any]) -> None:
    """
    Map fields from /api/miner_info/<address> into Prometheus metrics.

    Example JSON:

    {
        "id": 28916,
        "address": "<addr>",
        "shares": [
            {"shares": 0, "uncles": 0, "last_height": 0},
            {"shares": 220, "uncles": 5, "last_height": 12464190},
            {"shares": 0, "uncles": 0, "last_height": 0}
        ],
        "last_share_height": 12464190,
        "last_share_timestamp": 1765504951
    }
    """
    LOG.debug("miner_info JSON: %s", data)
    labels = (address,)

    miner_id = data.get("id")
    if miner_id is not None:
        MINER_ID.labels(*labels).set(_to_float(miner_id))

    last_height = data.get("last_share_height")
    if last_height is not None:
        LAST_SHARE_HEIGHT.labels(*labels).set(_to_float(last_height))

    last_ts = data.get("last_share_timestamp")
    LAST_SHARE_TS.labels(*labels).set(_to_timestamp(last_ts))

    # shares is a list of windows; we expose per index
    shares_list = data.get("shares") or []
    if isinstance(shares_list, list):
        for idx, entry in enumerate(shares_list):
            if not isinstance(entry, dict):
                continue
            idx_label = str(idx)
            WINDOW_SHARES.labels(address, idx_label).set(
                _to_float(entry.get("shares"))
            )
            WINDOW_UNCLES.labels(address, idx_label).set(
                _to_float(entry.get("uncles"))
            )
            WINDOW_LAST_HEIGHT.labels(address, idx_label).set(
                _to_float(entry.get("last_height"))
            )


def update_payout_metrics(address: str, payouts: Any) -> None:
    """
    Map fields from /api/payouts/<address>?search_limit=N into metrics.

    We take the *first* element of the array as "most recent" payout:

    {
        "miner": 28916,
        "template_id": "...",
        "side_height": 12462049,
        "main_id": "...",
        "main_height": 3563428,
        "timestamp": 1765483184,
        "coinbase_id": "...",
        "coinbase_reward": 5041918014,
        "coinbase_private_key": "...",
        "coinbase_output_index": 580,
        "global_output_index": 145025503,
        "including_height": 12459889
    }
    """
    labels = (address,)

    if not isinstance(payouts, list) or not payouts:
        LOG.debug("No payouts for miner %s", address)
        LAST_PAYOUT_TS.labels(*labels).set(float("nan"))
        LAST_PAYOUT_MAIN_HEIGHT.labels(*labels).set(float("nan"))
        LAST_PAYOUT_SIDE_HEIGHT.labels(*labels).set(float("nan"))
        LAST_PAYOUT_INCLUDING_HEIGHT.labels(*labels).set(float("nan"))
        LAST_PAYOUT_REWARD_RAW.labels(*labels).set(float("nan"))
        LAST_PAYOUT_REWARD_XMR.labels(*labels).set(float("nan"))
        return

    last = payouts[0]
    if not isinstance(last, dict):
        LOG.warning("Unexpected payout element type: %r", type(last))
        return

    LOG.debug("Last payout JSON: %s", last)

    ts = last.get("timestamp")
    main_h = last.get("main_height")
    side_h = last.get("side_height")
    inc_h = last.get("including_height")
    reward_raw = last.get("coinbase_reward")

    reward_raw_f = _to_float(reward_raw)
    LAST_PAYOUT_TS.labels(*labels).set(_to_timestamp(ts))
    LAST_PAYOUT_MAIN_HEIGHT.labels(*labels).set(_to_float(main_h))
    LAST_PAYOUT_SIDE_HEIGHT.labels(*labels).set(_to_float(side_h))
    LAST_PAYOUT_INCLUDING_HEIGHT.labels(*labels).set(_to_float(inc_h))
    LAST_PAYOUT_REWARD_RAW.labels(*labels).set(reward_raw_f)

    # Convert atomic units → XMR, if we have a real number
    if reward_raw_f == reward_raw_f:  # not NaN
        LAST_PAYOUT_REWARD_XMR.labels(*labels).set(
            reward_raw_f / ATOMIC_UNITS_PER_XMR
        )
    else:
        LAST_PAYOUT_REWARD_XMR.labels(*labels).set(float("nan"))


# ------------------------
# Main
# ------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Prometheus exporter for MINI.P2Pool.Observer miner stats"
    )
    parser.add_argument(
        "--miner-address",
        required=True,
        help="Monero address used with mini.p2pool.observer",
    )
    parser.add_argument(
        "--listen-address",
        default="0.0.0.0",
        help="Address to listen on for Prometheus scrapes (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=8000,
        help="Port to listen on for Prometheus scrapes (default: 8000)",
    )
    parser.add_argument(
        "--payout-limit",
        type=int,
        default=20,
        help="search_limit for payouts API (default: 20)",
    )
    parser.add_argument(
        "--scrape-interval",
        type=int,
        default=60,
        help="How often to poll mini.p2pool.observer, in seconds (default: 60)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR). Default: INFO",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    address = args.miner_address
    miner_info_url = MINER_INFO_URL_TEMPLATE.format(address=address)
    payouts_url = PAYOUTS_URL_TEMPLATE.format(
        address=address, limit=args.payout_limit
    )

    LOG.info("Starting P2Pool mini exporter")
    LOG.info("Miner address: %s", address)
    LOG.info("Miner info URL: %s", miner_info_url)
    LOG.info("Payouts URL:    %s", payouts_url)
    LOG.info(
        "Listening on %s:%d (scrape interval: %ds)",
        args.listen_address,
        args.listen_port,
        args.scrape_interval,
    )

    # Start HTTP server for Prometheus
    start_http_server(port=args.listen_port, addr=args.listen_address)

    # Simple polling loop
    while True:
        try:
            miner_info = fetch_json(miner_info_url)
            update_miner_metrics(address, miner_info)
        except Exception as exc:
            LOG.exception("Failed to update miner metrics: %s", exc)

        try:
            payouts = fetch_json(payouts_url)
            update_payout_metrics(address, payouts)
        except Exception as exc:
            LOG.exception("Failed to update payout metrics: %s", exc)

        time.sleep(args.scrape_interval)


if __name__ == "__main__":
    raise SystemExit(main())

