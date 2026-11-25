"""NFR 8 cross-browser test and NFR 2 3G timing, with Playwright.

Runs the main flows in Chromium (Chrome, Edge), Firefox and WebKit (Safari), on desktop
and on an emulated Android phone and iPhone. Requests to other sites (map library and
tiles) are blocked, so the list-only map fallback (SRS 3.4) is tested too.
Needs a running server with the demo data (seed, seed_questions).
"""
import argparse
import time

from playwright.sync_api import expect, sync_playwright

TEACHER = ("teacher01@demo.autismcare.test", "DemoTherapist2026!")
NAIROBI = {"latitude": -1.2864, "longitude": 36.8172}

# name, engine, Playwright device (None = desktop)
TARGETS = [
    ("Chrome / Edge (desktop)", "chromium", None),
    ("Firefox (desktop)", "firefox", None),
    ("Safari (desktop)", "webkit", None),
    ("Chrome on Android", "chromium", "Pixel 7"),
    ("Safari on iPhone", "webkit", "iPhone 13"),
]

# Chrome DevTools network presets
NETWORKS = {
    "Fast 3G": {"latency": 150 * 3.75, "download": 1.6e6 * 0.9 / 8, "upload": 750e3 * 0.9 / 8},
    "Slow 3G": {"latency": 400 * 5, "download": 500e3 * 0.8 / 8, "upload": 500e3 * 0.8 / 8},
}


def home(page, base):
    page.goto(base + "/")
    expect(page.get_by_role("heading", level=1)).to_be_visible()
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()


def screening(page, base):
    page.goto(base + "/screening/questions/")
    page.fill("#age", "20")
    page.get_by_role("button", name="Continue").click()
    for _ in range(20):
        page.locator(".step:not([hidden]) .answer", has_text="No").click()
    page.get_by_role("button", name="See my result").click()
    expect(page.get_by_text("Score 0 of 20")).to_be_visible()


def screening_keyboard(page, base):
    """Arrow keys choose an answer without moving on; Enter moves on (NFR 5)."""
    page.goto(base + "/screening/questions/")
    page.fill("#age", "20")
    page.keyboard.press("Enter")
    first = page.locator(".step:not([hidden])")
    expect(first).to_contain_text("Question 1 of 20")
    page.keyboard.press("Tab")
    page.keyboard.press("ArrowRight")
    expect(page.locator(".step:not([hidden])")).to_contain_text("Question 1 of 20")
    page.keyboard.press("Enter")
    expect(page.locator(".step:not([hidden])")).to_contain_text("Question 2 of 20")


def search(page, base):
    page.goto(base + "/find/")
    page.get_by_role("button", name="Use my location").click()
    expect(page.locator("#location-status")).to_have_text("Using your current location.")
    page.fill("#radius", "50")
    page.get_by_role("button", name="Search").click()
    expect(page.locator("#result-summary")).to_contain_text("verified therapist")
    assert page.locator("#results li").count() > 0
    expect(page.locator("#map-notice")).to_be_visible(timeout=12_000)   # map blocked: list-only fallback


def teaching(page, base):
    page.goto(base + "/login/")
    page.fill("input[name=email]", TEACHER[0])
    page.fill("input[name=password]", TEACHER[1])
    page.get_by_role("button", name="Log in").click()
    page.wait_for_load_state()
    page.goto(base + "/teach/")
    page.get_by_role("link", name="Start session").first.click()
    page.select_option("select[name=planned_cards]", "6")
    page.get_by_role("button", name="Start session").click()
    page.get_by_role("button", name="Start").click()
    for _ in range(6):
        page.locator(".choice").first.click()
        nxt = page.locator("#next")
        expect(nxt).to_be_visible()
        nxt.click()
    expect(page.get_by_role("heading", name="Session summary", exact=False)).to_be_visible()
    page.get_by_role("button", name="Log out").click()


FLOWS = [("Home", home), ("Screening", screening), ("Screening by keyboard", screening_keyboard),
         ("Therapist search", search), ("Teaching session", teaching)]


def run_target(p, base, name, engine, device):
    browser = getattr(p, engine).launch()
    opts = dict(p.devices[device]) if device else {"viewport": {"width": 1280, "height": 800}}
    if engine == "firefox":
        opts.pop("is_mobile", None)
    context = browser.new_context(**opts, geolocation=NAIROBI, permissions=["geolocation"])
    context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base)
                  else route.abort())
    rows = []
    for flow, fn in FLOWS:
        if flow == "Screening by keyboard" and device:
            continue  # phones have no keyboard
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        start = time.perf_counter()
        try:
            fn(page, base)
            result = "pass" if not errors else f"JS error: {errors[0]}"
        except Exception as e:  # report and carry on with the next flow
            result = f"FAIL: {str(e).splitlines()[0][:150]}"
        rows.append((name, flow, result, time.perf_counter() - start))
        page.close()
    browser.close()
    return rows


def network_timings(p, base):
    """Load time of each page on throttled 3G (Chromium only: it uses Chrome DevTools)."""
    browser = p.chromium.launch()
    rows = []
    for net, cond in NETWORKS.items():
        for path in ("/", "/screening/questions/", "/find/"):
            context = browser.new_context()   # empty cache: a first visit
            page = context.new_page()
            cdp = context.new_cdp_session(page)
            cdp.send("Network.enable")
            cdp.send("Network.emulateNetworkConditions", {
                "offline": False, "latency": cond["latency"],
                "downloadThroughput": cond["download"], "uploadThroughput": cond["upload"]})
            start = time.perf_counter()
            page.goto(base + path, wait_until="load")
            rows.append((net, path, time.perf_counter() - start))
            context.close()
    browser.close()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    with sync_playwright() as p:
        rows = []
        for name, engine, device in TARGETS:
            rows += run_target(p, args.base, name, engine, device)
        print("\nBrowser | Flow | Result | Seconds")
        for r in rows:
            print(f"{r[0]} | {r[1]} | {r[2]} | {r[3]:.1f}")
        print("\nNetwork | Page | Load time (s)")
        for net, path, secs in network_timings(p, args.base):
            print(f"{net} | {path} | {secs:.1f}")
        failed = [r for r in rows if r[2] != "pass"]
        print(f"\n{len(rows) - len(failed)} of {len(rows)} passed")
        raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
