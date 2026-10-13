"""Native saved-result product actions, independent of ephemeral chat."""

import os

import pytest


@pytest.mark.skipif(not os.getenv("KRONIG_TEST_CDP"), reason="requires development Electron")
def test_saved_result_sidebar_exposes_reopen_and_separate_reviewed_recalculation():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(os.environ["KRONIG_TEST_CDP"])
        page = browser.contexts[0].pages[0]
        result = page.evaluate("""() => {
          renderExperimentProjects([{bundle_run_id:'run-independent',
            name:'Saved scientific evidence with a complete inspectable title',
            project_path:null, execution_state:'completed',validation_state:'needs_review',
            failed_check_count:1, reason:'Current conservation needs review'}]);
          const root=document.querySelector('#experiment-project-list');
          const reopen=root.querySelector('[aria-label^="Reopen results"]');
          return {reopen:reopen?.getAttribute('aria-label'),
            recalculate:[...root.querySelectorAll('button')].some(e=>e.textContent==='Recalculate'),
            reason:root.textContent.includes('Current conservation needs review')};
        }""")
        assert (
            result["reopen"]
            == "Reopen results: Saved scientific evidence with a complete inspectable title"
        )
        assert result["recalculate"]
        assert result["reason"]
