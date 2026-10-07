"""One-shot: ask Wikidata for Hindi names of the bird species in data/species_cache.json.

    python scripts/build_hindi_names.py

Writes data/hindi_names.json  {scientific: {"hi": ..., "source": "wikidata"|"hi.wikipedia", "roman": null}}.
Uses the Hindi taxon-common-name (P1843@hi), else the Hindi label, else the Hindi Wikipedia article title.
Wikidata's query service rate-limits aggressively at times (1 req/min was observed) — this makes ONE query.
Run again whenever species_cache.json grows; existing entries are kept.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "species_cache.json")
OUT = os.path.join(ROOT, "data", "hindi_names.json")
UA = {"User-Agent": "PakshiPadosi/0.1 (+https://github.com/Yuser00123/pakshi-padosi)", "Accept": "application/sparql-results+json"}


def main() -> int:
    names = json.load(open(CACHE, encoding="utf-8"))
    sci = sorted({v[0] for v in names.values()})
    existing = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    todo = [s for s in sci if s not in existing]
    if not todo:
        print("nothing to do")
        return 0
    values = " ".join(json.dumps(s) for s in todo)
    query = f"""
SELECT ?sci ?common ?label ?title WHERE {{
  VALUES ?sci {{ {values} }}
  ?item wdt:P225 ?sci .
  OPTIONAL {{ ?item wdt:P1843 ?common FILTER(LANG(?common) = "hi") }}
  OPTIONAL {{ ?item rdfs:label ?label FILTER(LANG(?label) = "hi") }}
  OPTIONAL {{ ?article schema:about ?item ; schema:isPartOf <https://hi.wikipedia.org/> ; schema:name ?title . }}
}}"""
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers=UA)
    try:
        rows = json.load(urllib.request.urlopen(req, timeout=120))["results"]["bindings"]
    except Exception as err:  # noqa: BLE001
        print("Wikidata query failed:", err)
        return 1
    found = 0
    for b in rows:
        s = b["sci"]["value"]
        hi = b.get("common", {}).get("value") or b.get("label", {}).get("value") or b.get("title", {}).get("value")
        if not hi or s in existing:
            continue
        # Hindi labels on Wikidata are sometimes just the scientific name in Latin letters — skip those
        if not any("\u0900" <= ch <= "\u097f" for ch in hi):
            continue
        src = "wikidata" if (b.get("common") or b.get("label")) else "hi.wikipedia"
        existing[s] = {"hi": hi.split("(")[0].strip(), "roman": None, "source": src}
        found += 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(existing, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print(f"{found} new Hindi names from Wikidata; {len(existing)} total; {len(todo) - found} still missing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
