from pathlib import Path

import pytest
from openhands.sdk.event import ActionEvent
from openhands.sdk.llm.message import MessageToolCall
from openhands.sdk.security import SecurityRisk
from openhands.sdk.tool import Action
from openhands.sdk.tool.builtins.finish import FinishAction
from openhands.sdk.tool.builtins.invoke_skill import InvokeSkillAction
from openhands.sdk.tool.builtins.think import ThinkAction
from openhands.tools.file_editor.definition import CommandLiteral, FileEditorAction
from openhands.tools.task.definition import TaskAction
from openhands.tools.task_tracker.definition import TaskItem, TaskTrackerAction
from openhands.tools.terminal.definition import TerminalAction

import tcad_agent.agent.policy as policy_module
from tcad_agent.agent.policy import (
    WorkspaceSecurityAnalyzer,
    action_summary,
    classify_action,
)
from tcad_agent.agent.tools import TcadDomainAction
from tcad_agent.ide.models import PermissionCategory, is_run_grantable


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


def action_event(tool_name: str, action: Action | None) -> ActionEvent:
    return ActionEvent(
        thought=[],
        action=action,
        tool_name=tool_name,
        tool_call_id="call-1",
        tool_call=MessageToolCall(
            id="call-1",
            name=tool_name,
            arguments="{}",
            origin="completion",
        ),
        llm_response_id="response-1",
    )


def terminal_event(command: str) -> ActionEvent:
    return action_event("terminal", TerminalAction(command=command))


def file_event(path: str, command: CommandLiteral = "view") -> ActionEvent:
    return action_event(
        "file_editor", FileEditorAction(command=command, path=path)
    )


@pytest.mark.parametrize(
    "command",
    [
        "cat README.md",
        "grep -n TODO src/model.py",
        "pytest -q",
        "git diff",
        "rg TODO src",
        "cp tests/test.py.template tests/test.py",
        "mv draft.txt notes/draft.txt",
        "mkdir -p build/results",
        "touch build/results/.keep",
    ],
)
def test_repository_commands_are_low_risk(workspace: Path, command: str) -> None:
    assert classify_action(workspace, terminal_event(command)) is SecurityRisk.LOW


@pytest.mark.parametrize(
    "command",
    [
        r"C:\hostedtoolcache\windows\Python\3.13.15\x64\python.exe scripts/check.py",
        r'"C:\Program Files\Python\python.exe" scripts/check.py',
    ],
)
def test_windows_python_commands_inside_repository_are_low_risk(
    workspace: Path, command: str
) -> None:
    assert classify_action(workspace, terminal_event(command)) is SecurityRisk.LOW


@pytest.mark.parametrize(
    "command",
    [
        "pip install x",
        "git add src",
        "git commit -am x",
        "git push",
        "rm -rf build",
        "cat /etc/passwd",
        "ls ~",
        "ls $HOME",
        "head -20 ~/notes.txt",
        "curl https://example.com",
        "sed -n 1p ../secret.txt",
    ],
)
def test_external_or_mutating_commands_require_confirmation(
    workspace: Path, command: str
) -> None:
    assert classify_action(workspace, terminal_event(command)) is SecurityRisk.HIGH


def test_repository_file_actions_are_low_risk(workspace: Path) -> None:
    target = workspace / "src" / "model.py"

    assert classify_action(workspace, file_event(str(target))) is SecurityRisk.LOW
    assert (
        classify_action(workspace, file_event(str(target), command="create"))
        is SecurityRisk.LOW
    )


@pytest.mark.parametrize("operation", ["search_web", "fetch_source"])
def test_scientific_web_research_requires_network_approval(
    workspace: Path, operation: str
) -> None:
    event = action_event(
        "tcad_domain",
        TcadDomainAction(operation=operation, payload={"query": "contact equation"}),
    )

    assert classify_action(workspace, event) is SecurityRisk.HIGH
    assert (
        policy_module.permission_category(workspace, event).value
        == "network_access"
    )
    assert "internet" in policy_module.approval_explanation(workspace, event).lower()


def test_terminal_symlink_escape_requires_confirmation(
    workspace: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "external").symlink_to(outside, target_is_directory=True)

    assert (
        classify_action(workspace, terminal_event("cat external/secret.txt"))
        is SecurityRisk.HIGH
    )


