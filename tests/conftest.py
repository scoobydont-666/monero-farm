"""Shared fixtures for monero-farm tests."""

import json
import os
import tempfile
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_rpc():
    """Return a MagicMock that behaves like MoneroRPC."""
    rpc = MagicMock()
    rpc.call.return_value = {}
    rpc.post_other.return_value = {}
    return rpc


@pytest.fixture
def p2pool_api_dirs(tmp_path):
    """Create fake P2Pool API directories with sample JSON files."""
    mini_dir = tmp_path / "api-mini"
    main_dir = tmp_path / "api-main"

    # Mini sidechain stats
    local_dir = mini_dir / "local"
    local_dir.mkdir(parents=True)
    pool_dir = mini_dir / "pool"
    pool_dir.mkdir(parents=True)

    (local_dir / "stratum").write_text(json.dumps({
        "hashrate_15m": 1250,
        "hashrate_1h": 1180,
        "hashrate_24h": 1100,
        "shares_found": 42,
        "shares_failed": 1,
        "connections": 3,
    }))

    (local_dir / "p2p").write_text(json.dumps({
        "connections": 8,
        "peer_list_size": 200,
    }))

    (pool_dir / "stats").write_text(json.dumps({
        "pool_statistics": {
            "hashRate": 12500000,
            "miners": 450,
            "totalHashes": 999999999,
            "lastBlockFound": 3563428,
            "lastBlockFoundTime": 1765504951,
        }
    }))

    # Main sidechain (minimal)
    main_local = main_dir / "local"
    main_local.mkdir(parents=True)
    (main_local / "stratum").write_text(json.dumps({
        "hashrate_15m": 0,
        "hashrate_1h": 0,
        "connections": 0,
    }))

    return str(mini_dir), str(main_dir)


@pytest.fixture
def sample_get_info():
    """Realistic monerod get_info response."""
    return {
        "height": 3563500,
        "target_height": 3563500,
        "difficulty": 350000000000,
        "tx_count": 85000000,
        "tx_pool_size": 12,
        "database_size": 85000000000,
        "free_space": 200000000000,
        "incoming_connections_count": 15,
        "outgoing_connections_count": 8,
        "alt_blocks_count": 2,
        "white_peerlist_size": 1000,
        "grey_peerlist_size": 5000,
        "synchronized": True,
        "busy_syncing": False,
        "offline": False,
        "restricted": True,
        "testnet": False,
        "stagenet": False,
    }


@pytest.fixture
def sample_block_header():
    """Realistic block_header response."""
    return {
        "block_header": {
            "height": 3563499,
            "difficulty": 350000000000,
            "cumulative_difficulty": 1234567890123456,
            "reward": 600000000000,
            "block_weight": 300000,
            "block_size": 300000,
            "num_txes": 5,
            "timestamp": 1765504800,
            "orphan_status": False,
        }
    }


@pytest.fixture
def sample_connections():
    """Realistic get_connections response."""
    return {
        "connections": [
            {"incoming": True, "state": "normal", "host": "1.2.3.4"},
            {"incoming": True, "state": "normal", "host": "5.6.7.8"},
            {"incoming": False, "state": "normal", "host": "10.0.0.1"},
            {"incoming": False, "state": "synchronizing", "host": "10.0.0.2"},
        ]
    }


@pytest.fixture
def sample_bans():
    """Realistic get_bans response."""
    return {
        "bans": [
            {"host": "1.2.3.4", "banned": True, "seconds": 3600},
            {"host": "5.6.7.8", "banned": True, "seconds": 1800},
            {"host": "10.0.0.1", "banned": False, "seconds": 0},
        ]
    }


@pytest.fixture
def sample_miner_info():
    """Realistic P2Pool observer miner_info response."""
    return {
        "id": 28916,
        "address": "4TESTADDR",
        "shares": [
            {"shares": 0, "uncles": 0, "last_height": 0},
            {"shares": 220, "uncles": 5, "last_height": 12464190},
            {"shares": 15, "uncles": 1, "last_height": 12464100},
        ],
        "last_share_height": 12464190,
        "last_share_timestamp": 1765504951,
    }


@pytest.fixture
def sample_payouts():
    """Realistic P2Pool observer payouts response."""
    return [
        {
            "miner": 28916,
            "side_height": 12462049,
            "main_height": 3563428,
            "timestamp": 1765483184,
            "coinbase_reward": 5041918014,
            "including_height": 12459889,
        },
        {
            "miner": 28916,
            "side_height": 12460000,
            "main_height": 3563400,
            "timestamp": 1765480000,
            "coinbase_reward": 4900000000,
            "including_height": 12458000,
        },
    ]
