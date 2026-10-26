import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


def _javascript_runner() -> str | None:
    return shutil.which("node") or next(
        (
            str(path)
            for path in (
                Path("/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc"),
                Path("/usr/bin/jsc"),
            )
            if path.is_file()
        ),
        None,
    )


def _run_javascript(tmp_path: Path, source: str) -> subprocess.CompletedProcess[str]:
    # File-based execution avoids the Windows command-line length limit.
    script = tmp_path / "assertions.js"
    script.write_text(source, encoding="utf-8")
    return subprocess.run(
        [_javascript_runner() or "", str(script)],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(_javascript_runner() is None, reason="No JavaScript runtime installed")
def test_navigation_guard_prevents_stale_browser_updates(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/ide-state.js").read_text(encoding="utf-8")
    assertions = (project_root / "tests/js/ide_navigation_guard.test.js").read_text(encoding="utf-8")
    completed = _run_javascript(tmp_path, f"{source}\n{assertions}")

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(_javascript_runner() is None, reason="No JavaScript runtime installed")
def test_file_viewer_helpers_preserve_scientific_data_and_safe_markdown(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/file-viewer.js").read_text(encoding="utf-8")
    assertions = (project_root / "tests/js/file_viewer.test.js").read_text(encoding="utf-8")
    completed = _run_javascript(tmp_path, f"{source}\n{assertions}")

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(_javascript_runner() is None, reason="No JavaScript runtime installed")
def test_results_workbench_recognizes_and_summarizes_canonical_results(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/results-workbench.js").read_text(encoding="utf-8")
    assertions = (project_root / "tests/js/results_workbench.test.js").read_text(encoding="utf-8")
    completed = _run_javascript(tmp_path, f"{source}\n{assertions}")

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(_javascript_runner() is None, reason="No JavaScript runtime installed")
def test_scientific_chart_helpers_are_dataset_and_device_neutral(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/scientific-chart.js").read_text(encoding="utf-8")
    assertions = (project_root / "tests/js/scientific_chart.test.js").read_text(encoding="utf-8")
    completed = _run_javascript(tmp_path, f"{source}\n{assertions}")

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(_javascript_runner() is None, reason="No JavaScript runtime installed")
def test_agent_events_reduce_restored_and_live_activity_deterministically(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/ide-events.js").read_text(encoding="utf-8")
    assertions = (project_root / "tests/js/ide_events.test.js").read_text(encoding="utf-8")
    completed = _run_javascript(tmp_path, f"{source}\n{assertions}")

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(_javascript_runner() is None, reason="No JavaScript runtime installed")
def test_agent_markdown_constructs_safe_document_nodes(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/ide-markdown.js").read_text(encoding="utf-8")
    assertions = (project_root / "tests/js/ide_markdown.test.js").read_text(encoding="utf-8")
    completed = _run_javascript(tmp_path, f"{source}\n{assertions}")

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(_javascript_runner() is None, reason="No JavaScript runtime installed")
def test_workbench_layout_preserves_editor_space_and_recovers_preferences(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/ide-layout.js").read_text(encoding="utf-8")
    assertions = (project_root / "tests/js/ide_layout.test.js").read_text(encoding="utf-8")
    completed = _run_javascript(tmp_path, f"{source}\n{assertions}")

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(_javascript_runner() is None, reason="No JavaScript runtime installed")
def test_agent_view_models_group_activity_permissions_and_outcomes(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/ide-agent.js").read_text(encoding="utf-8")
    assertions = (project_root / "tests/js/ide_agent.test.js").read_text(encoding="utf-8")
    completed = _run_javascript(tmp_path, f"{source}\n{assertions}")

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(_javascript_runner() is None, reason="No JavaScript runtime installed")
def test_changes_view_model_handles_text_binary_and_rename_operations(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/ide-changes.js").read_text(encoding="utf-8")
    assertions = (project_root / "tests/js/ide_changes.test.js").read_text(encoding="utf-8")
    completed = _run_javascript(tmp_path, f"{source}\n{assertions}")

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(_javascript_runner() is None, reason="No JavaScript runtime installed")
def test_prompt_clarification_view_preserves_generic_questions_and_answers(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/prompt-clarification.js").read_text(encoding="utf-8")
    assertions = (project_root / "tests/js/prompt_clarification.test.js").read_text(encoding="utf-8")
    completed = _run_javascript(tmp_path, f"{source}\n{assertions}")

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(_javascript_runner() is None, reason="No JavaScript runtime installed")
def test_production_ide_script_parses(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/ide.js").read_text(encoding="utf-8")
    parser = tmp_path / "parse-ide.js"
    parser.write_text(f"new Function({json.dumps(source)});", encoding="utf-8")
    completed = subprocess.run(
        [_javascript_runner() or "", str(parser)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(_javascript_runner() is None, reason="No JavaScript runtime installed")
def test_desktop_bridge_script_parses(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/desktop-bridge.js").read_text(encoding="utf-8")
    parser = tmp_path / "parse-desktop-bridge.js"
    parser.write_text(f"new Function({json.dumps(source)});", encoding="utf-8")
    completed = subprocess.run(
        [_javascript_runner() or "", str(parser)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_production_ide_wires_chat_recovery_file_editing_and_panel_controls() -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/ide.js").read_text(encoding="utf-8")
    permission_source = (project_root / "src/tcad_agent/web/static/ide-agent.js").read_text(encoding="utf-8")

    for required in (
        "refreshCoordinator.request",
        'document.addEventListener("visibilitychange"',
        "setInterval",
        'querySelector("#toggle-agent-panel")',
        'querySelector("#refresh-session")',
        'querySelector("#file-viewer-edit")',
        'querySelector("#file-editor")',
        "/files/content",
        "/approve-category",
        "Approve all like this",
        "Technical details",
        "permission_category",
        "technicalArguments",
        "Reversibility:",
        "refreshCurrentRepository",
        "shouldRefreshRepository(event.kind)",
        "scrollSessionToBottom",
        "renderChatProgress",
        "/runs/active",
        "error.code = data.code",
        "change-validation-link",
        "data-action-id",
        "affectedFilePaths(row, activeWorkspace?.root)",
        "Affected file:",
        "row.validationActionIds.forEach",
        "unlinkedValidationChecks",
        "AgentKronigResults.isCanonicalResultPath",
        "AgentKronigResults.findCanonicalResultPath",
        "AgentKronigResults.render",
        "/results?path=",
        "openCanonicalResult",
        "openManagedResult",
        "/plan/approve",
        "/plan/revise",
        "renderPlan",
        'target.querySelector("summary")?.focus()',
    ):
        assert required in source or required in permission_source

    assert ".slice(0, 12_000)" not in source
    assert "/conversations/" not in source
    assert "conversationId" not in source
    assert "conversationSelect" not in source
    assert "createConversation" not in source
    assert "Working in the repository" not in source
    assert "Run active. Waiting for the next recorded action." not in source
    assert 'addEventListener("keydown"' in source


def test_responsive_styles_keep_agent_panel_available_as_a_drawer() -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/ide.css").read_text(encoding="utf-8")

    assert source.count("{") == source.count("}")
    assert ".edge-reveal-right" in source
    assert ".agent-panel.is-open" in source
    assert "position: fixed" in source
    assert ".file-editor" in source
    assert ".panel-title > span:first-child" in source
    assert ".panel-title > span:last-child" in source
    assert "text-overflow: ellipsis" in source
    assert ".approval-technical" in source
    assert ".is-approve-category" in source
    assert ".research-trail" in source
    assert ".chat-timeline" not in source
    assert "border-left-color: var(--blue)" not in source
    assert "border-left-color: #6b8f83" not in source
    assert ".research-trail-current-marker" not in source
    assert ".results-workbench" in source
    assert ".result-chart" in source
    assert ".result-validation" in source
    assert "height: 100%" in source
    assert re.search(
        r"\.agent-chat\s*\{[^}]*display:\s*flex;[^}]*flex-direction:\s*column",
        source,
        re.DOTALL,
    )


def test_file_viewer_toolbar_stays_compact_across_widths() -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/ide.css").read_text(encoding="utf-8")

    header = re.search(r"\.file-viewer-header\s*\{([^}]*)\}", source, re.DOTALL)
    assert header is not None
    assert "grid-template-columns: minmax(0, 1fr) auto" in header.group(1)
    assert "min-height: 46px" in header.group(1)
    assert "min-height: 72px" not in source
    assert ".file-viewer-meta[hidden] { display: none; }" in source
    assert re.search(
        r"\.file-viewer-actions\s*\{[^}]*overflow-x:\s*auto",
        source,
        re.DOTALL,
    )
    assert ".file-viewer-actions { flex-wrap: wrap; }" not in source


def test_company_lockup_stays_at_far_right_without_header_divider() -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/ide.css").read_text(encoding="utf-8")

    brand = re.search(r"(?m)^\.brand\s*\{([^}]*)\}", source, re.DOTALL)
    header_actions = re.search(r"(?m)^\.header-actions\s*\{([^}]*)\}", source, re.DOTALL)

    assert brand is not None
    assert "border-right" not in brand.group(1)
    assert header_actions is not None
    assert "grid-column: 3" in header_actions.group(1)


def test_desktop_shell_keeps_the_center_canvas_dominant() -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/ide.css").read_text(encoding="utf-8")

    shell = re.search(r"(?m)^\.ide-shell\s*\{([^}]*)\}", source, re.DOTALL)
    header = re.search(r"(?m)^\.ide-header\s*\{([^}]*)\}", source, re.DOTALL)
    workspace_main = re.search(r"(?m)^\.workspace-main\s*\{([^}]*)\}", source, re.DOTALL)
    resizer_marker = re.search(r"(?m)^\.pane-resizer::after\s*\{([^}]*)\}", source, re.DOTALL)

    assert shell is not None
    assert "--pane-gap: 6px" in shell.group(1)
    assert "--pane-radius: 11px" in shell.group(1)
    assert "grid-template-rows: 42px minmax(0, 1fr)" in shell.group(1)
    assert header is not None
    assert "border:" not in header.group(1)
    assert "border-radius" not in header.group(1)
    assert "grid-template-columns: auto minmax(0, 1fr) auto" in header.group(1)
    assert workspace_main is not None
    assert "margin: 4px 3px 6px" in workspace_main.group(1)
    assert "border:" not in workspace_main.group(1)
    assert "border-left" not in workspace_main.group(1)
    assert "border-right" not in workspace_main.group(1)
    assert "border-radius" not in workspace_main.group(1)
    assert resizer_marker is not None
    assert "top: 22%" in resizer_marker.group(1)
    assert "bottom: 22%" in resizer_marker.group(1)
    assert "border-radius: 999px" in resizer_marker.group(1)
    assert ".ide-shell.is-explorer-collapsed" in source
    assert ".ide-shell.is-agent-collapsed" in source
    assert ".ide-shell.is-explorer-collapsed .explorer-resizer" in source
    assert ".ide-shell.is-agent-collapsed .agent-resizer" in source


def test_internal_workbench_hierarchy_is_minimal_and_sidebars_are_secondary() -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/ide.css").read_text(encoding="utf-8")

    def rule(selector: str) -> str:
        match = re.search(rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}", source, re.DOTALL)
        assert match is not None, selector
        return match.group(1)

    tabs = rule(".agent-tabs")
    composer = rule(".message-form")
    message = rule(".message")
    file_header = rule(".file-viewer-header")
    workspace_facts = rule(".workspace-facts")
    result_section = rule(".result-section")

    sidebars = rule(".workspace-browser, .agent-panel")

    assert "border: 0" in sidebars
    assert "border-radius: var(--pane-radius)" in sidebars
    assert "background: var(--surface)" in sidebars
    assert "margin: 5px 3px 6px 6px" in source
    assert "margin: 5px 6px 6px 3px" in source
    assert "margin: 5px 7px 0" in tabs
    assert "border-bottom" not in tabs
    assert "border-radius: 8px" in tabs
    assert "margin: 8px" in composer
    assert "border-top" not in composer
    assert "border-radius: 10px" in composer
    assert "border-bottom" not in message
    assert "margin:" not in file_header
    assert "border-bottom" not in file_header
    assert "background: transparent" in file_header
    assert "display: grid" in workspace_facts
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in workspace_facts
    assert "border-top" not in workspace_facts
    assert ".workspace-facts > div" in source
    assert "background: transparent" in source
    assert "border-radius: 9px" in result_section
    assert source.count("top: 42px") >= 3
    assert "width: min(360px, calc(100vw - 16px))" in source
    assert "width: min(390px, calc(100vw - 16px))" in source
    assert ".ide-shell.is-explorer-collapsed .edge-reveal-left" in source
    assert ".ide-shell.is-agent-collapsed .edge-reveal-right" in source


def test_composer_and_panel_reveal_controls_are_integrated_and_minimal() -> None:
    project_root = Path(__file__).parents[3]
    source = (project_root / "src/tcad_agent/web/static/ide.css").read_text(encoding="utf-8")
    template = (project_root / "src/tcad_agent/web/templates/ide.html").read_text(encoding="utf-8")

    assert 'class="edge-reveal edge-reveal-left"' in template
    assert 'class="edge-reveal edge-reveal-right"' in template
    assert '<span aria-hidden="true">&#8250;</span>' in template
    assert '<span aria-hidden="true">&#8249;</span>' in template
    assert re.search(
        r"\.edge-reveal\s*\{[^}]*top:\s*50%;[^}]*opacity:\s*0",
        source,
        re.DOTALL,
    )
    assert ".edge-reveal:hover" in source
    assert ".edge-reveal:focus-visible" in source
    assert ".ide-shell.is-explorer-open .edge-reveal-left" in source
    assert ".ide-shell.is-agent-open .edge-reveal-right" in source
    assert re.search(
        r"\.message-form\s*\{[^}]*border-radius:\s*10px;[^}]*background:\s*#0d1116",
        source,
        re.DOTALL,
    )
    assert ".message-form:focus-within" in source
    assert re.search(
        r"\.message-form textarea\s*\{[^}]*border:\s*0;[^}]*background:\s*transparent",
        source,
        re.DOTALL,
    )
    assert ".message-form > label" in source


def test_workspace_shell_loads_researcher_facing_experiment_projects() -> None:
    project_root = Path(__file__).parents[3]
    script = (project_root / "src/tcad_agent/web/static/ide.js").read_text(encoding="utf-8")

    assert "/saved-results`" in script
    assert "function renderExperimentProjects" in script
    assert "openSavedResult(experiment.bundle_run_id)" in script
