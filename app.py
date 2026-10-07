"""Pakshi Padosi (पक्षी पड़ोसी) — a 60-second card of the birds actually recorded near you this month.

Open data decides which birds (GBIF: eBird + iNaturalist records), Open-Meteo decides when, and the
open-weight model (Gemma) only explains — in Hinglish, by eye, no camera, no mic. Then you put the phone
away and go. Built for Hacktoberfest 2026 Week 1: Touch Grass.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

_env = Path(__file__).with_name(".env")  # tiny .env loader (no python-dotenv dependency)
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

import gradio as gr  # noqa: E402
from fastapi import FastAPI  # noqa: E402

import birds  # noqa: E402
import llm  # noqa: E402
import names  # noqa: E402
import places  # noqa: E402
import prompts as P  # noqa: E402
import sky  # noqa: E402

llm.MOCK_HANDLER = P.mock_reply
TOWN_DEFAULT = os.getenv("TOWN_DEFAULT", "Raebareli")
TOWN_COORDS = places.parse_coords(os.getenv("TOWN_COORDS", ""))  # e.g. "26.2087, 81.2186" — default town needs no geocoder
REPO_URL = os.getenv("REPO_URL", "https://github.com/Yuser00123/pakshi-padosi")
STARTED = time.time()
N_BIRDS = 6

STATUS_HI = {"resident": "padosi (saal bhar yahin)", "winter_visitor": "sardi ka mehmaan (Oct–Feb)",
             "monsoon_visitor": "barsaat ka mehmaan (ab ja raha hai)", "passage": "raaste ka musafir (passage)"}
TAG = {"resident": "🏠", "winter_visitor": "🧳", "monsoon_visitor": "🌧️", "passage": "➡️"}


# ----------------------------------------------------------------------------- data → context
def resolve_place(text: str) -> places.Place:
    text = (text or "").strip() or TOWN_DEFAULT
    coords = places.parse_coords(text)
    if coords:
        return places.reverse(*coords)
    if TOWN_COORDS and text.lower() == TOWN_DEFAULT.lower():
        return places.Place(TOWN_COORDS[0], TOWN_COORDS[1], TOWN_DEFAULT, TOWN_DEFAULT)
    place = places.geocode(text)
    if not place:
        raise ValueError(f"'{text}' map par nahi mila. Sheher ka naam ya '26.21, 81.22' jaise coordinates likho.")
    return place


def build_context(place: places.Place, minutes: int, when: str) -> Dict:
    month = datetime.now().month
    survey = birds.nearby(place.lat, place.lon, month)
    if not survey.species:
        raise ValueError("Is jagah ke aas-paas GBIF me koi bird record nahi mila (100 km tak). Koi bada sheher try karo.")
    weather = sky.forecast(place.lat, place.lon, "kal" if when.startswith("kal") else "abhi", minutes)
    easy, visitors = birds.pick_for_card(survey)

    def pack(sp: birds.Species) -> Dict:
        dev, roman, src = names.hindi(sp.scientific)
        return {
            "en": sp.english, "sci": sp.scientific, "hi": names.label(sp.scientific, sp.english),
            "hi_src": src, "status": sp.status, "season_records": sp.season_records,
            "year_records": sp.year_records, "local_records": sp.local_records, "quarters": sp.quarter_shares,
        }

    best = weather.best
    return {
        "place": place.name, "lat": place.lat, "lon": place.lon, "minutes": minutes, "when": best.text,
        "window_note": best.note, "sunrise": weather.sunrise.strftime("%-I:%M %p"), "sunset": weather.sunset.strftime("%-I:%M %p"),
        "rain_day_pct": weather.rain_day_pct, "aqi_now": weather.aqi_now,
        "radius_km": survey.radius_km, "season_records": survey.season_records, "year_records": survey.year_records,
        "local_records": survey.local_records, "months": survey.months_label,
        "hotspots": [{"name": h.name or f"{h.lat}, {h.lon}", "km": h.km, "records": h.records} for h in survey.hotspots[:4]],
        "hotspot_radius_km": survey.hotspot_radius_km,
        "datasets": survey.datasets, "n_species": len(survey.species),
        "easy": [pack(s) for s in easy], "visitors": [pack(s) for s in visitors],
        "all_species": [pack(s) for s in survey.species[:40]],
        "created": datetime.now().isoformat(timespec="minutes"),
    }


def data_table(ctx: Dict) -> str:
    rows = ["| | Pakshi | Status | Records (" + ctx["months"] + ") | ≤25 km |", "|---|---|---|---|---|"]
    for b in ctx["easy"] + ctx["visitors"]:
        rows.append(f"| {TAG[b['status']]} | **{b['hi']}** | {STATUS_HI[b['status']]} | {b['season_records']} | {b['local_records']} |")
    src = ", ".join(f"{t.split(' – ')[0].split(' - ')[0]} ({n:,})" for t, n in ctx["datasets"][:2]) or "GBIF"
    return (
        "\n".join(rows)
        + f"\n\n<small>📊 {ctx['season_records']:,} bird records within **{ctx['radius_km']} km** in {ctx['months']} "
        f"· {ctx['n_species']} species in the data, 6 on the card · {ctx['local_records']:,} records within 25 km · source: {src} via GBIF · "
        f"Hindi names: curated folk names + Wikidata</small>"
    )


# ----------------------------------------------------------------------------- Gemma → card
_DESC_CACHE: Dict[tuple, tuple] = {}  # (english, status, style) → (timestamp, description dict)
DESC_TTL = 24 * 3600
T = {  # templated lines, so the model only ever writes about birds
    "Hinglish": {
        "opening": "{place} ke {radius} km me is season {n} pakshi record hue hain — {v} sardi ke mehmaan abhi aa rahe hain, aur {e} padosi hamesha yahin the.",
        "opening_nov": "{place} ke {radius} km me is season {n} pakshi record hue hain — {e} padosi aur {v} mehmaan is card par hain.",
        "where": "Sabse paas: {spots}. Paani ka kinara + bade ped = sabse zyada chance.",
        "go": "Phone jeb me, aankhein upar — {minutes} minute.",
        "hard": "{name} — {tip}",
        "fail": "Gemma se iska description nahi mil paya — naam aur status data se hai; aankhon se dhoondho.",
    },
    "Hindi": {
        "opening": "{place} के {radius} किमी में इस मौसम {n} पक्षी दर्ज हुए हैं — {v} सर्दी के मेहमान आ रहे हैं, और {e} पड़ोसी हमेशा यहीं थे।",
        "opening_nov": "{place} के {radius} किमी में इस मौसम {n} पक्षी दर्ज हुए हैं — इस कार्ड पर {e} पड़ोसी और {v} मेहमान हैं।",
        "where": "सबसे पास: {spots}। पानी का किनारा + बड़े पेड़ = सबसे ज़्यादा संभावना।",
        "go": "फ़ोन जेब में, आँखें ऊपर — {minutes} मिनट।",
        "hard": "{name} — {tip}",
        "fail": "Gemma से इसका विवरण नहीं मिल पाया — नाम और स्थिति डेटा से है; आँखों से ढूँढो।",
    },
    "English": {
        "opening": "{n} bird species were recorded within {radius} km of {place} this season — {v} winter visitors are arriving now, and {e} residents never left.",
        "opening_nov": "{n} bird species were recorded within {radius} km of {place} this season — {e} residents and {v} visitors are on this card.",
        "where": "Nearest: {spots}. Water edge + big trees = best odds.",
        "go": "Phone in pocket, eyes up — {minutes} minutes.",
        "hard": "{name} — {tip}",
        "fail": "Gemma couldn't describe this one — name and status are from the data; look for it anyway.",
    },
}


def _describe(bird: Dict, ctx: Dict, style: str) -> Dict:
    key = (bird["en"], bird["status"], style)
    hit = _DESC_CACHE.get(key)
    if hit and time.time() - hit[0] < DESC_TTL:
        return hit[1]
    raw = llm.chat(P.bird_prompt(ctx, bird, style), json_mode=True, max_tokens=2500)
    d = llm.parse_json(raw)
    look = d.get("look") if isinstance(d.get("look"), list) else [str(d.get("look") or "")]
    desc = {
        "size": str(d.get("size") or "").strip(), "look": [str(x).strip() for x in look if str(x).strip()][:3],
        "where": str(d.get("where") or "").strip(), "sound": str(d.get("sound") or "pakka nahi").strip(),
        "status_line": str(d.get("status_line") or "").strip(), "hook": str(d.get("hook") or "").strip(),
        "tip": str(d.get("tip") or "").strip(),
    }
    if desc["size"] or desc["look"]:
        _DESC_CACHE[key] = (time.time(), desc)
    return desc


def generate_card(ctx: Dict, style: str, progress=None) -> Dict:
    """Six parallel one-bird calls; the header lines are templates filled from the data."""
    from concurrent.futures import ThreadPoolExecutor

    wanted = ctx["easy"] + ctx["visitors"]
    results: Dict[str, Dict] = {}
    errors: Dict[str, str] = {}
    with ThreadPoolExecutor(len(wanted)) as ex:
        futs = {ex.submit(_describe, b, ctx, style): b for b in wanted}
        for fut, b in futs.items():
            try:
                results[b["en"]] = fut.result()
            except Exception as err:  # noqa: BLE001
                errors[b["en"]] = str(err)[:120]
            if progress:
                progress(len(results) + len(errors))
    t = T.get(style, T["Hinglish"])
    birds_out = []
    for b in wanted:
        d = results.get(b["en"]) or {"size": "", "look": [], "where": "", "sound": "pakka nahi", "status_line": "", "hook": t["fail"], "tip": ""}
        birds_out.append({
            "en": b["en"], "hi": b["hi"], "status": b["status"], "tag": "padosi" if b["status"] == "resident" else "mehmaan",
            **{k: d[k] for k in ("size", "look", "where", "sound", "hook", "tip")},
            "status_line": d["status_line"] or STATUS_HI[b["status"]],
            "season_records": b["season_records"], "local_records": b["local_records"],
        })
    n_v = sum(1 for b in wanted if b["status"] != "resident")
    opening = t["opening" if ctx["visitors"] and any(b["status"] == "winter_visitor" for b in ctx["visitors"]) else "opening_nov"].format(
        place=ctx["place"].split(",")[0], radius=ctx["radius_km"], n=ctx["n_species"], v=n_v, e=len(wanted) - n_v)
    spots = ", ".join(f"{h['name']} ({h['km']} km)" for h in ctx["hotspots"][:3]) or "paas ka talaab ya nadi"
    hard = min((b for b in birds_out if b["tag"] == "mehmaan"), key=lambda b: (b["local_records"], b["season_records"]), default=birds_out[-1])
    return {
        "opening": opening, "birds": birds_out,
        "where_to_go": t["where"].format(spots=spots), "go_line": t["go"].format(minutes=ctx["minutes"]),
        "hard_one": t["hard"].format(name=hard["hi"], tip=hard["tip"]) if hard.get("tip") else "",
        "errors": errors, "place": ctx["place"], "when": ctx["when"], "minutes": ctx["minutes"],
        "lat": ctx["lat"], "lon": ctx["lon"], "created": ctx["created"],
    }


def _validate_card(raw: str, ctx: Dict) -> Dict:
    data = llm.parse_json(raw)
    wanted = ctx["easy"] + ctx["visitors"]
    by_en = {b["en"].lower(): b for b in (data.get("birds") or []) if isinstance(b, dict) and b.get("en")}
    out = []
    for b in wanted:  # keep OUR order and OUR names; take only the model's descriptions
        m = by_en.get(b["en"].lower(), {})
        look = m.get("look") if isinstance(m.get("look"), list) else [str(m.get("look") or "")]
        out.append({
            "en": b["en"], "hi": b["hi"], "status": b["status"], "tag": "padosi" if b["status"] == "resident" else "mehmaan",
            "size": str(m.get("size") or "").strip(), "look": [str(x).strip() for x in look if str(x).strip()][:3],
            "where": str(m.get("where") or "").strip(), "sound": str(m.get("sound") or "pakka nahi").strip(),
            "status_line": str(m.get("status_line") or STATUS_HI[b["status"]]).strip(), "hook": str(m.get("hook") or "").strip(),
            "season_records": b["season_records"], "local_records": b["local_records"],
        })
    return {
        "opening": str(data.get("opening") or "").strip(), "birds": out,
        "where_to_go": str(data.get("where_to_go") or "").strip(), "go_line": str(data.get("go_line") or "Phone jeb me, aankhein upar.").strip(),
        "hard_one": str(data.get("hard_one") or "").strip(), "place": ctx["place"], "when": ctx["when"], "minutes": ctx["minutes"],
        "lat": ctx["lat"], "lon": ctx["lon"], "created": ctx["created"],
    }


def render_card(card: Dict, ctx: Dict) -> str:
    L = [f"## 🪶 Aaj dhoondho — {card['place']}", f"**🕰 {card['when']}** · {ctx['minutes']} min · {ctx['window_note']}", ""]
    if card["opening"]:
        L += [f"*{card['opening']}*", ""]
    for i, b in enumerate(card["birds"], 1):
        L.append(f"### {i}. {b['hi']} {TAG[b['status']]}")
        bits = []
        if b["size"]:
            bits.append(f"**Size:** {b['size']}")
        for mark in b["look"]:
            bits.append(f"👀 {mark}")
        if b["where"]:
            bits.append(f"📍 {b['where']}")
        if b["sound"] and b["sound"].lower() != "pakka nahi":
            bits.append(f"🔊 {b['sound']}")
        bits.append(f"<small>{b['status_line']} · {b['season_records']} records</small>")
        if b["hook"]:
            bits.append(f"💡 *{b['hook']}*")
        L += ["  \n".join(bits), ""]
    if card["where_to_go"]:
        L += [f"**🗺 Kahan jaayein:** {card['where_to_go']}", ""]
    if card["hard_one"]:
        L += [f"**🎯 Sabse mushkil:** {card['hard_one']}", ""]
    L += [f"### 📵 {card['go_line']}", ""]
    return "\n".join(L)


def _poll(fn, label: str, prefix: str):
    """Run fn in a thread; yield prefix + a live timer until it finishes (Gemma thinks for 20–60 s)."""
    box: Dict = {}

    def work():
        try:
            box["ok"] = fn()
        except Exception as err:  # noqa: BLE001
            box["err"] = err

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t0 = time.time()
    while t.is_alive():
        t.join(1.0)
        yield None, prefix + f"\n\n🤔 *{label}… {int(time.time() - t0)}s* — tab tak upar ka data padho."
    if "err" in box:
        raise box["err"]
    yield box["ok"], None


def do_card(place_text, minutes, when, style, store):
    """Generator: data instantly, then Gemma's card. Outputs: card_md, checklist, store."""
    store = dict(store or {})
    checklist = gr.CheckboxGroup(choices=[], value=[])
    try:
        yield "📍 Jagah dhoondh raha hoon…", checklist, store
        place = resolve_place(place_text)
        yield f"📊 **{place.name}** — GBIF se records aur mausam la raha hoon…", checklist, store
        ctx = build_context(place, int(minutes), when)
    except Exception as err:  # noqa: BLE001
        yield f"⚠️ {err}", checklist, store
        return

    table = data_table(ctx)
    head = f"## 🪶 {ctx['place']} · {ctx['when']}\n\n{table}"
    done = {"n": 0}
    card = None
    try:
        for result, status in _poll(lambda: generate_card(ctx, style, progress=lambda n: done.update(n=n)), "Gemma likh raha hai", head):
            if status:
                yield status.replace("Gemma likh raha hai", f"Gemma {done['n']}/{N_BIRDS} pakshi likh chuka"), checklist, store
            else:
                card = result
    except llm.LLMError as err:
        yield head + f"\n\n⚠️ {err}", checklist, store
        return
    except Exception as err:  # noqa: BLE001
        yield head + f"\n\n⚠️ Card nahi ban paya: {str(err)[:200]}", checklist, store
        return

    store["card"], store["ctx"] = card, ctx
    choices = [b["hi"] for b in card["birds"]]
    yield render_card(card, ctx) + "\n\n<details><summary>📊 Data (kahan se aaya)</summary>\n\n" + table + "\n\n</details>", \
        gr.CheckboxGroup(choices=choices, value=[]), store


