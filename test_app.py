"""Offline tests: python test_app.py   (no API key, no network — uses recorded GBIF/Open-Meteo fixtures)

Covers: season maths, the migrant classifier (calibrated on real Raebareli data), card validation
(the model cannot add birds or rename them), Hindi-name trust order, and the eBird export.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["LLM_PROVIDER"] = "mock"
sys.path.insert(0, str(Path(__file__).parent))

import app  # noqa: E402
import birds  # noqa: E402
import names  # noqa: E402
import prompts as P  # noqa: E402

FIX = Path(__file__).parent / "tests" / "fixtures"


def test_season_maths():
    assert birds.season_months(10) == [(9, 11)]
    assert birds.season_months(12) == [(11, 12), (1, 1)]
    assert birds.season_months(1) == [(12, 12), (1, 2)]
    assert birds._quarter_ranges("winter") == [(12, 12), (1, 2)]


def test_classifier_on_real_signatures():
    # numbers recorded from GBIF within 50 km of Raebareli, Oct 2026
    assert birds.classify({"winter": 38, "spring": 22, "monsoon": 16, "autumn": 23}, 21) == "resident"      # Laughing Dove
    assert birds.classify({"winter": 10, "spring": 7, "monsoon": 0, "autumn": 12}, 12) == "winter_visitor"  # White Wagtail
    assert birds.classify({"winter": 0, "spring": 2, "monsoon": 70, "autumn": 60}, 30) == "monsoon_visitor" # Pied Cuckoo-like
    assert birds.classify({"winter": 1, "spring": 2, "monsoon": 3, "autumn": 4}, 4) == "resident"          # too little data
    assert birds.classify({"winter": 0, "spring": 20, "monsoon": 0, "autumn": 20}, 20) == "passage"


def test_card_validation_cannot_add_or_rename_birds():
    ctx = json.loads((FIX / "ctx_raebareli.json").read_text(encoding="utf-8"))
    fake = {
        "opening": "x",
        "birds": [
            {"en": "Indian Pond-Heron", "hi": "INVENTED NAME", "size": "maina se bada", "look": ["a", "b"], "where": "paani", "sound": "pakka nahi", "status_line": "s", "hook": "h"},
            {"en": "Dodo", "hi": "डोडो", "size": "", "look": [], "where": "", "sound": "", "status_line": "", "hook": ""},
        ],
        "where_to_go": "w", "go_line": "g", "hard_one": "h",
    }
    card = app._validate_card(json.dumps(fake), ctx)
    ens = [b["en"] for b in card["birds"]]
    assert "Dodo" not in ens and len(card["birds"]) == len(ctx["easy"] + ctx["visitors"])
    assert card["birds"][0]["hi"] == ctx["easy"][0]["hi"] != "INVENTED NAME"  # our name wins
    assert card["birds"][0]["size"] == "maina se bada"                        # the model's description is kept
    md = app.render_card(card, ctx)
    assert "Aaj dhoondho" in md and "Dodo" not in md


def test_hindi_name_trust_order():
    dev, roman, src = names.hindi("Vanellus indicus")
    assert dev == "टिटहरी" and src == "curated"          # Wikidata has a transliteration; curated wins
    assert names.hindi("Oriolus xanthornus")[2] in ("none", "wikidata", "hi.wikipedia")
    assert "pakka nahi" in names.label("Nonexistus birdus", "Nonexistent Bird")


def test_prompt_only_contains_our_birds():
    ctx = json.loads((FIX / "ctx_raebareli.json").read_text(encoding="utf-8"))
    msgs = P.card_prompt(ctx, "Hinglish", 40)
    user = msgs[-1]["content"]
    for b in ctx["easy"] + ctx["visitors"]:
        assert b["en"] in user
    assert "Return ONLY the JSON" in user


def test_mock_card_and_diary_roundtrip(monkeypatch=None):
    ctx = json.loads((FIX / "ctx_raebareli.json").read_text(encoding="utf-8"))
    raw = P.mock_reply(P.card_prompt(ctx, "Hinglish", 40), True)
    card = app._validate_card(raw, ctx)
    store = {"card": card, "ctx": ctx, "diary": []}
    seen = [card["birds"][0]["hi"]]
    md, stats, rows, store = app.do_diary(seen, 35, "ek titahri chillayi", "Hinglish", store)
    assert "Diary" in md and len(store["diary"]) == 1 and rows[0][2] == 35
    csv_text = Path(app.export_ebird(store)).read_text(encoding="utf-8")
    assert csv_text.startswith(card["birds"][0]["en"] + ",") and ",IN,Traveling,1,35,Y," in csv_text
    assert "Pakshi Diary" in Path(app.export_md(store)).read_text(encoding="utf-8")
    md2, _, stats2, _ = app.restore(store)
    assert "Aaj dhoondho" in md2 and "1** sair" in stats2


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"✅ {name}")
            except Exception as err:  # noqa: BLE001
                failed += 1
                print(f"❌ {name}: {err!r}")
    sys.exit(1 if failed else 0)
