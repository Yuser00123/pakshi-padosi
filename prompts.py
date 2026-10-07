"""Prompts for Pakshi Padosi. The species list is INPUT to the model, never output.

Gemma's job is narrow on purpose: turn a data-grounded list of birds into a card a 15-year-old in
Raebareli can use with their eyes. It may not add species, may not invent Hindi names, and must say
"pata nahi" when it doesn't know a field mark.
"""
from __future__ import annotations

import json
from typing import Dict, List

STYLES = ["Hinglish", "Hindi", "English"]
MINUTES = [20, 40, 60]

SYSTEM = """You are Pakshi Padosi, a warm, precise birding friend from the Gangetic plain of India.
You write SHORT field cards for beginners who will read them once, put the phone away, and go outside.

Language rules
- "Hinglish": Roman-script Hindi mixed with English, the way friends talk on WhatsApp. Technical words stay in English.
- "Hindi": Devanagari Hindi, simple words. "English": plain English.
- Never translate bird names yourself. Use the Hindi name exactly as given in the data. If the data says
  "Hindi naam pakka nahi", keep the English name and say the Hindi name is not confirmed.

Honesty rules
- Only describe the species given to you. Never add, swap or "upgrade" a bird. Never invent rarity or numbers.
- Field marks must be things visible WITHOUT binoculars at 10–30 m: size compared to a sparrow/myna/crow/kite,
  colour blocks, tail/head shape, how it moves, where it sits. One sound cue in words, if you are confident.
- If you are not sure of a field mark, write "pakka nahi" instead of guessing.
- Status lines must follow the data: a "winter_visitor" is here only in the cool months (say where such birds
  usually come from only if you are sure, e.g. Himalaya/Central Asia); a "monsoon_visitor" is leaving now; a
  "resident" lives here all year; "passage" is passing through.
- The best screen is the shortest one. No preambles, no emojis inside field marks, no markdown in JSON strings.
"""