# ----------------------------------------------------------------------------- diary
def diary_stats(diary: List[Dict]) -> str:
    if not diary:
        return "Abhi koi sair nahi. Card banao, bahar jao, wapas aake tick karo."
    mins = sum(int(d.get("minutes") or 0) for d in diary)
    seen = {s for d in diary for s in d.get("seen", [])}
    return f"**{len(diary)}** sair · **{mins}** minute bahar · **{len(seen)}** alag pakshi dekhe"


def diary_rows(diary: List[Dict]) -> List[List]:
    return [[d["date"], d["place"], d.get("minutes", ""), len(d.get("seen", [])), ", ".join(d.get("seen", []))[:80]] for d in reversed(diary)]


def do_diary(seen, minutes, note, style, store):
    store = dict(store or {})
    card = store.get("card")
    if not card:
        return "⚠️ Pehle card banao aur bahar ja ke aao.", diary_stats(store.get("diary", [])), diary_rows(store.get("diary", [])), store
    seen = list(seen or [])
    seen_en = [b["en"] for b in card["birds"] if b["hi"] in seen]
    try:
        text = llm.chat(P.diary_prompt(card, seen_en, int(minutes or 0), note or "", style), max_tokens=1200)
    except llm.LLMError as err:
        text = f"(Gemma se nahi likhwa paye: {err})"
    entry = {
        "date": datetime.now().strftime("%d %b %Y %H:%M"), "place": card["place"], "lat": card["lat"], "lon": card["lon"],
        "minutes": int(minutes or 0), "seen": seen, "seen_en": seen_en, "note": note or "", "text": text,
        "card_birds": [b["en"] for b in card["birds"]],
    }
    store["diary"] = (store.get("diary") or []) + [entry]
    return f"### ✍️ Diary — {entry['date']}\n\n{text}", diary_stats(store["diary"]), diary_rows(store["diary"]), store


