#!/usr/bin/env python3
"""Dev server for M5Stack ventilation web UI."""

import json
import math
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SCRIPT_DIR = Path(__file__).parent
START_TIME = time.time()
PORT = 3000
HISTORY_INTERVAL_S = 300

fan = {
    "fan_speed": "off",
    "override_until": 0.0,
    "manual_override_minutes": 10,
    "switch_active": False,
}


def get_status() -> dict:
    now = time.time()
    t = now * 0.1
    d: dict = {
        "uptime_seconds": int(now - START_TIME),
        "wifi_rssi": -52,
        "co2_ppm": int(850 + 200 * math.sin(t * 0.3)),
        "temperature": round(22.5 + 1.5 * math.sin(t * 0.1), 1),
        "humidity": round(55 + 10 * math.sin(t * 0.2), 1),
        "pm25": round(8 + 4 * abs(math.sin(t * 0.15)), 1),
        "fan_speed": fan["fan_speed"],
        "switch_active": fan["switch_active"],
    }
    remaining = int(fan["override_until"] - now)
    if remaining > 0:
        d["override_remaining_seconds"] = remaining
    return d


def get_history() -> dict:
    """Generate 48 synthetic history entries (4 hours back at 5-min intervals)."""
    now_s = int(time.time() - START_TIME)
    entries = []
    n = 48
    for i in range(n):
        offset = (n - 1 - i) * HISTORY_INTERVAL_S
        t = max(0, now_s - offset)
        phase = t * 0.005
        co2 = round(820 + 250 * math.sin(phase) + 80 * math.sin(phase * 3.7))
        temp = round(22.0 + 2.0 * math.sin(phase * 0.4), 1)
        hum = round(54 + 12 * math.sin(phase * 0.6 + 1), 1)
        pm25 = round(7 + 5 * abs(math.sin(phase * 0.8)), 1)
        fan_speed = 2 if co2 > 1100 else 1 if co2 > 900 else 0
        entries.append(
            {
                "t": t,
                "co2": co2,
                "temp": temp,
                "hum": hum,
                "pm25": pm25,
                "fan": fan_speed,
            }
        )
    return {"interval_s": HISTORY_INTERVAL_S, "count": len(entries), "entries": entries}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # type: ignore[override]
        print(f"  {self.address_string()} {fmt % args}")

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", (SCRIPT_DIR / "index.html").read_bytes())
        elif path == "/status":
            self._send(200, "application/json", json.dumps(get_status(), indent=2).encode())
        elif path == "/api/history":
            self._send(200, "application/json", json.dumps(get_history()).encode())
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/control":
            qs = parse_qs(urlparse(self.path).query)
            action = (qs.get("action") or [None])[0]
            now = time.time()
            if action == "on":
                fan["fan_speed"] = "high"
                fan["override_until"] = now + fan["manual_override_minutes"] * 60
            elif action == "cancel":
                fan["fan_speed"] = "off"
                fan["override_until"] = 0.0
            print(f"  control: {action} → {fan['fan_speed']}")
            self._send(200, "text/plain", b"OK")
        else:
            self._send(404, "text/plain", b"Not found")


if __name__ == "__main__":
    print(f"Dev server → http://localhost:{PORT}/")
    HTTPServer(("", PORT), Handler).serve_forever()
