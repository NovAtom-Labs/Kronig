"""Optional native DOM regression tests against the actual Electron renderer."""

import os
from pathlib import Path

import pytest


@pytest.mark.skipif(not os.getenv("KRONIG_TEST_CDP"), reason="requires Electron")
def test_metric_evidence_does_not_ellipsis_or_overflow_narrow_card():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        page = (
            playwright.chromium.connect_over_cdp(os.environ["KRONIG_TEST_CDP"]).contexts[0].pages[0]
        )
        result = page.evaluate("""() => {
          const card=document.createElement('div');
          card.className='result-metric'; card.style.width='150px';
          const value=document.createElement('div');value.className='result-metric-value';
          value.innerHTML='<strong>13 passed</strong><small>0 failed · 7 not applicable</small>';
          card.append(value);document.body.append(card);
          const strong=value.querySelector('strong');
          const result={ellipsis:getComputedStyle(strong).textOverflow,
            clipped:strong.scrollWidth>strong.clientWidth,overflow:value.scrollWidth>value.clientWidth};
          card.remove();return result;
        }""")
        assert result["ellipsis"] != "ellipsis"
        assert not result["clipped"]
        assert not result["overflow"]


@pytest.mark.skipif(
    not os.getenv("KRONIG_TEST_CDP"), reason="requires a development Electron window"
)
def test_native_results_commands_use_compact_themed_controls():
    from playwright.sync_api import sync_playwright

    static = Path(__file__).parents[3] / "src/tcad_agent/web/static"
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(os.environ["KRONIG_TEST_CDP"])
        page = browser.contexts[0].pages[0]
        page.add_style_tag(content=(static / "ide.css").read_text())
        result = page.evaluate("""() => {
          const bar=document.createElement('div'); bar.className='result-command-bar';
          const button=document.createElement('button');
          button.className='result-popout'; button.textContent='Open in window';
          bar.append(button);document.body.append(bar);
          const style=getComputedStyle(button);
          const project=document.createElement('article');project.className='experiment-project';
          project.style.width='180px';
          const name=document.createElement('strong');
          name.textContent='Full_scientific_result_with_a_long_inspectable_name';
          project.append(name);document.body.append(project);
          const result={font:parseFloat(style.fontSize),radius:parseFloat(style.borderRadius),
            height:button.getBoundingClientRect().height,
            nameWhiteSpace:getComputedStyle(name).whiteSpace,
            nameOverflow:project.scrollWidth>project.clientWidth};
          bar.remove();project.remove();return result;
        }""")
        assert result["font"] <= 14
        assert result["radius"] >= 6
        assert result["height"] <= 36
        assert result["nameWhiteSpace"] == "normal"
        assert not result["nameOverflow"]


@pytest.mark.skipif(
    not os.getenv("KRONIG_TEST_CDP"), reason="requires a development Electron window"
)
def test_results_render_mixed_validation_and_isolate_section_failures():
    from playwright.sync_api import sync_playwright

    source = Path(__file__).parents[3] / "src/tcad_agent/web/static/results-workbench.js"
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(os.environ["KRONIG_TEST_CDP"])
        page = browser.contexts[0].pages[0]
        page.add_script_tag(content=source.read_text())
        result = page.evaluate("""() => {
          const root = document.createElement('div');
          const payload = {experiment: {name:'DOM regression', regions:[]},
            result: {status:'completed', fields:{}, datasets:{}, bias_points:[]},
            validation: {overall:'needs_review', checks:[
              {id:'convergence', status:'failed', message:'Point 2 failed'},
              {id:'structural', status:'passed', message:'Structure valid'},
              {id:'equilibrium', status:'not_applicable', message:'Biased study'}]}};
          AgentKronigResults.render(root, payload);
          const text = root.textContent;
          const brokenRoot = document.createElement('div');
          AgentKronigResults.render(brokenRoot,
            {...payload, experiment:{...payload.experiment,regions:{}}});
          return {text, sections:root.querySelectorAll('.result-section').length,
            brokenText:brokenRoot.textContent,
            errors:brokenRoot.querySelectorAll('[role=alert]').length};
        }""")
        assert "Point 2 failed" in result["text"]
        assert "needs review" in result["text"].lower()
        assert result["sections"] >= 3
        assert result["errors"] == 1
        assert "Point 2 failed" in result["brokenText"]