def export_md(store):
    diary = (store or {}).get("diary") or []
    lines = ["# 🪶 Pakshi Diary", ""]
    for d in reversed(diary):
        lines += [f"## {d['date']} — {d['place']} ({d['minutes']} min)", f"Dekha: {', '.join(d['seen']) or '—'}", "", d["text"], ""]
        if d.get("note"):
            lines += [f"> {d['note']}", ""]
    path = os.path.join(tempfile.gettempdir(), "pakshi-diary.md")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return path


def export_ebird(store):
    """eBird Record Format (no header row): one line per bird seen, so your walk becomes open data too."""
    diary = (store or {}).get("diary") or []
    buf = io.StringIO()
    w = csv.writer(buf)
    for d in diary:
        try:
            dt = datetime.strptime(d["date"], "%d %b %Y %H:%M")
        except ValueError:
            dt = datetime.now()
        for en in d.get("seen_en", []):
            w.writerow([en, "", "", "X", "", d["place"], d.get("lat", ""), d.get("lon", ""), dt.strftime("%m/%d/%Y"),
                        dt.strftime("%H:%M"), "", "IN", "Traveling", 1, d.get("minutes", ""), "Y", "", "", "Pakshi Padosi walk"])
    path = os.path.join(tempfile.gettempdir(), "pakshi-ebird.csv")
    Path(path).write_text(buf.getvalue(), encoding="utf-8")
    return path


