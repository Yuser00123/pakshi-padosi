"""Phone-sized screenshots of a running Pakshi Padosi for the README / write-up.

    pip install playwright && python -m playwright install chromium
    python scripts/take_screenshots.py https://pakshi-padosi.onrender.com docs/screenshots

Gradio keeps an SSE connection open, so never wait for "networkidle" — wait for selectors instead.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7860"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)


def shot(page, name: str, full: bool = False):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=full)
    print("saved", path)


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 412, "height": 915}, device_scale_factor=2, is_mobile=True, has_touch=True,
                              locale="en-IN", timezone_id="Asia/Kolkata")
    page = ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_selector("text=Card banao", timeout=60_000)
    time.sleep(1.5)
    shot(page, "1-home")

    page.locator("button", has_text="Card banao").click()
    # wait until the card has its last line (all birds done) — up to 3 minutes when Gemma writes live
    page.wait_for_selector("text=aankhein upar", timeout=180_000)  # the card's last line
    deadline = time.time() + 180
    while time.time() < deadline and page.locator("text=pakshi likh chuka").count() > 0:  # still filling in
        time.sleep(2)
    time.sleep(1)
    shot(page, "2-card", full=True)

    page.get_by_role("tab", name=lambda n: "Bahar" in n).click() if False else page.locator("button[role=tab]", has_text="Bahar").click()
    time.sleep(1.5)
    shot(page, "3-bahar", full=True)

    page.locator("button[role=tab]", has_text="Diary").click()
    time.sleep(1.5)
    shot(page, "4-diary", full=True)
    browser.close()
