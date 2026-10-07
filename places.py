"""Where are you? OpenStreetMap Nominatim (open data; 1 request/second, identify yourself)."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

import requests

NOMINATIM = "https://nominatim.openstreetmap.org"
PHOTON = "https://photon.komoot.io"  # open-source geocoder on OSM data; fallback when Nominatim refuses a shared IP

# Last-resort table so the app works even if every geocoder is down (±0.05°, fine for a 25–50 km search).
CITIES = {
    "raebareli": (26.2087, 81.2186, "Raebareli, Uttar Pradesh"), "rae bareli": (26.2087, 81.2186, "Raebareli, Uttar Pradesh"),
    "samaspur": (25.9919, 81.3929, "Samaspur Bird Sanctuary, Raebareli"), "lucknow": (26.8467, 80.9462, "Lucknow, Uttar Pradesh"),
    "kanpur": (26.4499, 80.3319, "Kanpur, Uttar Pradesh"), "prayagraj": (25.4358, 81.8463, "Prayagraj, Uttar Pradesh"),
    "allahabad": (25.4358, 81.8463, "Prayagraj, Uttar Pradesh"), "varanasi": (25.3176, 82.9739, "Varanasi, Uttar Pradesh"),
    "ayodhya": (26.7922, 82.1998, "Ayodhya, Uttar Pradesh"), "gorakhpur": (26.7606, 83.3732, "Gorakhpur, Uttar Pradesh"),
    "agra": (27.1767, 78.0081, "Agra, Uttar Pradesh"), "bareilly": (28.3670, 79.4304, "Bareilly, Uttar Pradesh"),
    "meerut": (28.9845, 77.7064, "Meerut, Uttar Pradesh"), "noida": (28.5355, 77.3910, "Noida, Uttar Pradesh"),
    "delhi": (28.6139, 77.2090, "Delhi"), "new delhi": (28.6139, 77.2090, "Delhi"), "gurugram": (28.4595, 77.0266, "Gurugram, Haryana"),
    "gurgaon": (28.4595, 77.0266, "Gurugram, Haryana"), "chandigarh": (30.7333, 76.7794, "Chandigarh"),
    "jaipur": (26.9124, 75.7873, "Jaipur, Rajasthan"), "jodhpur": (26.2389, 73.0243, "Jodhpur, Rajasthan"),
    "udaipur": (24.5854, 73.7125, "Udaipur, Rajasthan"), "bhopal": (23.2599, 77.4126, "Bhopal, Madhya Pradesh"),
    "indore": (22.7196, 75.8577, "Indore, Madhya Pradesh"), "patna": (25.5941, 85.1376, "Patna, Bihar"),
    "ranchi": (23.3441, 85.3096, "Ranchi, Jharkhand"), "kolkata": (22.5726, 88.3639, "Kolkata, West Bengal"),
    "bhubaneswar": (20.2961, 85.8245, "Bhubaneswar, Odisha"), "guwahati": (26.1445, 91.7362, "Guwahati, Assam"),
    "dehradun": (30.3165, 78.0322, "Dehradun, Uttarakhand"), "shimla": (31.1048, 77.1734, "Shimla, Himachal Pradesh"),
    "srinagar": (34.0837, 74.7973, "Srinagar, Jammu & Kashmir"), "amritsar": (31.6340, 74.8723, "Amritsar, Punjab"),
    "mumbai": (19.0760, 72.8777, "Mumbai, Maharashtra"), "pune": (18.5204, 73.8567, "Pune, Maharashtra"),
    "nagpur": (21.1458, 79.0882, "Nagpur, Maharashtra"), "ahmedabad": (23.0225, 72.5714, "Ahmedabad, Gujarat"),
    "surat": (21.1702, 72.8311, "Surat, Gujarat"), "vadodara": (22.3072, 73.1812, "Vadodara, Gujarat"),
    "hyderabad": (17.3850, 78.4867, "Hyderabad, Telangana"), "bengaluru": (12.9716, 77.5946, "Bengaluru, Karnataka"),
    "bangalore": (12.9716, 77.5946, "Bengaluru, Karnataka"), "mysuru": (12.2958, 76.6394, "Mysuru, Karnataka"),
    "chennai": (13.0827, 80.2707, "Chennai, Tamil Nadu"), "coimbatore": (11.0168, 76.9558, "Coimbatore, Tamil Nadu"),
    "kochi": (9.9312, 76.2673, "Kochi, Kerala"), "thiruvananthapuram": (8.5241, 76.9366, "Thiruvananthapuram, Kerala"),
    "visakhapatnam": (17.6868, 83.2185, "Visakhapatnam, Andhra Pradesh"), "bharatpur": (27.2173, 77.4901, "Bharatpur, Rajasthan"),
}
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


def _log(msg: str) -> None:
    print(f"[places] {msg}", flush=True)


def _nominatim(q: str) -> Optional[Place]:
    for extra in ({"countrycodes": "in"}, {}):
        _throttle()
        r = requests.get(f"{NOMINATIM}/search", headers=UA, timeout=20, params=dict(q=q, format="jsonv2", limit=1, addressdetails=1, **extra))
        if not r.ok:
            raise RuntimeError(f"nominatim HTTP {r.status_code}")
        rows = r.json()
        if rows:
            row = rows[0]
            return Place(float(row["lat"]), float(row["lon"]), _short(row.get("address", {}), row["display_name"].split(",")[0]), row["display_name"])
    return None


def _photon(q: str) -> Optional[Place]:
    r = requests.get(f"{PHOTON}/api/", headers=UA, timeout=10, params=dict(q=q, limit=1, lang="en"))
    if not r.ok:
        raise RuntimeError(f"photon HTTP {r.status_code}")
    feats = r.json().get("features") or []
    if not feats:
        return None
    f = feats[0]
    lon, lat = f["geometry"]["coordinates"]
    pr = f.get("properties", {})
    name = ", ".join(x for x in (pr.get("name") or pr.get("city"), pr.get("state")) if x) or q
    return Place(float(lat), float(lon), name, ", ".join(x for x in (pr.get("name"), pr.get("city"), pr.get("state"), pr.get("country")) if x))


def geocode(query: str) -> Optional[Place]:
    """'Raebareli' → Place. Nominatim → Photon → built-in table (free hosts share IPs that geocoders sometimes refuse)."""
    q = (query or "").strip()
    if not q:
        return None
    for fn in (_nominatim, _photon):
        try:
            place = fn(q)
            if place:
                return place
        except Exception as err:  # noqa: BLE001
            _log(f"{fn.__name__} failed for {q!r}: {str(err)[:100]}")
    hit = CITIES.get(q.lower().split(",")[0].strip())
    if hit:
        return Place(hit[0], hit[1], hit[2], hit[2] + ", India")
    return None


def reverse(lat: float, lon: float) -> Place:
    """GPS → a human name for the card header. Never fails (falls back to coordinates)."""
    try:
        _throttle()
        r = requests.get(f"{NOMINATIM}/reverse", headers=UA, timeout=20,
                         params=dict(lat=lat, lon=lon, format="jsonv2", zoom=14, addressdetails=1))
        if r.ok:
            row = r.json()
            return Place(lat, lon, _short(row.get("address", {}), f"{lat:.3f}, {lon:.3f}"), row.get("display_name", ""))
        _log(f"nominatim reverse HTTP {r.status_code}")
    except Exception as err:  # noqa: BLE001
        _log(f"nominatim reverse failed: {str(err)[:100]}")
    try:
        r = requests.get(f"{PHOTON}/reverse", headers=UA, timeout=10, params=dict(lat=lat, lon=lon, lang="en"))
        pr = (r.json().get("features") or [{}])[0].get("properties", {}) if r.ok else {}
        name = ", ".join(x for x in (pr.get("city") or pr.get("name") or pr.get("county"), pr.get("state")) if x)
        if name:
            return Place(lat, lon, name, name)
    except Exception as err:  # noqa: BLE001
        _log(f"photon reverse failed: {str(err)[:100]}")
    # nearest built-in city within 40 km, else raw coordinates
    import math
    best = min(CITIES.values(), key=lambda c: (c[0] - lat) ** 2 + (c[1] - lon) ** 2)
    if math.hypot((best[0] - lat) * 111, (best[1] - lon) * 100) < 40:
        return Place(lat, lon, f"{best[2]} ke paas", best[2])
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