def restore(store):
    """On page load: bring back the last card + diary from the browser (works offline once cached)."""
    store = store or {}
    card, ctx, diary = store.get("card"), store.get("ctx"), store.get("diary") or []
    if card and ctx:
        md = render_card(card, ctx) + "\n\n<details><summary>📊 Data (kahan se aaya)</summary>\n\n" + data_table(ctx) + "\n\n</details>"
        checklist = gr.CheckboxGroup(choices=[b["hi"] for b in card["birds"]], value=[])
    else:
        md, checklist = "", gr.CheckboxGroup(choices=[], value=[])
    return md, checklist, diary_stats(diary), diary_rows(diary)


# ----------------------------------------------------------------------------- UI
CSS = """
#title h1 { font-size: 1.7rem; margin-bottom: 0; }
.gradio-container { max-width: 760px !important; margin: auto; }
#card { font-size: 1.05rem; line-height: 1.55; }
#card h3 { margin: 1.1rem 0 0.3rem; }
#field .wrap label { font-size: 1.35rem !important; padding: 0.8rem 1rem !important; }
#field { font-size: 1.2rem; }
button.lg { min-height: 56px; font-size: 1.1rem; }
@media print {
  .no-print, footer, .tabs > .tab-nav, #setup, button, details { display: none !important; }
  #card { font-size: 12pt; }
  .gradio-container { max-width: 100% !important; }
}
"""
GPS_JS = """async (cur) => {
  try {
    const p = await new Promise((ok, no) => navigator.geolocation.getCurrentPosition(ok, no, {enableHighAccuracy: true, timeout: 12000}));
    return p.coords.latitude.toFixed(4) + ', ' + p.coords.longitude.toFixed(4);
  } catch (e) { alert('GPS nahi mila — sheher ka naam likh do.'); return cur; }
}"""