@pytest.mark.skipif(
    not os.getenv("KRONIG_TEST_CDP"), reason="requires a development Electron window"
)
def test_operating_point_and_complex_selectors_are_visible():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(os.environ["KRONIG_TEST_CDP"])
        page = browser.contexts[0].pages[0]
        source = Path(__file__).parents[3] / "src/tcad_agent/web/static/results-workbench.js"
        page.add_script_tag(content=source.read_text())
        result = page.evaluate("""() => {
          const root=document.createElement('div'); document.body.append(root);
          AgentKronigResults.render(root, {experiment:{name:'selector test',regions:[]},
            result:{status:'completed',fields:{},bias_points:[],
              axes:{bias:{id:'bias',kind:'bias',label:'Bias',unit:'V',values:[0,1]},
                position:{id:'position',kind:'position',label:'Position',unit:'m',values:[0,1]}},
              datasets:{potential:{id:'potential',label:'Potential',unit:'V',
                axes:['bias','position'],
                shape:[2,2],centering:'node',values:[0,1,1,2],imaginary_values:[0,0,0,0]}}},
            validation:{overall:'passed',checks:[]}});
          const controls=[...root.querySelectorAll('select')];
          const visible=label=>{const e=controls.find(e=>e.getAttribute('aria-label')===label);
            return Boolean(e && getComputedStyle(e).display!=='none');};
          const out={slice:visible('Displayed operating point'),
            mode:visible('Complex result view')};
          root.remove();return out;
        }""")
        assert result == {"slice": True, "mode": True}


@pytest.mark.skipif(
    not os.getenv("KRONIG_TEST_CDP"), reason="requires a development Electron window"
)
def test_results_separate_evidence_counts_and_keep_full_labels_readable():
    from playwright.sync_api import sync_playwright

    static = Path(__file__).parents[3] / "src/tcad_agent/web/static"
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(os.environ["KRONIG_TEST_CDP"])
        page = browser.contexts[0].pages[0]
        page.add_script_tag(content=(static / "results-workbench.js").read_text())
        page.add_style_tag(content=(static / "ide.css").read_text())
        result = page.evaluate("""() => {
          const root=document.createElement('div'); root.style.width='560px';
          document.body.append(root);
          AgentKronigResults.render(root, {execution_state:'completed',deliverable_state:'complete',
            experiment:{name:'Full researcher result name with all scientific context visible',
              regions:[]},
            result:{operating_points:[{state:'converged',coordinates:{bias:0},
              terminal_currents_a_per_m2:{long_contact_label_that_must_remain_inspectable:0}}],
              axes:{frequency:{id:'frequency',kind:'frequency',label:'Frequency',unit:'Hz',values:[1e3,1e4,1e5]}},
              datasets:{admittance:{id:'admittance',label:'Full complex admittance dataset name',
                unit:'S/m^2',
                axes:['frequency'],shape:[3],values:[1,2,3],validity:[true,false,true]}}},
            validation:{overall:'failed',checks:[{id:'current',level:'physical',status:'failed',
              message:'Current residual requires review',measured_value:2.96e-6,limit:1e-6,
              unit:'A/m^2',absolute_tolerance:1e-6,scale:2e-8}]}});
          const states=[...root.querySelectorAll('[data-status-dimension]')]
            .map(e=>e.dataset.statusDimension);
          const text=root.textContent;
          const name=root.querySelector('h1');
          const measurement=root.querySelector('.result-validation small');
          const result={states,text,font:parseFloat(getComputedStyle(measurement).fontSize),
            nameOverflow:getComputedStyle(name).textOverflow,
            label:root.querySelector('.result-dataset-identity')?.textContent,
            rows:root.querySelectorAll('.result-ac-grid tbody tr').length,
            overflow:root.scrollWidth>root.clientWidth};
          const acOnly=document.createElement('div');
          AgentKronigResults.render(acOnly, {result:{operating_points:[],
            axes:{frequency:{id:'frequency',kind:'frequency',unit:'Hz',values:[1e3,1e4]}},
            datasets:{capacitance:{id:'capacitance',unit:'F/m^2',axes:['frequency'],
              shape:[2],values:[1,1]}}}});
          result.acOnlyRows=acOnly.querySelectorAll('.result-ac-grid tbody tr').length;
          root.remove();return result;
        }""")
        assert result["states"] == ["execution", "scientific", "deliverables"]
        assert "1 DC operating point" in result["text"]
        assert "3 AC samples" in result["text"]
        assert "2 valid" in result["text"]
        assert "absolute tolerance 1.000e-6 A/m^2" in result["text"]
        assert "long_contact_label_that_must_remain_inspectable" in result["text"]
        assert result["font"] >= 11
        assert result["nameOverflow"] != "ellipsis"
        assert result["label"] == "Full complex admittance dataset name · run 1 · S/m^2"
        assert result["rows"] == 3
        assert result["acOnlyRows"] == 2
        assert not result["overflow"]


