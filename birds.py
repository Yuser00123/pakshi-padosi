"""Which birds have people *actually* recorded near here, this time of year?

Source: GBIF occurrence API (https://api.gbif.org) — open data, no key. Most Indian records
come from eBird and iNaturalist contributors. We never ask a language model which birds exist
near you; we ask the data, and the model only explains.

Main entry point: `nearby(lat, lon, month)` → Survey.
"""
from __future__ import annotations

import json
import math
import re
import os
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

import requests

GBIF = os.getenv("GBIF_API", "https://api.gbif.org/v1")
AVES = 212  # GBIF taxonKey for class Aves
UA = {"User-Agent": "PakshiPadosi/0.1 (+https://github.com/Yuser00123/pakshi-padosi)"}
TIMEOUT = 40
RADII_KM = (25, 50, 100)
ENOUGH = int(os.getenv("GBIF_ENOUGH_RECORDS", "1000"))  # widen the radius until this many seasonal records
LOCAL_KM = 25  # "yeh tumhare paas bhi dikhi hai" radius
QUARTERS = {"winter": (12, 2), "spring": (3, 5), "monsoon": (6, 8), "autumn": (9, 11)}  # Indian seasons, roughly
NAME_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "species_cache.json")
MAX_SPECIES = 60

_cache: Dict[str, Tuple[float, object]] = {}
CACHE_TTL = 6 * 3600


