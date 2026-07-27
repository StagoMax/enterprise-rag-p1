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
    assert page.locator("#document-count").inner_text() == "1000"
    assert int(page.locator("#relation-count").inner_text()) > 0
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
    graph_paths = page.locator("#graph-path-list li").count()
    if graph_paths < 1:
        raise AssertionError("P2 sample query has no graph path")
    page.screenshot(path=output / "workbench-query-desktop.png", full_page=True)

    with page.expect_response(
        lambda response: response.url.endswith("/dev/token")
        and response.request.method == "POST"
    ) as token_response:
        page.locator("#role-select").select_option("security_auditor")
    if not token_response.value.ok:
        raise AssertionError("security auditor token refresh failed")
    with page.expect_response(
        lambda response: response.url.endswith("/v1/graph")
    ) as graph_response:
        page.get_by_role("button", name="图索引").click()
    if not graph_response.value.ok:
        raise AssertionError("graph summary request failed")
    page.locator("#graph-summary").wait_for(state="visible")
    page.wait_for_function("document.querySelector('#graph-relations').textContent !== '-'")
    graph_relations = int(page.locator("#graph-relations").inner_text())
    if graph_relations < 1:
        raise AssertionError("graph view reports no relations")
    page.screenshot(path=output / "workbench-graph-desktop.png", full_page=True)

    page.get_by_role("button", name="基线评测").click()
    page.locator(".metric-item").first.wait_for(state="visible")
    metric_count = page.locator(".metric-item").count()
    if metric_count != 15:
        raise AssertionError(f"expected 15 P2 metrics, got {metric_count}")
    summary_count = page.locator(".run-summary > div").count()
    if summary_count != 4:
        raise AssertionError(f"expected 4 run-summary cells, got {summary_count}")
    # Every gated proportion carries a Wilson interval; the ungated ones carry a
    # "参考指标" note instead, so each card must have exactly one footnote.
    interval_count = page.locator(".metric-item small").count()
    if interval_count != metric_count:
        raise AssertionError(
            f"expected a footnote on each of {metric_count} metrics, got {interval_count}"
        )
    assert_no_horizontal_overflow(page)
    page.screenshot(path=output / "workbench-evaluation-desktop.png", full_page=True)
    context.close()
    return {
        "route": route,
        "citations": citations,
        "graph_paths": graph_paths,
        "graph_relations": graph_relations,
        "metrics": metric_count,
        "metric_footnotes": interval_count,
        "run_summary_cells": summary_count,
        "console_errors": console_errors,
    }


def verify_mobile(browser: Browser, base_url: str, output: Path) -> dict[str, object]:
    context = browser.new_context(viewport={"width": 375, "height": 812}, device_scale_factor=1)
    page = context.new_page()
    page.goto(base_url, wait_until="networkidle")
    page.locator("#service-label").wait_for(state="attached")
    assert_no_horizontal_overflow(page)
    nav_buttons = page.locator(".nav-button").count()
    if nav_buttons != 5:
        raise AssertionError(f"expected 5 mobile navigation buttons, got {nav_buttons}")
    page.screenshot(path=output / "workbench-mobile.png", full_page=True)

    # The evaluation view carries the widest grids, so it is the one that would
    # overflow first on a narrow viewport. It needs the auditor role to load.
    with page.expect_response(
        lambda response: response.url.endswith("/dev/token")
        and response.request.method == "POST"
    ) as token_response:
        page.locator("#role-select").select_option("security_auditor")
    if not token_response.value.ok:
        raise AssertionError("security auditor token refresh failed on mobile")
    page.get_by_role("button", name="基线评测").click()
    page.locator(".metric-item").first.wait_for(state="visible")
    assert_no_horizontal_overflow(page)
    page.screenshot(path=output / "workbench-evaluation-mobile.png", full_page=True)
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