@pytest.mark.parametrize(
    "inner_command",
    [
        "python scripts/check.py 2>&1",
        "git --no-pager diff 2>&1",
    ],
)
def test_workspace_cd_wrapper_for_safe_command_is_low_risk(
    workspace: Path, inner_command: str
) -> None:
    command = f'cd "{workspace}" && {inner_command}'

    assert classify_action(workspace, terminal_event(command)) is SecurityRisk.LOW


@pytest.mark.parametrize(
    "command",
    [
        "cat README.md | head -20",
        "pytest -q && python scripts/validate.py",
        "mkdir -p outputs && touch outputs/result.txt",
        "python -c 'import devsim; print(devsim.__version__)' 2>/dev/null",
        "which python && python --version",
        "pip list | head",
        "conda list | head",
    ],
)
def test_provably_safe_composed_repository_commands_are_low_risk(
    workspace: Path, command: str
) -> None:
    assert classify_action(workspace, terminal_event(command)) is SecurityRisk.LOW


def test_composed_external_reads_keep_a_narrow_grantable_category(
    workspace: Path, tmp_path: Path
) -> None:
    external = tmp_path / "shared" / "reference.txt"
    command = f'ls "{external.parent}" && cat "{external}" | head -20'
    event = terminal_event(command)

    assert classify_action(workspace, event) is SecurityRisk.HIGH
    assert policy_module.permission_category(workspace, event).value == "external_file_access"


@pytest.mark.parametrize(
    "command,category",
    [
        ("cat README.md && curl https://example.com", "network_access"),
        ("pytest -q; rm -rf build", "destructive_command"),
        ("git status && git push", "git_mutation"),
    ],
)
def test_composed_commands_never_hide_a_risky_segment(
    workspace: Path, command: str, category: str
) -> None:
    event = terminal_event(command)

    assert classify_action(workspace, event) is SecurityRisk.HIGH
    assert policy_module.permission_category(workspace, event).value == category


@pytest.mark.parametrize(
    "command",
    [
        'cd "/tmp" && python scripts/check.py 2>&1',
        "cd . && rm -rf build",
    ],
)
def test_cd_wrapper_cannot_widen_or_bypass_policy(
    workspace: Path, command: str
) -> None:
    assert classify_action(workspace, terminal_event(command)) is SecurityRisk.HIGH


def test_file_action_outside_workspace_requires_confirmation(workspace: Path) -> None:
    assert (
        classify_action(workspace, file_event("/tmp/external.txt"))
        is SecurityRisk.HIGH
    )


def test_delegated_task_is_medium_risk(workspace: Path) -> None:
    event = action_event(
        "task",
        TaskAction(prompt="Review the device model", subagent_type="code-explorer"),
    )

    assert classify_action(workspace, event) is SecurityRisk.MEDIUM


def test_task_tracker_is_low_risk_workspace_metadata(workspace: Path) -> None:
    event = action_event(
        "task_tracker",
        TaskTrackerAction(
            command="plan",
            task_list=[TaskItem(title="Inspect the repository")],
        ),
    )

    assert classify_action(workspace, event) is SecurityRisk.LOW
    assert action_summary(event) == "task_tracker: update 1 task"


def test_skill_invocation_is_low_risk_context_loading(workspace: Path) -> None:
    event = action_event(
        "invoke_skill",
        InvokeSkillAction(name="devsim-compilation"),
    )

    assert classify_action(workspace, event) is SecurityRisk.LOW
    assert action_summary(event) == "invoke_skill: devsim-compilation"


@pytest.mark.parametrize(
    "tool_name,action,summary",
    [
        ("think", ThinkAction(thought="compare fixes"), "think: internal planning"),
        ("finish", FinishAction(message="done"), "finish: complete response"),
        (
            "tcad_domain",
            TcadDomainAction(operation="validate_spec"),
            "Checking the experiment specification",
        ),
    ],
)
def test_builtin_and_tcad_actions_are_low_risk(
    workspace: Path,
    tool_name: str,
    action: Action,
    summary: str,
) -> None:
    event = action_event(tool_name, action)

    assert classify_action(workspace, event) is SecurityRisk.LOW
    assert action_summary(event) == summary