def _get(path: str, params: list | dict) -> dict:
    """GET with a tiny in-process cache (GBIF asks clients to be gentle)."""
    key = path + "?" + json.dumps(params, sort_keys=True)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]  # type: ignore[return-value]
    for attempt in range(3):
        try:
            r = requests.get(GBIF + path, params=params, headers=UA, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
            _cache[key] = (time.time(), data)
            return data
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable")


# ----------------------------------------------------------------------------- season maths
def season_months(month: int) -> List[Tuple[int, int]]:
    """A ±1-month window as GBIF ranges (GBIF wants 'a,b' ranges; wrap Dec→Jan by splitting)."""
    lo, hi = (month - 2) % 12 + 1, month % 12 + 1  # month-1 .. month+1
    if lo <= hi:
        return [(lo, hi)]
    return [(lo, 12), (1, hi)]


def _quarter_ranges(q: str) -> List[Tuple[int, int]]:
    a, b = QUARTERS[q]
    return [(a, b)] if a <= b else [(a, 12), (1, b)]


def _month_params(ranges: List[Tuple[int, int]]) -> List[Tuple[str, str]]:
    return [("month", f"{a},{b}") for a, b in ranges]


# ----------------------------------------------------------------------------- data classes
@dataclass
class Species:
    key: int
    scientific: str
    english: str
    season_records: int          # records in the ±1-month window within the radius
    year_records: int            # all-year records within the radius
    quarters: Dict[str, int]     # records per Indian season: winter/spring/monsoon/autumn
    status: str                  # "resident" | "winter_visitor" | "monsoon_visitor" | "passage"
    local_records: int = 0       # seasonal records within LOCAL_KM of the user
    hindi: Optional[str] = None  # filled in by names.py
    hindi_source: Optional[str] = None

    @property
    def season_share(self) -> float:
        return self.season_records / self.year_records if self.year_records else 0.0

    @property
    def quarter_shares(self) -> Dict[str, float]:
        tot = sum(self.quarters.values()) or 1
        return {k: round(v / tot, 2) for k, v in self.quarters.items()}


@dataclass
class Hotspot:
    lat: float
    lon: float
    records: int
    name: Optional[str] = None  # eBird hotspot / locality string when present
    km: float = 0.0             # distance from the user


@dataclass
class Survey:
    lat: float
    lon: float
    month: int
    radius_km: int
    season_records: int
    year_records: int
    species: List[Species] = field(default_factory=list)
    hotspots: List[Hotspot] = field(default_factory=list)
    hotspot_radius_km: int = 0
    datasets: List[Tuple[str, int]] = field(default_factory=list)  # (dataset title, records)
    local_records: int = 0  # seasonal records within LOCAL_KM

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @property
    def residents(self) -> List[Species]:
        return [s for s in self.species if s.status == "resident"]

    @property
    def visitors(self) -> List[Species]:
        return [s for s in self.species if s.status != "resident"]

    @property
    def months_label(self) -> str:
        names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        (a, b), *rest = season_months(self.month)
        return f"{names[a - 1]}–{names[(rest[0][1] if rest else b) - 1]}"


# ----------------------------------------------------------------------------- GBIF queries
def _facet_species(lat: float, lon: float, radius_km: int, months: Optional[List[Tuple[int, int]]], limit: int = 300) -> Tuple[int, Dict[int, int]]:
    params: list = [
        ("taxonKey", AVES), ("geoDistance", f"{lat},{lon},{radius_km}km"), ("hasCoordinate", "true"),
        ("limit", 0), ("facet", "speciesKey"), ("facetLimit", limit),
    ]
    if months:
        params += _month_params(months)
    data = _get("/occurrence/search", params)
    counts = {int(c["name"]): int(c["count"]) for c in (data.get("facets") or [{}])[0].get("counts", [])}
    return int(data.get("count", 0)), counts


_names: Dict[str, list] = {}
try:
    with open(NAME_CACHE, encoding="utf-8") as fh:
        _names = json.load(fh)
except Exception:  # noqa: BLE001
    _names = {}


def _save_names() -> None:
    try:
        os.makedirs(os.path.dirname(NAME_CACHE), exist_ok=True)
        with open(NAME_CACHE, "w", encoding="utf-8") as fh:
            json.dump(_names, fh, ensure_ascii=False, indent=0, sort_keys=True)
    except OSError:
        pass


def species_names(keys: List[int]) -> Dict[int, Tuple[str, str]]:
    """(scientific, english) for many keys — disk-cached, parallel for the misses."""
    from concurrent.futures import ThreadPoolExecutor

    out = {int(k): tuple(_names[str(k)]) for k in keys if str(k) in _names}
    missing = [k for k in keys if int(k) not in out]
    if missing:
        with ThreadPoolExecutor(8) as ex:
            for k, pair in zip(missing, ex.map(_species_name, missing)):
                out[int(k)] = pair
                _names[str(k)] = list(pair)
        _save_names()
    return out


def _species_name(key: int) -> Tuple[str, str]:
    sp = _get(f"/species/{key}", {})
    sci = sp.get("canonicalName") or sp.get("scientificName") or str(key)
    en = sp.get("vernacularName") or ""
    if not en:  # try the vernacular endpoint for an English name
        try:
            v = _get(f"/species/{key}/vernacularNames", {"limit": 50})
            for row in v.get("results", []):
                if row.get("language") in ("eng", "en") and row.get("vernacularName"):
                    en = row["vernacularName"]
                    break
        except Exception:  # noqa: BLE001
            pass
    return sci, en or sci


def classify(quarters: Dict[str, int], season_records: int) -> str:
    """Seasonal signature → status. Residents keep ≥ ~12 % of their records in every season (a uniform bird has 25 %);
    winter visitors vanish in the monsoon, monsoon visitors vanish in winter, passage birds vanish in both.
    Calibrated on GBIF data around Raebareli (Oct 2026): residents 14–30 % in the off-season, migrants ≤ 12 %."""
    tot = sum(quarters.values())
    if tot < 20 or season_records < 3:
        return "resident"  # too little data to claim anything exotic (small samples flip randomly)
    w, sp, mo, au = (quarters.get(k, 0) / tot for k in ("winter", "spring", "monsoon", "autumn"))
    if mo <= 0.06 and w >= 0.25:
        return "winter_visitor"
    if w <= 0.06 and mo >= 0.25:
        return "monsoon_visitor"
    if w <= 0.08 and mo <= 0.08 and (sp + au) >= 0.8:
        return "passage"
    if min(w, sp, mo, au) <= 0.05 and max(w, sp, mo, au) >= 0.5:
        return "winter_visitor" if w == max(w, sp, mo, au) else ("monsoon_visitor" if mo == max(w, sp, mo, au) else "passage")
    return "resident"


_COORDS_RE = re.compile(r"[\(\[]?\s*-?\d{1,2}\.\d+\s*,\s*-?\d{1,3}\.\d+\s*[\)\]]?")
_DROP_PARTS = {"in", "india", "uttar pradesh", "up", "unnamed road", "unnamed rd", "general area", "area"}


def clean_locality(name: Optional[str]) -> Optional[str]:
    """eBird/iNat locality strings → something a person would say ("Bheetha Near Jagdishpur-26.13, 81.438" → "Bheetha near Jagdishpur")."""
    if not name:
        return None
    s = _COORDS_RE.sub(" ", name)
    parts = [p.strip(" -–—_.") for p in re.split(r"[,;/]|--", s)]
    parts = [p for p in parts if p and p.lower() not in _DROP_PARTS and not re.fullmatch(r"[\d\s.\-]+", p)]
    parts = [p for i, p in enumerate(parts) if p.lower() not in {q.lower() for q in parts[:i]}]  # dedupe
    out = ", ".join(parts[:2]).strip()
    out = re.sub(r"\s+", " ", out).replace(" Near ", " near ")
    return out[:48] or None


def _hotspots(lat: float, lon: float, radius_km: int, months: List[Tuple[int, int]], n_fetch: int = 300) -> List[Hotspot]:
    """Cluster recent seasonal records on a ~2 km grid → where people actually see birds here."""
    params: list = [
        ("taxonKey", AVES), ("geoDistance", f"{lat},{lon},{radius_km}km"), ("hasCoordinate", "true"),
        ("limit", n_fetch), ("year", "2018,2026"),
    ] + _month_params(months)
    try:
        data = _get("/occurrence/search", params)
    except Exception:  # noqa: BLE001
        return []
    grid: Dict[Tuple[int, int], List[dict]] = defaultdict(list)
    for occ in data.get("results", []):
        la, lo = occ.get("decimalLatitude"), occ.get("decimalLongitude")
        if la is None or lo is None:
            continue
        grid[(int(la / 0.02), int(lo / 0.02))].append(occ)  # 0.02° ≈ 2 km
    spots = []
    for cell, occs in sorted(grid.items(), key=lambda kv: -len(kv[1]))[:5]:
        la = sum(o["decimalLatitude"] for o in occs) / len(occs)
        lo = sum(o["decimalLongitude"] for o in occs) / len(occs)
        names = Counter((o.get("locality") or o.get("verbatimLocality") or "").strip() for o in occs)
        names.pop("", None)
        spots.append(Hotspot(round(la, 4), round(lo, 4), len(occs), clean_locality(names.most_common(1)[0][0]) if names else None,
                             round(km_between(lat, lon, la, lo), 1)))
    return spots


def hotspots_near(lat: float, lon: float, months: List[Tuple[int, int]], min_records: int = 20) -> Tuple[List[Hotspot], int]:
    """Smallest radius whose recent seasonal records are enough to cluster."""
    for r in RADII_KM:
        spots = _hotspots(lat, lon, r, months)
        if sum(h.records for h in spots) >= min_records or r == RADII_KM[-1]:
            return spots, r
    return [], RADII_KM[-1]


def _datasets(lat: float, lon: float, radius_km: int) -> List[Tuple[str, int]]:
    try:
        data = _get("/occurrence/search", [("taxonKey", AVES), ("geoDistance", f"{lat},{lon},{radius_km}km"),
                                           ("limit", 0), ("facet", "datasetKey"), ("facetLimit", 3)])
        out = []
        for c in (data.get("facets") or [{}])[0].get("counts", []):
            title = _get(f"/dataset/{c['name']}", {}).get("title", c["name"])
            out.append((title, int(c["count"])))
        return out
    except Exception:  # noqa: BLE001
        return []


def km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


# ----------------------------------------------------------------------------- public API
def nearby(lat: float, lon: float, month: int, max_species: int = MAX_SPECIES) -> Survey:
    """Survey the birds recorded around (lat, lon) in the ±1-month window around `month`.

    Widens the search radius (25 → 50 → 100 km) until there is enough data to be useful — and says which."""
    season = season_months(month)

    radius, n_season, season_counts = RADII_KM[-1], 0, {}
    for r in RADII_KM:
        n_season, season_counts = _facet_species(lat, lon, r, season)
        radius = r
        if n_season >= ENOUGH:
            break

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(8) as ex:  # the remaining calls are independent → run them together
        f_year = ex.submit(_facet_species, lat, lon, radius, None)
        f_q = {q: ex.submit(_facet_species, lat, lon, radius, _quarter_ranges(q)) for q in QUARTERS}
        f_local = None if radius == LOCAL_KM else ex.submit(_facet_species, lat, lon, LOCAL_KM, season)
        f_spots = ex.submit(hotspots_near, lat, lon, season)
        f_sets = ex.submit(_datasets, lat, lon, radius)
        n_year, year_counts = f_year.result()
        quarter_counts = {q: f.result()[1] for q, f in f_q.items()}
        n_local, local_counts = (n_season, season_counts) if f_local is None else f_local.result()
        spots, spot_radius = f_spots.result()
        datasets = f_sets.result()

    top = [k for k, _ in sorted(season_counts.items(), key=lambda kv: -kv[1])[:max_species]]
    names = species_names(top)
    species: List[Species] = []
    for key in top:
        n = season_counts[key]
        q = {qn: quarter_counts[qn].get(key, 0) for qn in QUARTERS}
        sci, en = names.get(key, (str(key), str(key)))
        species.append(Species(key, sci, en, n, year_counts.get(key, n), q, classify(q, n), local_counts.get(key, 0)))

    return Survey(
        lat=lat, lon=lon, month=month, radius_km=radius,
        season_records=n_season, year_records=n_year,
        species=species, hotspots=spots, hotspot_radius_km=spot_radius,
        datasets=datasets, local_records=n_local,
    )


def pick_for_card(survey: Survey, n_easy: int = 3, n_visitors: int = 3) -> Tuple[List[Species], List[Species]]:
    """Three easy neighbours (most-recorded residents, locally confirmed first) + three seasonal visitors."""
    cool = survey.month in (10, 11, 12, 1, 2, 3)
    order = ["winter_visitor", "passage", "monsoon_visitor"] if cool else ["monsoon_visitor", "passage", "winter_visitor"]

    def rank(sp: Species):
        return (order.index(sp.status) if sp.status in order else 9, -(sp.local_records > 0), -sp.season_records)

    easy = sorted(survey.residents, key=rank)[:n_easy]
    visitors = sorted(survey.visitors, key=rank)[:n_visitors]
    if len(visitors) < n_visitors:  # keep the card full: next-best residents the user hasn't got yet
        extra = [sp for sp in sorted(survey.residents, key=rank) if sp not in easy]
        visitors += extra[: n_visitors - len(visitors)]
    return easy, visitors


if __name__ == "__main__":  # quick manual probe: python birds.py 26.2087 81.2186 10
    import sys

    la, lo, mo = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3])
    t0 = time.time()
    s = nearby(la, lo, mo)
    print(f"radius {s.radius_km} km · {s.season_records} seasonal / {s.year_records} all-year records · {len(s.species)} species · {time.time() - t0:.1f}s")
    for sp in s.species[:40]:
        q = sp.quarter_shares
        print(f"  {sp.season_records:4d}/{sp.year_records:<5d} local={sp.local_records:<3d} W{q['winter']:.2f} S{q['spring']:.2f} M{q['monsoon']:.2f} A{q['autumn']:.2f} {sp.status:15s} {sp.english} ({sp.scientific})")
    easy, vis = pick_for_card(s)
    print("card:", [x.english for x in easy], "+", [x.english for x in vis])
    print(f"hotspots (within {s.hotspot_radius_km} km):", [(h.records, h.name, h.km) for h in s.hotspots])
    print("visitors:", [(x.english, x.status) for x in s.visitors])
    print("datasets:", s.datasets)