@pytest.mark.skipif(
    not os.getenv("KRONIG_TEST_CDP"), reason="requires a development Electron window"
)
def test_recovery_choice_requests_review_without_executing_and_input_sources_remain_visible():
    from playwright.sync_api import sync_playwright

    static = Path(__file__).parents[3] / "src/tcad_agent/web/static"
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(os.environ["KRONIG_TEST_CDP"])
        page = browser.contexts[0].pages[0]
        page.add_script_tag(content=(static / "ide-agent.js").read_text())
        page.add_script_tag(content=(static / "results-workbench.js").read_text())
        result = page.evaluate("""() => {
          const root=document.createElement('div');
          let review=null;
          root.addEventListener('kronig:review-recovery',event=>{review=event.detail;event.stopPropagation();});
          AgentKronigResults.render(root, {workspace_id:'workspace',saved_bundle_id:'original',
            recovery_actions:['refine_mesh'],result:{status:'completed',fields:{},operating_points:[]},
            validation:{overall:'failed',checks:[]},completeness:{records:[
              {path:'temperature',value:300,authority:'researcher_owned',status:'resolved',source:{id:'reviewed-temperature'}},
              {path:'solver.maximum_iterations',value:100,authority:'platform_reviewed_default',status:'resolved',source:{id:'reviewed-numerical-default'}}]}});
          const button=root.querySelector('[data-recovery-action=refine_mesh]');
          button?.click();
          const out={review,text:root.textContent,
            buttons:[...root.querySelectorAll('[data-recovery-action]')]
              .map(b=>b.dataset.recoveryAction)};
          return out;
        }""")
        assert result["review"] == {
            "workspaceId": "workspace",
            "bundleRunId": "original",
            "action": "refine_mesh",
        }
        assert result["buttons"] == ["refine_mesh", "stop_and_report"]
        assert "Researcher-reviewed inputs" in result["text"]
        assert "reviewed-temperature" in result["text"]
        assert "Platform-controlled settings" in result["text"]
        assert "reviewed-numerical-default" in result["text"]


@pytest.mark.skipif(
    not os.getenv("KRONIG_TEST_CDP"), reason="requires a development Electron window"
)
def test_recovery_results_preserve_comparison_identities_and_acceptance_values():
    from playwright.sync_api import sync_playwright

    static = Path(__file__).parents[3] / "src/tcad_agent/web/static"
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(os.environ["KRONIG_TEST_CDP"])
        page = browser.contexts[0].pages[0]
        page.add_script_tag(content=(static / "results-workbench.js").read_text())
        result = page.evaluate("""() => {
          const root=document.createElement('div');
          AgentKronigResults.render(root, {result:{status:'completed'},
            recovery_comparison:{original_bundle_id:'original-research-result',
              new_bundle_id:'new-reviewed-recovery-result',action:'refine_mesh',
              original_spec_digest:'a'.repeat(64),candidate_spec_digest:'b'.repeat(64),
              preserved_physics_digest:'c'.repeat(64),
              changes:[{path:'regions[0].mesh_spacing',
                before:{magnitude_si:1e-8,dimension:'length'},
                after:{magnitude_si:5e-9,dimension:'length'}}],
              validation_limits:[{name:'current_atol',value:1e-6},
                {name:'current_rtol',value:1e-4}]}});
          return {text:root.querySelector('.result-recovery-comparison')?.textContent,
            rows:root.querySelectorAll('.result-recovery-changes tbody tr').length};
        }""")
        assert result["text"] is not None
        assert "original-research-result" in result["text"]
        assert "new-reviewed-recovery-result" in result["text"]
        assert "regions[0].mesh_spacing" in result["text"]
        assert '"magnitude_si":1e-8' in result["text"]
        assert '"magnitude_si":5e-9' in result["text"]
        assert "Unchanged scientific acceptance values" in result["text"]
        assert "current_atol" in result["text"]
        assert "1.000e-6" in result["text"]
        assert "current_rtol" in result["text"]
        assert "1.000e-4" in result["text"]
        assert "c" * 64 in result["text"]
        assert result["rows"] == 1
