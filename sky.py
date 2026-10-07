"""When should you go? Sunrise/sunset, rain and air quality from Open-Meteo (open data, no key).

Birds are busiest in the first 90 minutes after sunrise and the last hour before sunset; we pick the
best window inside those that is dry and not too hot, and we are honest about smog (Oct–Jan in the plains).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

import requests

FORECAST = "https://api.open-meteo.com/v1/forecast"
AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"
UA = {"User-Agent": "PakshiPadosi/0.1 (+https://github.com/Yuser00123/pakshi-padosi)"}
TZ = "Asia/Kolkata"


@dataclass
class Window:
    start: datetime
    end: datetime
    label: str          # "subah" | "shaam"
    rain_pct: int       # max precipitation probability inside the window
    temp_c: float       # temperature at the start
    aqi: Optional[int]  # US AQI at the start, if known
    note: str           # one Hinglish line of reasoning

    @property
    def text(self) -> str:
        return f"{self.start:%a %d %b}, {self.start:%-I:%M %p}–{self.end:%-I:%M %p}"


@dataclass
class Sky:
    sunrise: datetime
    sunset: datetime
    day_label: str
    rain_day_pct: int
    tmax: float
    tmin: float
    aqi_now: Optional[int]
    windows: List[Window]

    @property
    def best(self) -> Window:
        return self.windows[0]


def _aqi_word(aqi: Optional[int]) -> str:
    if aqi is None:
        return "AQI pata nahi"
    if aqi <= 50:
        return f"hawa saaf (AQI {aqi})"
    if aqi <= 100:
        return f"hawa theek (AQI {aqi})"
    if aqi <= 150:
        return f"hawa thodi bhaari (AQI {aqi}) — mask rakh lo agar asthma hai"
    if aqi <= 200:
        return f"smog (AQI {aqi}) — chhoti sair, bhaari exercise nahi"
    return f"bahut smog (AQI {aqi}) — aaj khidki se hi dekho"


def forecast(lat: float, lon: float, when: str = "abhi", minutes: int = 40) -> Sky:
    """`when` = "abhi" (next good window from now) or "kal" (tomorrow morning)."""
    now = datetime.now()  # the server runs in UTC on Render; we only compare against local forecast times below
    try:
        import zoneinfo

        now = datetime.now(zoneinfo.ZoneInfo(TZ)).replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        pass

    fc = requests.get(FORECAST, headers=UA, timeout=20, params=dict(
        latitude=lat, longitude=lon, timezone=TZ, forecast_days=3,
        daily="sunrise,sunset,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        hourly="temperature_2m,precipitation_probability")).json()
    aqi_hourly: dict = {}
    aqi_now = None
    try:
        aq = requests.get(AIR, headers=UA, timeout=20, params=dict(
            latitude=lat, longitude=lon, timezone=TZ, forecast_days=3, hourly="us_aqi")).json()
        aqi_hourly = dict(zip(aq["hourly"]["time"], aq["hourly"]["us_aqi"]))
        aqi_now = next((v for t, v in aqi_hourly.items() if datetime.fromisoformat(t) >= now.replace(minute=0)), None)
    except Exception:  # noqa: BLE001
        pass

    hourly_t = dict(zip(fc["hourly"]["time"], fc["hourly"]["temperature_2m"]))
    hourly_p = dict(zip(fc["hourly"]["time"], fc["hourly"]["precipitation_probability"]))

    def at(d: dict, t: datetime, default=None):
        return d.get(t.replace(minute=0, second=0, microsecond=0).isoformat(timespec="minutes"), default)

    windows: List[Window] = []
    for i, day in enumerate(fc["daily"]["time"]):
        sunrise = datetime.fromisoformat(fc["daily"]["sunrise"][i])
        sunset = datetime.fromisoformat(fc["daily"]["sunset"][i])
        for label, start in (("subah", sunrise + timedelta(minutes=10)), ("shaam", sunset - timedelta(minutes=minutes + 15))):
            end = start + timedelta(minutes=minutes)
            if end <= now + timedelta(minutes=20):
                continue  # already gone
            if when == "kal" and start.date() <= now.date():
                continue
            rain = max(int(at(hourly_p, start, 0) or 0), int(at(hourly_p, end, 0) or 0))
            temp = float(at(hourly_t, start, fc["daily"]["temperature_2m_min"][i]) or 0)
            aqi = at(aqi_hourly, start)
            score = (label == "shaam") * 1 + (rain >= 50) * 3 + (temp >= 33) * 2 + ((aqi or 0) >= 200) * 2 + i * 0.75
            why = []
            why.append("sunrise ke baad pehla ghanta — chidiyan sabse active" if label == "subah" else "sunset se pehle — paani par bheed lagti hai")
            if rain >= 50:
                why.append(f"baarish ka chance {rain}% — chhata/plan B")
            elif rain >= 25:
                why.append(f"halki baarish ho sakti hai ({rain}%)")
            why.append(_aqi_word(aqi))
            windows.append((score, Window(start, end, label, rain, temp, aqi, "; ".join(why))))
    windows.sort(key=lambda w: w[0])
    today = 0 if windows and windows[0][1].start.date() == now.date() else 1
    sky = Sky(
        sunrise=datetime.fromisoformat(fc["daily"]["sunrise"][today]),
        sunset=datetime.fromisoformat(fc["daily"]["sunset"][today]),
        day_label=datetime.fromisoformat(fc["daily"]["time"][today]).strftime("%a %d %b"),
        rain_day_pct=int(fc["daily"]["precipitation_probability_max"][today] or 0),
        tmax=fc["daily"]["temperature_2m_max"][today], tmin=fc["daily"]["temperature_2m_min"][today],
        aqi_now=aqi_now, windows=[w for _, w in windows[:4]],
    )
    return sky


if __name__ == "__main__":
    s = forecast(26.2087, 81.2186)
    print(s.day_label, "sunrise", s.sunrise.time(), "sunset", s.sunset.time(), "rain", s.rain_day_pct, "% AQI", s.aqi_now)
    for w in s.windows:
        print(" ", w.text, "|", w.label, "| rain", w.rain_pct, "% |", w.temp_c, "°C |", w.note)
