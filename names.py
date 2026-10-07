"""Hindi names for birds — from open data, not from the language model.

Order of trust:
  1. CURATED below — folk names actually used in the Gangetic plain (hand-checked; Wikidata sometimes only has
     transliterations like "ओपनबिल्ड स्टॉर्क", which nobody says)
  2. data/hindi_names.json — Wikidata / Hindi Wikipedia names built by scripts/build_hindi_names.py (fills the gaps)
  3. nothing → the card shows the English name and says "Hindi naam pakka nahi"; Gemma must NOT invent one.
"""
from __future__ import annotations

import json
import os
from typing import Optional, Tuple

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hindi_names.json")

# scientific name → (Devanagari, roman) — only names I'd say out loud to a birder in UP.
CURATED = {
    "Corvus splendens": ("कौआ", "Kauwa"),
    "Corvus macrorhynchos": ("जंगली कौआ", "Jangli kauwa"),
    "Passer domesticus": ("गौरैया", "Gauraiya"),
    "Acridotheres tristis": ("मैना", "Maina"),
    "Acridotheres ginginianus": ("गंगा मैना", "Ganga maina"),
    "Gracupica contra": ("अबलक मैना", "Ablak maina"),
    "Sturnia pagodarum": ("ब्राह्मणी मैना", "Brahmani maina"),
    "Pastor roseus": ("गुलाबी मैना", "Gulabi maina"),
    "Psittacula krameri": ("तोता", "Tota"),
    "Psittacula eupatria": ("पहाड़ी तोता", "Pahadi tota"),
    "Psittacula cyanocephala": ("टुइयाँ तोता", "Tuiyan tota"),
    "Columba livia": ("कबूतर", "Kabootar"),
    "Spilopelia chinensis": ("चितकबरी फाख्ता", "Chitkabri fakhta"),
    "Spilopelia senegalensis": ("छोटी फाख्ता / टुटरू", "Chhoti fakhta / Tutru"),
    "Streptopelia decaocto": ("पंडुक", "Panduk"),
    "Streptopelia tranquebarica": ("सुर्ख फाख्ता", "Surkh fakhta"),
    "Treron phoenicopterus": ("हरियल", "Hariyal"),
    "Pycnonotus cafer": ("बुलबुल", "Bulbul"),
    "Pycnonotus jocosus": ("सिपाही बुलबुल", "Sipahi bulbul"),
    "Turdoides striata": ("सात भाई", "Saat bhai"),
    "Argya striata": ("सात भाई", "Saat bhai"),
    "Argya caudata": ("डुमरी / छोटा सतभइया", "Dumri"),
    "Argya malcolmi": ("बड़ा सतभइया / गंगई", "Gangai"),
    "Dicrurus macrocercus": ("भुजंगा / कोतवाल", "Bhujanga / Kotwal"),
    "Milvus migrans": ("चील", "Cheel"),
    "Elanus caeruleus": ("कपासी", "Kapasi"),
    "Accipiter badius": ("शिकरा", "Shikra"),
    "Neophron percnopterus": ("सफेद गिद्ध", "Safed giddh"),
    "Pandion haliaetus": ("मछरंग", "Machhrang"),
    "Falco tinnunculus": ("खेरमुतिया", "Khermutiya"),
    "Spilornis cheela": ("डोगरा चील", "Dogra cheel"),
    "Ardeola grayii": ("अंधा बगुला", "Andha bagula"),
    "Bubulcus ibis": ("गाय बगुला", "Gai bagula"),
    "Egretta garzetta": ("छोटा बगुला / किलचिया", "Chhota bagula"),
    "Ardea alba": ("बड़ा बगुला", "Bada bagula"),
    "Ardea intermedia": ("पतोखा बगुला", "Patokha bagula"),
    "Ardea cinerea": ("अंजन / नारी", "Anjan"),
    "Ardea purpurea": ("लाल अंजन / नारी", "Lal anjan"),
    "Nycticorax nycticorax": ("वाक", "Waak"),
    "Vanellus indicus": ("टिटहरी", "Titahri"),
    "Vanellus malabaricus": ("पीली टिटहरी / ज़र्दी", "Peeli titahri"),
    "Halcyon smyrnensis": ("किलकिला / कौड़िल्ला", "Kilkila"),
    "Alcedo atthis": ("छोटा किलकिला", "Chhota kilkila"),
    "Ceryle rudis": ("कौड़िल्ला", "Kaudilla"),
    "Centropus sinensis": ("महोख / भारद्वाज", "Mahokh"),
    "Eudynamys scolopaceus": ("कोयल", "Koyal"),
    "Clamator jacobinus": ("चातक / पपीहा", "Chatak"),
    "Hierococcyx varius": ("पपीहा", "Papiha"),
    "Pavo cristatus": ("मोर", "Mor"),
    "Grus antigone": ("सारस", "Saras"),
    "Antigone antigone": ("सारस", "Saras"),
    "Grus grus": ("कुरजां / कुलंग", "Kurjan"),
    "Grus virgo": ("कुरजां / करकरा", "Karkara"),
    "Cinnyris asiaticus": ("शकरखोरा", "Shakarkhora"),
    "Copsychus saularis": ("दहियर / दैयाल", "Dahiyar"),
    "Copsychus fulicatus": ("कलचुरी", "Kalchuri"),
    "Saxicoloides fulicatus": ("कलचुरी", "Kalchuri"),
    "Copsychus malabaricus": ("शामा", "Shama"),
    "Prinia socialis": ("फुटकी", "Phutki"),
    "Prinia inornata": ("फुटकी", "Phutki"),
    "Orthotomus sutorius": ("दर्जिन", "Darzin"),
    "Dendrocitta vagabunda": ("महालत / टका चोर", "Mahalat"),
    "Motacilla alba": ("धोबिन / खंजन", "Dhobin / Khanjan"),
    "Motacilla maderaspatensis": ("ममोला / बड़ी धोबिन", "Mamola"),
    "Motacilla flava": ("पीली खंजन", "Peeli khanjan"),
    "Phoenicurus ochruros": ("थिरथिरा", "Thirthira"),
    "Saxicola caprata": ("काला पिद्दा", "Kala pidda"),
    "Saxicola maurus": ("खरपिद्दा", "Kharpidda"),
    "Luscinia svecica": ("हुसैनी पिद्दा / नीलकंठी", "Husaini pidda"),
    "Upupa epops": ("हुदहुद", "Hudhud"),
    "Coracias benghalensis": ("नीलकंठ", "Neelkanth"),
    "Ocyceros birostris": ("धनेश / चलोत्रा", "Dhanesh"),
    "Microcarbo niger": ("पनकौआ", "Pankauwa"),
    "Phalacrocorax carbo": ("बड़ा पनकौआ", "Bada pankauwa"),
    "Anhinga melanogaster": ("बनवा / सर्पग्रीव", "Banwa"),
    "Anastomus oscitans": ("घोंघिल", "Ghonghil"),
    "Mycteria leucocephala": ("जांघिल", "Janghil"),
    "Ciconia episcopus": ("लगलग", "Laglag"),
    "Ephippiorhynchus asiaticus": ("लोहारजंग", "Loharjang"),
    "Threskiornis melanocephalus": ("मुंडा / सफेद बाज़ा", "Munda"),
    "Pseudibis papillosa": ("काला बाज़ा / करांकुल", "Kala baza"),
    "Plegadis falcinellus": ("काला बुज्जा", "Kala bujja"),
    "Platalea leucorodia": ("चमचा / चम्मच बाज़ा", "Chamcha"),
    "Euodice malabarica": ("सफेद गले वाली मुनिया", "Munia"),
    "Lonchura punctulata": ("तिलिया मुनिया", "Tiliya munia"),
    "Lonchura malacca": ("तिरंगी मुनिया", "Tirangi munia"),
    "Amandava amandava": ("लाल मुनिया", "Lal munia"),
    "Ploceus philippinus": ("बया", "Baya"),
    "Amaurornis phoenicurus": ("जल मुर्गी / दावक", "Jal murgi"),
    "Gallinula chloropus": ("जल मुर्गी", "Jal murgi"),
    "Fulica atra": ("टिकरी / आरी", "Tikri"),
    "Tachybaptus ruficollis": ("पनडुब्बी / डुबडुबी", "Pandubbi"),
    "Himantopus himantopus": ("गजपाँव", "Gajpaon"),
    "Metopidius indicus": ("जल पीपी", "Jal peepi"),
    "Hydrophasianus chirurgus": ("जल पीपी / पिहो", "Piho"),
    "Burhinus indicus": ("करवानक", "Karwanak"),
    "Gallinago gallinago": ("चाहा", "Chaha"),
    "Tringa nebularia": ("टिमटिमा", "Timtima"),
    "Calidris pugnax": ("गेहवाला", "Gehwala"),
    "Charadrius dubius": ("जिर्री / छोटा मेरवा", "Jirri"),
    "Sterna aurantia": ("कुररी", "Kurri"),
    "Rynchops albicollis": ("पंचीरा", "Panchira"),
    "Anas acuta": ("सींखपर", "Seenkhpar"),
    "Anas crecca": ("छोटी मुरगाबी / केरा", "Kera"),
    "Mareca strepera": ("मिला / बेख़ुर", "Mila"),
    "Mareca penelope": ("पियासन", "Piyasan"),
    "Spatula querquedula": ("चैता", "Chaita"),
    "Dendrocygna javanica": ("सीलही / सिल्ली", "Silli"),
    "Anas poecilorhyncha": ("गुगरल", "Gugral"),
    "Sarkidiornis melanotos": ("नकटा", "Nakta"),
    "Anser indicus": ("राजहंस / सवन", "Rajhans"),
    "Anser anser": ("कलहंस", "Kalhans"),
    "Tadorna ferruginea": ("सुर्खाब / चकवा-चकवी", "Surkhab / Chakwa"),
    "Nettapus coromandelianus": ("गिर्री", "Girri"),
    "Aythya ferina": ("बुड़ार", "Budar"),
    "Netta rufina": ("लाल सिर", "Lal sir"),
    "Aythya nyroca": ("कर्चिया", "Karchiya"),
    "Aythya fuligula": ("दुबारू", "Dubaru"),
    "Francolinus pondicerianus": ("तीतर", "Teetar"),
    "Ortygornis pondicerianus": ("तीतर", "Teetar"),
    "Francolinus francolinus": ("काला तीतर", "Kala teetar"),
    "Coturnix coturnix": ("बटेर", "Bater"),
    "Pterocles exustus": ("भटतीतर", "Bhat-teetar"),
    "Athene brama": ("खूसट", "Khoosat"),
    "Tyto alba": ("उल्लू", "Ullu"),
    "Bubo bengalensis": ("घुग्घू", "Ghugghu"),
    "Ketupa zeylonensis": ("अमराई का घुग्घू", "Amrai ka ghugghu"),
    "Caprimulgus asiaticus": ("छपका", "Chhapka"),
    "Pitta brachyura": ("नौरंग", "Naurang"),
    "Merops orientalis": ("पतरिंगा", "Patringa"),
    "Psilopogon haemacephalus": ("ठठेरा / छोटा बसंता", "Thathera"),
    "Psilopogon zeylanicus": ("बड़ा बसंता", "Bada basanta"),
    "Dinopium benghalense": ("सुनहरा कठफोड़वा", "Kathphodwa"),
    "Lanius schach": ("लटोरा", "Latora"),
    "Lanius vittatus": ("छोटा लटोरा", "Chhota latora"),
    "Oriolus kundoo": ("पीलक", "Peelak"),
    "Hirundo smithii": ("अबाबील", "Ababeel"),
    "Hirundo rustica": ("अबाबील", "Ababeel"),
    "Cecropis daurica": ("मसजिद अबाबील", "Masjid ababeel"),
    "Apus affinis": ("बतासी", "Batasi"),
    "Eremopterix griseus": ("दियोरा", "Diyora"),
    "Galerida cristata": ("चंडूल", "Chandool"),
    "Alauda gulgula": ("भरत", "Bharat"),
    "Anthus rufulus": ("रुगेल", "Rugel"),
    "Gymnoris xanthocollis": ("जंगली गौरैया / रजा", "Jangli gauraiya"),
    "Zosterops palpebrosus": ("बबूना", "Babuna"),
    "Chrysomma sinense": ("गुलाब चश्म", "Gulab chashm"),
    "Terpsiphone paradisi": ("दूधराज / सुल्ताना बुलबुल", "Doodhraj"),
    "Carpodacus erythrinus": ("तूती", "Tooti"),
    "Emberiza bruniceps": ("गंदम", "Gandam"),
    "Emberiza melanocephala": ("गंदम", "Gandam"),
    "Emberiza lathami": ("पत्थर चिड़िया", "Patthar chidiya"),
    "Pernis ptilorhynchus": ("मधुया / शहद बाज़", "Madhuya"),
    "Falco peregrinus": ("शाहीन", "Shaheen"),
    "Oenanthe fusca": ("शमा", "Shama"),
}

_data: dict = {}
try:
    with open(DATA, encoding="utf-8") as fh:
        _data = json.load(fh)
except Exception:  # noqa: BLE001
    _data = {}


def hindi(scientific: str) -> Tuple[Optional[str], Optional[str], str]:
    """→ (devanagari, roman, source). source ∈ {"wikidata", "hi.wikipedia", "curated", "none"}."""
    if scientific in CURATED:
        dev, roman = CURATED[scientific]
        return dev, roman, "curated"
    row = _data.get(scientific)
    if row and row.get("hi"):
        return row["hi"], row.get("roman"), row.get("source", "wikidata")
    return None, None, "none"


def label(scientific: str, english: str) -> str:
    """'धोबिन (Dhobin) · White Wagtail' or 'White Wagtail (Hindi naam pakka nahi)'."""
    dev, roman, src = hindi(scientific)
    if dev:
        return f"{dev} ({roman}) · {english}" if roman else f"{dev} · {english}"
    return f"{english} (Hindi naam pakka nahi)"
