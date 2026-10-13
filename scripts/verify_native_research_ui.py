"""Optional development QA driver for the actual Electron webview, never production logic.

Requires playwright installed in the development environment and an Electron process
started with --remote-debugging-port=9225. This does not install a browser or expose
the application's private backend authentication token.
"""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation",
        choices=[
            "open",
            "prompt",
            "state",
            "answer",
            "plan",
            "run",
            "screenshot",
            "resize",
            "close",
        ],
    )
    parser.add_argument("value", nargs="?")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp("http://127.0.0.1:9225")
        context = browser.contexts[0]
        page = next(
            (
                candidate
                for candidate in context.pages
                if "saved_bundle_id=" not in candidate.url and "result_run_id=" not in candidate.url
            ),
            None,
        )
        if page is None:
            page = (
                context.pages[0] if context.pages else context.wait_for_event("page", timeout=60000)
            )
        page.wait_for_load_state("domcontentloaded")
        if args.operation == "open":
            page.locator("#workspace-path").fill(args.value or "/Users/satyagni/Documents/test")
            page.get_by_role("button", name="Open path", exact=True).click()
            page.wait_for_function("Boolean(activeSession)")
        elif args.operation == "prompt":
            page.locator("#message-input").fill(Path(args.value).read_text())
            page.locator("#send-message").click()
        elif args.operation == "answer":
            answers = json.loads(args.value)
            for index, answer in enumerate(answers):
                page.locator("#clarification-steps button").nth(index).click()
                page.locator(".clarification-question:not([hidden]) textarea").fill(answer)
            page.locator("#submit-clarification").click()
        elif args.operation == "run":
            page.locator("#approve-plan-unattended").click()
        elif args.operation == "plan":
            page.locator("#open-plan").click()
        elif args.operation == "screenshot":
            page.screenshot(path=args.value)
        elif args.operation == "resize":
            width, height = map(int, args.value.split("x"))
            # Exercise responsive renderer dimensions without moving the user's desktop.
            page.set_viewport_size({"width": width, "height": height})
        elif args.operation == "close":
            page.evaluate("window.close()")
        if args.operation not in {"close", "screenshot"}:
            state = page.evaluate("""() => ({
                url: location.href, run: typeof activeRun === 'undefined' ? null : activeRun,
                preparation: typeof activePreparation === 'undefined' ? null : activePreparation,
                plan: typeof activePlan === 'undefined' ? null : activePlan,
                error: document.querySelector('#session-error')?.textContent,
                trail: document.querySelector('#agent-research-trail')?.innerText,
                questions: Array.from(document.querySelectorAll('.clarification-question'))
                    .map(e=>e.innerText),
                results: document.querySelector('.results-workbench')?.innerText?.slice(0, 6000),
                messages: Array.from(document.querySelectorAll('.message-body'))
                    .slice(-2).map(e=>e.innerText),
                dimensions: {width: innerWidth, height: innerHeight},
            })""")
            print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
