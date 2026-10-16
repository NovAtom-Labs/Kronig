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
    preparation = {
        "revision": 1,
        "decision": {
            "status": "clarification",
            "summary": "Confirm dimensions and contact boundaries before execution.",
            "questions": [
                {
                    "id": "dimensions",
                    "prompt": "What are the region dimensions?",
                    "reason": "Dimensions define the domain.",
                    "required": True,
                },
                {
                    "id": "contacts",
                    "prompt": "What contact boundaries should be used?",
                    "reason": "Contacts define the applied bias.",
                    "required": True,
                },
            ],
        },
    }
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


def test_reused_question_id_never_carries_a_draft_into_a_different_field(research_page):
    page = research_page
    page.evaluate("""() => {
      activeRun={id:'run-a',state:'waiting_for_user'};
      renderClarification({revision:1,decision:{status:'clarification',questions:[
        {id:'setting',field_path:'physics.temperature',prompt:'Temperature?',reason:'Required'}]}});
    }""")
    answer = page.locator("#clarification-questions textarea")
    answer.fill("315 K")
    page.evaluate("""() => renderClarification({revision:2,decision:{
      status:'clarification',questions:[{id:'setting',field_path:'contacts.gate.work_function',
      prompt:'Work function?',reason:'Required'}]}})
    """)
    assert answer.input_value() == ""


def test_renamed_question_for_same_field_keeps_only_that_fields_draft(research_page):
    page = research_page
    page.evaluate("""() => {
      activeRun={id:'run-a',state:'waiting_for_user'};
      renderClarification({revision:1,decision:{status:'clarification',questions:[
        {id:'old',field_path:'physics.temperature',prompt:'Temperature?',reason:'Required'}]}});
    }""")
    page.locator("#clarification-questions textarea").fill("315 K")
    page.evaluate("""() => renderClarification({revision:2,decision:{
      status:'clarification',questions:[{id:'new',field_path:'physics.temperature',
      prompt:'Physical temperature?',reason:'Required'}]}})
    """)
    assert page.locator("#clarification-questions textarea").input_value() == "315 K"