def card_prompt(ctx: Dict, style: str, minutes: int) -> List[dict]:
    """ctx = {place, when, window_note, sky, radius_km, season_records, months, hotspots[], easy[], visitors[]}"""
    birds = ctx["easy"] + ctx["visitors"]
    schema = {
        "opening": "ONE sentence: why this walk, today, here (use the season and the visitors).",
        "birds": [
            {
                "en": "exact English name from the data",
                "hi": "exact Hindi label from the data (or 'Hindi naam pakka nahi')",
                "tag": "padosi | mehmaan",
                "size": "compared to gauraiya/maina/kauwa/cheel, max 8 words",
                "look": ["field mark 1 (max 10 words)", "field mark 2 (max 10 words)"],
                "where": "where to look: paani/ped/taar/zameen/aasmaan + a habit, max 12 words",
                "sound": "one call cue in words, or 'pakka nahi'",
                "status_line": "one short line from the data (status, when it is here)",
                "hook": "one memorable line to recognise it (max 14 words)",
            }
        ],
        "where_to_go": "ONE sentence using the hotspot names and distances given (closest first).",
        "go_line": "ONE short send-off line, e.g. 'Phone jeb me, aankhein upar — 40 minute.'",
        "hard_one": "name the single hardest bird on this card to find and ONE tip (max 20 words)",
    }
    data = {
        "language": style,
        "minutes": minutes,
        "place": ctx["place"],
        "when": ctx["when"],
        "sky_note": ctx.get("window_note", ""),
        "season": ctx.get("months", ""),
        "data_basis": f"{ctx['season_records']} records within {ctx['radius_km']} km, GBIF (eBird/iNaturalist)",
        "hotspots": ctx.get("hotspots", []),
        "birds": [
            {
                "en": b["en"], "hi": b["hi"], "tag": "padosi" if b["status"] == "resident" else "mehmaan",
                "status": b["status"], "season_records": b["season_records"],
                "seen_within_25km": b["local_records"],
            }
            for b in birds
        ],
    }
    user = (
        f"Write the field card as JSON with exactly this shape (keys and order), {len(birds)} birds in the SAME order as given:\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=1)}\n\n"
        f"DATA (the only birds you may mention):\n{json.dumps(data, ensure_ascii=False, indent=1)}\n\n"
        "Return ONLY the JSON object."
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def bird_prompt(ctx: Dict, bird: Dict, style: str) -> List[dict]:
    """ONE bird per call — six small parallel calls finish in the time one big one spends thinking."""
    schema = {
        "size": "compared to gauraiya/maina/kauwa/cheel, max 8 words",
        "look": ["most diagnostic field mark, max 10 words", "second field mark, max 10 words"],
        "where": "where to look: paani/ped/taar/zameen/aasmaan + a habit, max 12 words",
        "sound": "one call cue in words, or 'pakka nahi'",
        "status_line": "one short line in the chosen language that restates the given status (no new facts)",
        "hook": "one memorable line to recognise it, max 14 words",
        "tip": "if this bird is hard to find, ONE tip, max 16 words",
    }
    data = {
        "language": style, "place": ctx["place"], "season": ctx.get("months", ""),
        "bird": {"en": bird["en"], "scientific": bird.get("sci", ""), "hindi_label": bird["hi"], "status": bird["status"],
                 "records_this_season_nearby": bird["season_records"], "seen_within_25km": bird["local_records"]},
    }
    user = (
        "Describe ONLY this one bird for a beginner who will look for it with bare eyes. "
        f"Return JSON with exactly these keys:\n{json.dumps(schema, ensure_ascii=False, indent=1)}\n\n"
        f"DATA:\n{json.dumps(data, ensure_ascii=False, indent=1)}\n\nReturn ONLY the JSON object."
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def diary_prompt(card: Dict, seen: List[str], minutes: int, note: str, style: str) -> List[dict]:
    birds = [b["en"] for b in card.get("birds", [])]
    unseen = [b for b in birds if b not in seen]
    user = (
        f"Language: {style}.\n"
        f"The walk: {minutes} minutes outside at {card.get('place', 'the usual place')}.\n"
        f"Card birds: {birds}\nSeen (ticked by the person): {seen or ['none']}\nNot seen: {unseen}\n"
        f"Their note: {note.strip() or '(no note)'}\n\n"
        "Write a diary entry in markdown, max 90 words total:\n"
        "- Line 1: what they saw, warmly, no exaggeration (if nothing was seen, that is normal; say why mornings/evenings help).\n"
        "- Line 2: one sentence that reacts to their note (if any) with one real fact about a bird they mention.\n"
        "- Line 3: 'Kal ka ek pakshi:' — pick ONE bird from 'Not seen' and give ONE tip to find it.\n"
        "No headings, no emojis, no invented species."
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


# ----------------------------------------------------------------------------- mock (no API key)
def mock_reply(messages: List[dict], json_mode: bool) -> str:
    """Deterministic offline replies so the UI, tests and screenshots work without a model."""
    user = messages[-1]["content"]
    if json_mode and user.startswith("Describe ONLY this one bird"):
        data = json.loads(user.split("DATA:\n", 1)[1].rsplit("\n\nReturn ONLY", 1)[0])
        b = data["bird"]
        return json.dumps({
            "size": "(mock) maina jitna", "look": ["(mock) rang/pattern yahan", "(mock) poonchh/sir ka shape"],
            "where": "(mock) paani ke kinare ya taar par", "sound": "pakka nahi",
            "status_line": f"(mock) {b['status']}", "hook": "(mock) Gemma connect hoga to asli hook yahan aayega",
            "tip": "(mock) subah jaldi jao",
        }, ensure_ascii=False)
    if json_mode and '"DATA' in user or "DATA (the only birds" in user:
        data = json.loads(user.split("DATA (the only birds you may mention):\n", 1)[1].rsplit("\n\nReturn ONLY", 1)[0])
        birds = []
        for b in data["birds"]:
            birds.append({
                "en": b["en"], "hi": b["hi"], "tag": b["tag"],
                "size": "(mock) maina jitna", "look": ["(mock) rang/pattern yahan", "(mock) poonchh/sir ka shape"],
                "where": "(mock) paani ke kinare ya taar par", "sound": "pakka nahi",
                "status_line": f"(mock) data: {b['status']}, {b['season_records']} records",
                "hook": "(mock) Gemma connect hoga to asli hook yahan aayega",
            })
        return json.dumps({
            "opening": f"(mock) {data['place']} me aaj {len(birds)} pakshi dhoondhne ka din hai — LLM_API_KEY set karo to Gemma asli card likhega.",
            "birds": birds,
            "where_to_go": "(mock) " + (data["hotspots"][0]["name"] if data.get("hotspots") else "paas ka talaab"),
            "go_line": "Phone jeb me, aankhein upar.",
            "hard_one": "(mock) sabse mushkil: aakhri wala.",
        }, ensure_ascii=False)
    return "(mock) Aaj ki sair diary me likh li. Kal ka ek pakshi: card ka pehla wala — subah 6 baje paani ke paas dekho."