@pytest.mark.parametrize(
    "operation,summary",
    [
        ("prepare_experiment", "Creating experiment project and approval plan"),
        ("execute_experiment", "Running simulation and building scientific results"),
        ("execute_approved_plan", "Running simulation and building scientific results"),
        ("validate_bundle", "Validating canonical scientific results"),
    ],
)
def test_tcad_actions_expose_scientific_progress_in_plain_language(
    workspace: Path, operation: str, summary: str
) -> None:
    event = action_event("tcad_domain", TcadDomainAction(operation=operation))

    assert action_summary(event) == summary


def test_simulator_execution_requires_plain_language_run_scoped_approval(
    workspace: Path,
) -> None:
    event = action_event(
        "tcad_domain",
        TcadDomainAction(
            operation="execute_experiment",
            payload={"approved_plan_digest": "a" * 64},
        ),
    )

    category = policy_module.permission_category(workspace, event)

    assert classify_action(workspace, event) is SecurityRisk.HIGH
    assert category is PermissionCategory.SIMULATION_EXECUTION
    assert is_run_grantable(category)
    explanation = policy_module.approval_explanation(workspace, event, category)
    assert explanation == (
        "Agent Kronig wants to execute the approved simulation on the selected backend."
    )


def test_digest_only_simulator_execution_uses_same_permission_category(
    workspace: Path,
) -> None:
    event = action_event(
        "tcad_domain",
        TcadDomainAction(
            operation="execute_approved_plan",
            payload={"approved_plan_digest": "a" * 64},
        ),
    )

    assert classify_action(workspace, event) is SecurityRisk.HIGH
    assert (
        policy_module.permission_category(workspace, event)
        is PermissionCategory.SIMULATION_EXECUTION
    )


def test_unknown_action_fails_closed(workspace: Path) -> None:
    assert classify_action(workspace, action_event("mystery", None)) is SecurityRisk.HIGH


@pytest.mark.parametrize(
    "tool_name",
    ["file_editor", "terminal", "task", "task_tracker", "tcad_domain"],
)
def test_invalid_known_tool_action_surfaces_validation_without_approval(
    workspace: Path, tool_name: str
) -> None:
    event = action_event(tool_name, None)

    assert classify_action(workspace, event) is SecurityRisk.LOW
    assert action_summary(event) == f"{tool_name}: invalid or incomplete action"


def test_summary_excludes_file_content_and_clips_commands(workspace: Path) -> None:
    secret = "super-secret-file-content"
    event = action_event(
        "file_editor",
        FileEditorAction(
            command="create",
            path=str(workspace / "result.txt"),
            file_text=secret,
        ),
    )

    assert secret not in action_summary(event)
    assert str((workspace / "result.txt").resolve()) in action_summary(event)
    assert len(action_summary(terminal_event("x" * 1_000))) < 300


def test_security_analyzer_uses_workspace_policy(workspace: Path) -> None:
    analyzer = WorkspaceSecurityAnalyzer(workspace=workspace)

    assert analyzer.security_risk(terminal_event("pytest -q")) is SecurityRisk.LOW
    assert analyzer.security_risk(terminal_event("git push")) is SecurityRisk.HIGH


@pytest.mark.parametrize(
    "command,category,plain_text",
    [
        ("pip install devsim", "package_installation", "install or update software"),
        ("curl https://example.com", "network_access", "connect to the internet"),
        ("ssh tcad-host", "remote_execution", "connect to another computer"),
        ("rm -rf build", "destructive_command", "delete files"),
        ("git push", "git_mutation", "change Git history"),
    ],
)
def test_permission_categories_have_plain_language_explanations(
    workspace: Path, command: str, category: str, plain_text: str
) -> None:
    event = terminal_event(command)

    result = policy_module.permission_category(workspace, event)
    explanation = policy_module.approval_explanation(workspace, event, result)

    assert result.value == category
    assert explanation.startswith("Agent Kronig wants to")
    assert plain_text in explanation
    assert command not in explanation


def test_run_grant_downgrades_only_the_matching_permission_category(
    workspace: Path,
) -> None:
    granted = policy_module.permission_category(workspace, terminal_event("git push"))
    analyzer = WorkspaceSecurityAnalyzer(
        workspace=workspace,
        permission_grants={granted},
    )

    assert analyzer.security_risk(terminal_event("git push")) is SecurityRisk.LOW
    assert analyzer.security_risk(terminal_event("ssh tcad-host")) is SecurityRisk.HIGH
    assert (
        analyzer.security_risk(terminal_event("git status /etc/passwd"))
        is SecurityRisk.HIGH
    )
