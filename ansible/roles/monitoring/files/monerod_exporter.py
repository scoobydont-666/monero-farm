#!/usr/bin/env python3
import time
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer

DAEMON_URL = "http://127.0.0.1:18081/get_info"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return

        try:
            r = requests.get(DAEMON_URL, timeout=3)
            info = r.json()
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"# exporter_error {{}} {e}\n".encode())
            return

        metrics = []

        # Core Monero metrics
        def metric(name, value):
            metrics.append(f"{name} {value}")

        metric("monero_height", info.get("height", 0))
        metric("monero_target_height", info.get("target_height", 0))
        metric("monero_difficulty", info.get("difficulty", 0))
        metric("monero_tx_count", info.get("tx_count", 0))
        metric("monero_tx_pool_size", info.get("tx_pool_size", 0))
        metric("monero_outgoing_connections", info.get("outgoing_connections_count", 0))
        metric("monero_incoming_connections", info.get("incoming_connections_count", 0))
        metric("monero_database_size_bytes", info.get("database_size", 0))
        metric("monero_free_space_bytes", info.get("free_space", 0))
        metric("monero_synchronized", 1 if info.get("synchronized") else 0)

        # Sync %
        try:
            sync_pct = (info["height"] / info["target_height"]) * 100
        except:
            sync_pct = 0
        metric("monero_sync_percent", sync_pct)

        body = "\n".join(metrics) + "\n"

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(body.encode())


def run():
    server = HTTPServer(("0.0.0.0", 18090), Handler)
    print("Monero exporter running on :18090")
    while True:
        server.handle_request()

if __name__ == "__main__":
    run()
