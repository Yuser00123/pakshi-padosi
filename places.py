"""Where are you? OpenStreetMap Nominatim (open data; 1 request/second, identify yourself)."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

import requests

NOMINATIM = "https://nominatim.openstreetmap.org"
UA = {"User-Agent": "PakshiPadosi/0.1 (+https://github.com/Yuser00123/pakshi-padosi)", "Accept-Language": "en"}
_lock = threading.Lock()
_last = 0.0


@dataclass
class Place:
    lat: float
    lon: float
    name: str        # short: "Raebareli, Uttar Pradesh"
    display: str     # full Nominatim string


def _throttle() -> None:
    global _last
    with _lock:
        wait = 1.05 - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.time()


def _short(addr: dict, fallback: str) -> str:
    town = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("suburb") or addr.get("county") or addr.get("state_district")
    state = addr.get("state")
    return ", ".join(x for x in (town, state) if x) or fallback


def geocode(query: str) -> Optional[Place]:
    """'Raebareli' → Place. Biased to India but works anywhere."""
    q = (query or "").strip()
    if not q:
        return None
    _throttle()
    r = requests.get(f"{NOMINATIM}/search", headers=UA, timeout=20,
                     params=dict(q=q, format="jsonv2", limit=1, addressdetails=1, countrycodes="in"))
    rows = r.json() if r.ok else []
    if not rows:  # retry worldwide
        _throttle()
        r = requests.get(f"{NOMINATIM}/search", headers=UA, timeout=20, params=dict(q=q, format="jsonv2", limit=1, addressdetails=1))
        rows = r.json() if r.ok else []
    if not rows:
        return None
    row = rows[0]
    return Place(float(row["lat"]), float(row["lon"]), _short(row.get("address", {}), row["display_name"].split(",")[0]), row["display_name"])


def reverse(lat: float, lon: float) -> Place:
    """GPS → a human name for the card header. Never fails (falls back to coordinates)."""
    try:
        _throttle()
        r = requests.get(f"{NOMINATIM}/reverse", headers=UA, timeout=20,
                         params=dict(lat=lat, lon=lon, format="jsonv2", zoom=14, addressdetails=1))
        row = r.json()
        return Place(lat, lon, _short(row.get("address", {}), f"{lat:.3f}, {lon:.3f}"), row.get("display_name", ""))
    except Exception:  # noqa: BLE001
        return Place(lat, lon, f"{lat:.3f}, {lon:.3f}", "")


def parse_coords(text: str) -> Optional[tuple]:
    """Accept '26.21, 81.22' typed or pasted from Google Maps."""
    try:
        a, b = [float(x) for x in text.replace(";", ",").split(",")[:2]]
        if -90 <= a <= 90 and -180 <= b <= 180:
            return a, b
    except Exception:  # noqa: BLE001
        pass
    return None


if __name__ == "__main__":
    print(geocode("Raebareli"))
    print(geocode("Samaspur Bird Sanctuary"))
    print(reverse(26.2087, 81.2186))
