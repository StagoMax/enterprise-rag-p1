from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import Browser, Page, sync_playwright


def assert_no_horizontal_overflow(page: Page) -> None:
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    if overflow > 1:
        raise AssertionError(f"horizontal overflow: {overflow}px")


def verify_desktop(browser: Browser, base_url: str, output: Path) -> dict[str, object]:
    context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page = context.new_page()
    console_errors: list[str] = []

    def record_console_error(message) -> None:
        if message.type == "error":
            console_errors.append(message.text)

    page.on("console", record_console_error)
    page.goto(base_url, wait_until="networkidle")
    page.locator("#service-label").wait_for(state="visible")
    assert page.locator("#document-count").inner_text() == "200"
    assert_no_horizontal_overflow(page)

    sample = page.locator("#sample-row button").first
    sample.wait_for(state="visible")
    sample.click()
    page.locator("#submit-query").click()
    page.locator("#query-result").wait_for(state="visible", timeout=30_000)
    route = page.locator("#route-badge").inner_text()
    citations = page.locator("#citation-list li").count()
    if citations < 1:
        raise AssertionError("query result has no citation row")
    page.screenshot(path=output / "workbench-query-desktop.png", full_page=True)

    page.locator("#role-select").select_option("security_auditor")
    page.get_by_role("button", name="基线评测").click()
    page.locator(".metric-item").first.wait_for(state="visible")
    metric_count = page.locator(".metric-item").count()
    if metric_count != 6:
        raise AssertionError(f"expected 6 metrics, got {metric_count}")
    assert_no_horizontal_overflow(page)
    page.screenshot(path=output / "workbench-evaluation-desktop.png", full_page=True)
    context.close()
    return {
        "route": route,
        "citations": citations,
        "metrics": metric_count,
        "console_errors": console_errors,
    }


def verify_mobile(browser: Browser, base_url: str, output: Path) -> dict[str, object]:
    context = browser.new_context(viewport={"width": 375, "height": 812}, device_scale_factor=1)
    page = context.new_page()
    page.goto(base_url, wait_until="networkidle")
    page.locator("#service-label").wait_for(state="attached")
    assert_no_horizontal_overflow(page)
    nav_buttons = page.locator(".nav-button").count()
    if nav_buttons != 4:
        raise AssertionError(f"expected 4 mobile navigation buttons, got {nav_buttons}")
    page.screenshot(path=output / "workbench-mobile.png", full_page=True)
    context.close()
    return {"nav_buttons": nav_buttons, "horizontal_overflow": 0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--chrome",
        type=Path,
        default=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.chrome)
        try:
            result = {
                "desktop": verify_desktop(browser, args.url, args.output),
                "mobile": verify_mobile(browser, args.url, args.output),
            }
        finally:
            browser.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