def test_scientific_selectors_change_slice_and_zoom_in_narrow_result(research_page):
    page = research_page
    page.evaluate("""() => {
      const root=document.createElement('div');root.id='headless-result';
      root.style.width='560px';document.querySelector('#workspace-welcome').replaceWith(root);
      AgentKronigResults.render(root,{execution_state:'completed',experiment:{regions:[
        {id:'bulk',x0:{magnitude_si:0},x1:{magnitude_si:2e-6}}],contacts:[
        {id:'left_contact',location:'x_min'},
        {id:'right_reference_contact',location:'x_max'}]},
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
    assert root.locator(".result-metric-label").first.inner_text() == (
        "Potential span · all points"
    )
    dataset = root.locator('[aria-label="Displayed result dataset"]')
    point = root.locator('[aria-label="Displayed operating point"]')
    assert "requested profile" in point.locator("option").first.inner_text()
    line = root.locator(".result-chart-line").first
    right_label = root.locator('svg text').filter(has_text="right_reference_contact")
    assert right_label.evaluate("text => text.getBBox().x + text.getBBox().width <= 880")
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


def test_plot_png_export_retains_visible_curve_and_opaque_background(research_page):
    import base64

    page = research_page
    page.evaluate("""() => {
      const root=document.createElement('div');root.id='export-result';
      document.querySelector('#workspace-welcome').replaceWith(root);
      AgentKronigResults.render(root,{experiment:{regions:[]},result:{metadata:{},
        axes:{x:{id:'x',kind:'bias',label:'Bias',unit:'V',values:[-1,0,1]}},
        datasets:{response:{id:'response',label:'Response',unit:'F/m^2',
          axes:['x'],shape:[3],values:[0.003,0.0004,0.003]}},operating_points:[]},
        validation:{checks:[]}});
    }""")
    with page.expect_download() as exported:
        page.get_by_role("button", name="PNG", exact=True).click()
    encoded = base64.b64encode(Path(exported.value.path()).read_bytes()).decode()
    pixels = page.evaluate("""async encoded => {
      const image=new Image();image.src='data:image/png;base64,'+encoded;await image.decode();
      const canvas=document.createElement('canvas');
      canvas.width=image.width;canvas.height=image.height;
      const context=canvas.getContext('2d');context.drawImage(image,0,0);
      const p=context.getImageData(0,0,canvas.width,canvas.height).data;
      let blue=0;for(let i=0;i<p.length;i+=4)if(p[i+2]>p[i]+20&&p[i+2]>p[i+1]+5)blue++;
      return {backgroundAlpha:p[3],bluePixels:blue};
    }""", encoded)
    assert pixels["backgroundAlpha"] == 255
    assert pixels["bluePixels"] > 100


def _clarification_fixture():
    return {
        "run_id": "research-run",
        "revision": 1,
        "decision": {
            "status": "clarification",
            "summary": "Confirm the physical boundaries.",
            "questions": [
                {
                    "id": "boundary",
                    "prompt": "Which boundary is driven?",
                    "reason": "Defines the applied voltage.",
                    "required": True,
                }
            ],
        },
    }


def test_accepted_questions_do_not_reappear_from_queued_preparation(research_page):
    page = research_page
    page.evaluate(
        """preparation => {
      activeRun={id:'research-run',state:'queued'};
      renderClarification(preparation);
      api=async () => preparation;
    }""",
        _clarification_fixture(),
    )
    page.evaluate("async () => await loadPreparation(activeRun)")
    assert page.locator("#clarification-card").is_hidden()


def test_late_preparation_response_cannot_reopen_answered_questions(research_page):
    page = research_page
    page.evaluate(
        """preparation => {
      activeRun={id:'research-run',state:'waiting_for_user'};
      renderClarification(preparation);
      api=url => url.endsWith('/preparation')
        ? new Promise(resolve => {window.resolvePreparation=resolve})
        : Promise.resolve(null);
      window.preparationLoad=loadPreparation(activeRun);
      setRun({id:'research-run',state:'queued'});
      window.resolvePreparation(preparation);
    }""",
        _clarification_fixture(),
    )
    page.evaluate("async () => await window.preparationLoad")
    assert page.locator("#clarification-card").is_hidden()


def test_clarification_continue_cannot_submit_twice_while_request_pending(research_page):
    page = research_page
    page.evaluate(
        """preparation => {
      activeRun={id:'research-run',state:'waiting_for_user'};
      renderClarification(preparation);
      window.clarificationPosts=[];
      api=(url,options) => {
        if(url.endsWith('/clarifications')) {
          window.clarificationPosts.push(JSON.parse(options.body));
          return new Promise(resolve => {window.resolveSubmission=resolve});
        }
        return Promise.resolve(null);
      };
    }""",
        _clarification_fixture(),
    )
    page.locator("#clarification-questions textarea").fill("Drive the left boundary.")
    page.evaluate("""() => {
      const form=document.querySelector('#clarification-form');
      form.dispatchEvent(new Event('submit',{cancelable:true}));
      form.dispatchEvent(new Event('submit',{cancelable:true}));
    }""")
    assert page.evaluate("window.clarificationPosts.length") == 1
    page.evaluate("window.resolveSubmission({id:'research-run',state:'queued'})")
    page.wait_for_function(
        "document.querySelector('#clarification-card').classList.contains('hidden')"
    )


def test_accepted_revision_is_hidden_but_new_followup_remains_answerable(research_page):
    page = research_page
    page.evaluate(
        """preparation => {
      activeRun={id:'research-run',state:'waiting_for_user'};
      answeredClarificationRevisions.set('research-run',1);
      api=async () => preparation;
    }""",
        _clarification_fixture(),
    )
    page.evaluate("async () => await loadPreparation(activeRun)")
    assert page.locator("#clarification-card").is_hidden()
    followup = _clarification_fixture()
    followup["revision"] = 3
    followup["decision"]["questions"][0].update(
        id="area", prompt="Do you need total current or current density?"
    )
    page.evaluate("preparation => {api=async () => preparation}", followup)
    page.evaluate("async () => await loadPreparation(activeRun)")
    assert page.locator("#clarification-card").is_visible()
    page.locator('#clarification-questions textarea[data-question-id="area"]').fill(
        "Current density only."
    )
    assert page.locator("#clarification-questions textarea").input_value() == (
        "Current density only."
    )


def test_accepted_snapshot_revision_does_not_reopen_during_stale_run_poll(research_page):
    page = research_page
    preparation = _clarification_fixture()
    page.evaluate(
        """preparation => {
      activeRun={id:'research-run',state:'waiting_for_user'};
      renderClarification(preparation);
      api=async (url,options) => url.endsWith('/clarifications')
        ? {id:'research-run',state:'queued'} : null;
    }""",
        preparation,
    )
    page.locator("#clarification-questions textarea").fill("Drive the left boundary.")
    page.locator("#submit-clarification").click()
    page.wait_for_function("!clarificationSubmitting")
    # Accepting answers increments preparation to2 but keeps the old decision
    # until inference produces revision3. A poll can carry a pre-acceptance run.
    preparation["revision"] = 2
    page.evaluate(
        """preparation => {
      setRun({id:'research-run',state:'waiting_for_user'});
      api=async () => preparation;
    }""",
        preparation,
    )
    page.evaluate("async () => await loadPreparation(activeRun)")
    assert page.locator("#clarification-card").is_hidden()


def test_failed_clarification_submission_and_refresh_preserve_typed_answers(research_page):
    page = research_page
    page.evaluate(
        """preparation => {
      activeRun={id:'research-run',state:'waiting_for_user'};
      renderClarification(preparation);
      api=async () => {throw new Error('Connection temporarily unavailable')};
    }""",
        _clarification_fixture(),
    )
    page.locator("#clarification-questions textarea").fill("Drive the left boundary.")
    page.locator("#submit-clarification").click()
    page.wait_for_function("!clarificationSubmitting")
    page.evaluate("async () => await loadPreparation(activeRun)")
    assert page.locator("#clarification-card").is_visible()
    assert page.locator("#clarification-questions textarea").input_value() == (
        "Drive the left boundary."
    )
    assert page.locator("#submit-clarification").is_enabled()


def test_old_repository_submission_cannot_lock_or_unlock_new_clarification(research_page):
    page = research_page
    page.evaluate(
        """preparation => {
      activeRun={id:'research-run',state:'waiting_for_user'};
      renderClarification(preparation);
      window.pendingSubmissions={};
      api=(url,options) => url.endsWith('/clarifications')
        ? new Promise(resolve => {window.pendingSubmissions[url]=resolve})
        : Promise.resolve(null);
    }""",
        _clarification_fixture(),
    )
    page.locator("#clarification-questions textarea").fill("Drive the left boundary.")
    page.locator("#submit-clarification").click()
    next_preparation = _clarification_fixture()
    next_preparation["run_id"] = "second-research-run"
    page.evaluate(
        """preparation => {
      clearSession();
      activeRun={id:'second-research-run',state:'waiting_for_user'};
      renderClarification(preparation);
    }""",
        next_preparation,
    )
    assert page.locator("#clarification-form").evaluate("form => !form.inert")
    assert page.locator("#submit-clarification").is_enabled()
    page.locator("#clarification-questions textarea").fill("Drive the right boundary.")
    page.locator("#submit-clarification").click()
    page.evaluate("""() => {
      window.pendingSubmissions['/api/runs/research-run/clarifications'](
        {id:'research-run',state:'queued'});
    }""")
    page.wait_for_function("answeredClarificationRevisions.has('research-run')")
    assert page.locator("#clarification-form").evaluate("form => form.inert")
    assert page.locator("#submit-clarification").is_disabled()
    page.evaluate("""() => {
      window.pendingSubmissions['/api/runs/second-research-run/clarifications'](
        {id:'second-research-run',state:'queued'});
    }""")
    page.wait_for_function("!clarificationSubmitting")
    assert page.locator("#clarification-card").is_hidden()


def test_returning_to_same_run_does_not_apply_obsolete_submission_response(research_page):
    page = research_page
    page.evaluate(
        """preparation => {
      activeRun={id:'research-run',state:'waiting_for_user'};
      renderClarification(preparation);
      api=url => url.endsWith('/clarifications')
        ? new Promise(resolve => {window.resolveOldSubmission=resolve})
        : Promise.resolve(null);
    }""",
        _clarification_fixture(),
    )
    page.locator("#clarification-questions textarea").fill("Drive the left boundary.")
    page.locator("#submit-clarification").click()
    followup = _clarification_fixture()
    followup["revision"] = 3
    followup["decision"]["questions"][0].update(
        id="sampling", prompt="Which operating points should have spatial profiles?"
    )
    page.evaluate(
        """preparation => {
      clearSession();
      activeRun={id:'research-run',state:'waiting_for_user'};
      renderClarification(preparation);
    }""",
        followup,
    )
    page.locator("#clarification-questions textarea").fill("All requested operating points.")
    page.evaluate("window.resolveOldSubmission({id:'research-run',state:'queued'})")
    page.wait_for_function("answeredClarificationRevisions.has('research-run')")
    assert page.evaluate("activeRun.state") == "waiting_for_user"
    assert page.locator("#clarification-questions textarea").input_value() == (
        "All requested operating points."
    )


def test_failed_results_workbench_displays_reason_without_fabricating_plots(research_page):
    page = research_page
    page.evaluate("""() => {
      const root=document.createElement('div');root.id='failed-result';
      document.querySelector('#workspace-welcome').replaceWith(root);
      AgentKronigResults.render(root,{execution_state:'failed',experiment:{regions:[]},
        manifest:{execution_state:'failed',state:'failed'},
        result:{status:'timed_out',error:'Simulation exceeded the execution time budget.',
          axes:{},datasets:{},operating_points:[],metadata:{}},
        validation:{overall:'failed',checks:[]}});
    }""")
    root = page.locator("#failed-result")
    assert "Simulation exceeded the execution time budget." in root.inner_text()
    assert root.locator(".result-chart-line").count() == 0


def test_saved_results_do_not_expand_repository_and_library_is_paged(research_page):
    page = research_page
    entries = [
        {
            "bundle_run_id": f"run-{i}",
            "name": f"Study {i}",
            "validation_state": "passed",
            "execution_state": "completed",
            "reason": "Checks passed",
            "modified_at": 1_700_000_000 + i,
        }
        for i in range(101)
    ]
    page.evaluate(
        """entries => {
      activeWorkspace={id:'research-workspace'};
      renderExperimentProjects(entries);
    }""",
        entries,
    )
    assert page.locator("#experiment-project-list .experiment-project").count() == 0
    assert page.locator("#experiment-project-count").inner_text() == "101"
    assert (
        page.locator("#experiment-projects").evaluate(
            "section => section.getBoundingClientRect().height"
        )
        < 100
    )
    page.get_by_role("button", name="Browse saved results", exact=True).click()
    assert page.locator("[data-saved-result-row]").count() == 20
    page.get_by_role("button", name="Next results page", exact=True).click()
    assert page.locator("[data-saved-result-row]").count() == 20
    assert "Study 80" in page.locator("#file-viewer-body").inner_text()
    assert page.locator("#file-viewer-body").evaluate("body => body.scrollTop") == 0
    page.get_by_role("searchbox", name="Filter saved results", exact=True).fill("Study 97")
    assert page.locator("[data-saved-result-row]").count() == 1
    page.evaluate("""() => {
      window.openedSavedResult=null;
      api=async url => {
        window.openedSavedResult=url;
        return {manifest:{run_id:'run-97'},bundle_path:'run-97',result:{datasets:{},axes:{}}};
      };
    }""")
    page.get_by_role("button", name="Open results: Study 97", exact=True).click()
    page.wait_for_function("activeResult?.manifest?.run_id === 'run-97'")
    assert page.evaluate("window.openedSavedResult") == (
        "/api/workspaces/research-workspace/saved-results/run-97"
    )


def test_result_library_preserves_search_focus_and_does_not_discard_edits(research_page):
    page = research_page
    page.evaluate("""() => {
      activeWorkspace={id:'research-workspace'};
      renderExperimentProjects([{bundle_run_id:'a',name:'Evidence A',modified_at:2},
        {bundle_run_id:'b',name:'Evidence B',modified_at:1}]);
      activeFile={kind:'text',path:'notes.txt',content:'Original'};
      editingFile={content:'Original'};
      fileEditor.value='Unsaved researcher notes';
    }""")
    page.get_by_role("button", name="Browse saved results", exact=True).click()
    assert page.evaluate("activeFile.path") == "notes.txt"
    assert page.locator("#file-editor").input_value() == "Unsaved researcher notes"
    assert "Save or cancel" in page.locator("#file-viewer-notice").inner_text()
    page.evaluate("editingFile=null")
    page.get_by_role("button", name="Browse saved results", exact=True).click()
    search = page.get_by_role("searchbox", name="Filter saved results", exact=True)
    search.fill("Evidence B")
    page.evaluate("renderExperimentProjects(savedResultEntries)")
    assert search.input_value() == "Evidence B"
    assert search.evaluate("input => input === document.activeElement")
    assert page.locator("[data-saved-result-row]").count() == 1
    assert page.locator("#file-viewer-edit").is_hidden()
    assert page.locator("#file-viewer-download").is_hidden()


def test_library_refresh_and_saved_result_reply_respect_current_view(research_page):
    page = research_page
    page.evaluate("""() => {
      activeWorkspace={id:'research-workspace'};
      renderExperimentProjects([{bundle_run_id:'a',name:'Evidence A',modified_at:1}]);
      openSavedResultsLibrary();
      window.libraryRequests=[];
      api=async url => {
        libraryRequests.push(url);
        if(url.endsWith('/saved-results')) return {entries:[
          {bundle_run_id:'b',name:'Evidence B',modified_at:2}]};
        return new Promise(resolve => {window.replyToSavedResult=resolve;});
      };
    }""")
    page.locator("#file-viewer-refresh").click()
    page.wait_for_function("savedResultEntries[0]?.name === 'Evidence B'")
    assert page.evaluate("libraryRequests") == ["/api/workspaces/research-workspace/saved-results"]
    page.get_by_role("button", name="Open results: Evidence B", exact=True).click()
    page.wait_for_function('typeof replyToSavedResult === "function"')
    page.evaluate("""() => {
      openSavedResultsLibrary();
      replyToSavedResult({manifest:{run_id:'b'},bundle_path:'b',result:{datasets:{},axes:{}}});
    }""")
    page.wait_for_timeout(100)
    assert page.evaluate("activeFile.kind") == "result_library"
    assert page.evaluate("activeResult") is None
