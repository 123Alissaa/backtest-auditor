"""Open the public demo in a real browser so Streamlit Community Cloud doesn't put it to sleep.

Run by .github/workflows/keep-awake.yml every few hours until judging ends. Makes no paid
calls: it only loads the landing page (saved audits). Clicks "wake up" if the app is asleep.

    python -m scripts.keep_awake            # needs: pip install playwright && playwright install chromium
"""
import os
import sys
from datetime import date

from playwright.sync_api import sync_playwright

URL = "https://backtest-auditor.streamlit.app/"
STOP_AFTER = date(2026, 12, 16)  # judging ends Dec 15


def main() -> int:
    if date.today() > STOP_AFTER:
        print("Judging is over; nothing to do.")
        return 0
    with sync_playwright() as p:
        channel = os.getenv("KEEP_AWAKE_CHANNEL")  # e.g. "chrome" to use an installed browser locally
        browser = p.chromium.launch(channel=channel) if channel else p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(URL, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(8_000)
        wake = page.get_by_role("button", name="Yes, get this app back up!")
        if wake.count():
            print("App was asleep: waking it up.")
            wake.click()
            page.wait_for_timeout(90_000)
        app = next((f for f in page.frames if "/~/+/" in f.url), page.main_frame)
        try:
            app.wait_for_selector("text=Is your backtest lying?", timeout=180_000)
        except Exception:
            print("Landing page did not render in time.")
            return 1
        print("Landing page is up.")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