with gr.Blocks(title="Pakshi Padosi") as demo:
    store = gr.BrowserState({"card": None, "ctx": None, "diary": []}, storage_key="pakshi-padosi-v1")
    gr.Markdown(
        "# 🪶 Pakshi Padosi\n"
        "Jo pakshi **sach me** tumhare aas-paas is mahine dikhe hain (GBIF open data), unka 60-second Hinglish card — "
        "**Gemma** samjhata hai, phir phone jeb me aur bahar. Na camera, na mic. Sirf aankhein.",
        elem_id="title",
    )
    with gr.Tabs() as tabs:
        with gr.Tab("🪶 Card", id="card"):
            with gr.Group(elem_id="setup"):
                with gr.Row():
                    place_box = gr.Textbox(label="📍 Kahan ho?", value=TOWN_DEFAULT, placeholder="Sheher / mohalla, ya 26.21, 81.22", scale=4)
                    gps_btn = gr.Button("📡 GPS", scale=1)
                with gr.Row():
                    minutes = gr.Radio(P.MINUTES, value=40, label="⏱ Kitna time? (min)")
                    when = gr.Radio(["abhi / aaj", "kal subah"], value="abhi / aaj", label="🕰 Kab?")
                    style = gr.Radio(P.STYLES, value="Hinglish", label="🗣 Bhasha")
                go_btn = gr.Button("Card banao 🪶", variant="primary", elem_classes=["lg"])
            card_md = gr.Markdown(elem_id="card")
            with gr.Row(elem_classes=["no-print"]):
                print_btn = gr.Button("🖨 Print / PDF save karo")
                out_btn = gr.Button("📵 Bahar chalo →", variant="primary")
        with gr.Tab("📵 Bahar", id="field", elem_id="field"):
            gr.Markdown("### Wapas aa gaye? Jo dikha, tick karo.")
            checklist = gr.CheckboxGroup(choices=[], label="Kaun dikha?")
            with gr.Row():
                mins_out = gr.Number(value=40, label="Kitne minute bahar rahe?", precision=0)
                note = gr.Textbox(label="Ek line note (optional)", placeholder="e.g. talaab par 3 dhobin thi, ek titahri chillayi")
            diary_btn = gr.Button("Diary me likho ✍️", variant="primary", elem_classes=["lg"])
            diary_out = gr.Markdown()
        with gr.Tab("📓 Diary", id="diary"):
            stats_md = gr.Markdown(diary_stats([]))
            diary_df = gr.Dataframe(headers=["Kab", "Kahan", "Min", "Kitne", "Kaun"], interactive=False, wrap=True)
            with gr.Row():
                md_btn = gr.DownloadButton("⬇️ Diary (.md)")
                ebird_btn = gr.DownloadButton("⬇️ eBird CSV (apni sightings open data banao)")
            gr.Markdown("<small>Diary sirf is browser me rehti hai (koi account, koi server-side storage nahi). "
                        "eBird CSV ko ebird.org → Submit → Import data me upload kar sakte ho.</small>")

    gps_btn.click(None, inputs=[place_box], outputs=[place_box], js=GPS_JS)
    go_btn.click(do_card, inputs=[place_box, minutes, when, style, store], outputs=[card_md, checklist, store])
    print_btn.click(None, js="() => window.print()")
    out_btn.click(lambda: gr.Tabs(selected="field"), outputs=[tabs])
    diary_btn.click(do_diary, inputs=[checklist, mins_out, note, style, store], outputs=[diary_out, stats_md, diary_df, store])
    md_btn.click(export_md, inputs=[store], outputs=[md_btn])
    ebird_btn.click(export_ebird, inputs=[store], outputs=[ebird_btn])
    demo.load(restore, inputs=[store], outputs=[card_md, checklist, stats_md, diary_df])

    gr.Markdown(
        f"<small>Model: **{llm.describe()}** · Birds: GBIF (eBird, iNaturalist) · Weather/AQI: Open-Meteo · Map: OpenStreetMap · "
        f"Hindi names: curated + Wikidata · Tumhari location sirf in open APIs tak jaati hai, kahin save nahi hoti · "
        f"<a href='{REPO_URL}'>Source</a> · Hacktoberfest 2026 · Touch Grass</small>",
        elem_classes=["no-print"],
    )

api = FastAPI(title="Pakshi Padosi")


@api.get("/health")
def health():
    return {"status": "ok", "service": "pakshi-padosi", "model": llm.describe(), "uptime_seconds": int(time.time() - STARTED)}


app = gr.mount_gradio_app(api, demo, path="/", theme=gr.themes.Soft(primary_hue="green", secondary_hue="amber"), css=CSS, pwa=True)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
