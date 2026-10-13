"""Research review regressions in an isolated browser, without a native window."""

import os
import re
from pathlib import Path

import pytest


@pytest.fixture
def research_page():
    playwright_api = pytest.importorskip("playwright.sync_api")
    web = Path(__file__).parents[3] / "src/tcad_agent/web"
    with playwright_api.sync_playwright() as playwright:
        executable = os.getenv("KRONIG_TEST_BROWSER") or playwright.chromium.executable_path
        if not Path(executable).is_file():
            pytest.skip("requires installed Chromium or KRONIG_TEST_BROWSER")
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 500})
        html = (web / "templates/ide.html").read_text()
        scripts = re.findall(r'<script src="/static/([^?]+)[^"]*" defer></script>', html)
        page.set_content(re.sub(r"<script.*?</script>|<link[^>]+>", "", html))
        for name in ("theme.css", "ide.css"):
            page.add_style_tag(content=(web / "static" / name).read_text())
        for name in scripts:
            page.add_script_tag(content=(web / "static" / name).read_text())
        yield page
        browser.close()


def test_plan_revision_submit_remains_reachable_in_short_pane(research_page):
    page = research_page
    page.evaluate("""() => renderPlan({status:'pending',
      plan_path:'/experiments/research/PLAN.md',prepared:{backend:'devsim',
      spec:{name:'Forward and reverse bias research with complete scientific outputs'}}})""")
    page.locator("#revise-plan").click()
    bounds = page.evaluate("""() => {
      const card=document.querySelector('#plan-review-card').getBoundingClientRect();
      const submit=document.querySelector('#plan-revision-form button[type=submit]')
        .getBoundingClientRect();
      return {bottom:submit.bottom,cardBottom:card.bottom};
    }""")
    assert bounds["bottom"] <= bounds["cardBottom"]
    page.set_viewport_size({"width": 1200, "height": 420})
    page.locator("#plan-revision-instruction").fill("Use the requested operating points.")
    # Scrolling the actual form must bring its actions inside the clipping card.
    page.locator("#plan-revision-form").evaluate("form => {form.scrollTop=form.scrollHeight}")
    page.locator("#cancel-plan-revision").click(timeout=2000)
    assert page.locator("#plan-revision-form").is_hidden()
    assert page.locator("#approve-plan").is_visible()


def test_clarification_polling_keeps_answer_focus_and_selection(research_page):
    page = research_page
    preparation = {"revision": 1, "decision": {"status": "clarification",
        "summary": "Confirm dimensions and contact boundaries before execution.",
        "questions": [
            {"id": "dimensions", "prompt": "What are the region dimensions?",
             "reason": "Dimensions define the domain.", "required": True},
            {"id": "contacts", "prompt": "What contact boundaries should be used?",
             "reason": "Contacts define the applied bias.", "required": True},
        ]}}
    page.evaluate("preparation => renderClarification(preparation)", preparation)
    answer = page.locator('#clarification-questions textarea[data-question-id="dimensions"]')
    answer.fill("Use one micrometre per semiconductor region.")
    answer.evaluate("input => {input.focus(); input.setSelectionRange(4, 18);}")
    page.evaluate("preparation => renderClarification(preparation)", preparation)
    assert answer.evaluate("input => input === document.activeElement")
    assert answer.evaluate("input => [input.selectionStart,input.selectionEnd]") == [4, 18]
    # A changed server revision rebuilds the questions; the draft and caret survive.
    preparation["revision"] = 2
    preparation["decision"]["summary"] += " The plan will record these answers."
    page.evaluate("preparation => renderClarification(preparation)", preparation)
    page.wait_for_function("document.activeElement?.dataset.questionId === 'dimensions'")
    assert answer.input_value() == "Use one micrometre per semiconductor region."
    assert answer.evaluate("input => [input.selectionStart,input.selectionEnd]") == [4, 18]
    page.locator("#clarification-next").click()
    page.locator('#clarification-questions textarea[data-question-id="contacts"]').fill(
        "Ohmic contacts; right contact held at zero volts."
    )
    assert page.locator("#submit-clarification").is_visible()


def test_scientific_selectors_change_slice_and_zoom_in_narrow_result(research_page):
    page = research_page
    page.evaluate("""() => {
      const root=document.createElement('div');root.id='headless-result';
      root.style.width='560px';document.querySelector('#workspace-welcome').replaceWith(root);
      AgentKronigResults.render(root,{execution_state:'completed',experiment:{regions:[]},
        result:{metadata:{profile_bias_values_v:[-2,2]},operating_points:[],
          axes:{bias:{id:'bias',kind:'bias',label:'Bias',unit:'V',values:[-2,0,2]},
            position:{id:'position',kind:'position',label:'Position',unit:'m',values:[0,1e-6,2e-6]},
            frequency:{id:'frequency',kind:'frequency',label:'Frequency',unit:'Hz',values:[1e6]}},
          datasets:{potential:{id:'potential',label:'Potential',unit:'V',
            axes:['bias','position'],shape:[3,3],values:[0,1,2,0,2,3,0,3,5]},
            capacitance:{id:'capacitance',label:'Capacitance',unit:'F/m^2',
              axes:['bias','frequency'],shape:[3,1],values:[1,3,5]}}},
        validation:{overall:'passed',checks:[]}});
    }""")
    root = page.locator("#headless-result")
    dataset = root.locator('[aria-label="Displayed result dataset"]')
    point = root.locator('[aria-label="Displayed operating point"]')
    assert "requested profile" in point.locator("option").first.inner_text()
    line = root.locator(".result-chart-line").first
    original_line = line.get_attribute("d")
    point.select_option("2")
    assert line.get_attribute("d") != original_line
    root.get_by_role("button", name="Zoom in", exact=True).click()
    assert root.locator(".result-chart-viewport").inner_text() == "Zoomed range"
    root.get_by_role("button", name="Reset view", exact=True).click()
    assert root.locator(".result-chart-viewport").inner_text() == "Full range"
    dataset.select_option(label="Capacitance · run 1")
    assert point.locator("option").count() == 1
    assert "Frequency" in point.locator("option").first.inner_text()
    point.select_option("0")
    assert "1.000e6 Hz" in point.get_attribute("title")
    assert root.evaluate("root => root.scrollWidth <= root.clientWidth")
