"""Workspace-scoped confirmation policy for OpenHands actions."""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable
from pathlib import Path

from openhands.sdk.event import ActionEvent
from openhands.sdk.security import SecurityAnalyzerBase, SecurityRisk
from openhands.sdk.tool.builtins.finish import FinishAction
from openhands.sdk.tool.builtins.think import ThinkAction
from openhands.tools.file_editor.definition import FileEditorAction
from openhands.tools.task.definition import TaskAction
from openhands.tools.task_tracker.definition import TaskTrackerAction
from openhands.tools.terminal.definition import TerminalAction
from pydantic import Field

from tcad_agent.agent.tools import TcadDomainAction
from tcad_agent.ide.models import PermissionCategory, is_run_grantable
from tcad_agent.security.paths import is_credential_path

_SAFE_COMMANDS = {
    "basename",
    "cargo",
    "cat",
    "cd",
    "cmake",
    "cp",
    "devsim",
    "diff",
    "dirname",
    "find",
    "git",
    "grep",
    "head",
    "ls",
    "make",
    "mkdir",
    "mypy",
    "mv",
    "pytest",
    "pwd",
    "python",
    "python3",
    "rg",
    "ruff",
    "sed",
    "tail",
    "test",
    "touch",
    "wc",
    "which",
    "echo",
}
_SAFE_GIT_COMMANDS = {"branch", "diff", "log", "rev-parse", "show", "status"}
_KNOWN_TOOL_NAMES = {
    "file_editor",
    "finish",
    "task",
    "task_tracker",
    "tcad_domain",
    "terminal",
    "think",
}
_SHELL_CONTROL = re.compile(r"(?:&&|\|\||[;|]|>|<)")
_SHELL_EXPANSION = re.compile(r"[`$]")
_PACKAGE_COMMANDS = {"apt", "apt-get", "brew", "dnf", "npm", "npx", "pip", "pip3", "uv", "yum"}
_NETWORK_COMMANDS = {"curl", "nc", "wget"}
_REMOTE_COMMANDS = {"scp", "ssh"}
_DESTRUCTIVE_COMMANDS = {"dd", "kill", "killall", "pkill", "rm"}
_SYSTEM_COMMANDS = {"chmod", "chown", "docker", "podman", "sudo"}
_READ_ONLY_PACKAGE_COMMANDS = {
    "pip": {"check", "freeze", "list", "show"},
    "pip3": {"check", "freeze", "list", "show"},
    "conda": {"info", "list"},
}
_WINDOWS_EXECUTABLE = re.compile(r'^(?:"?[A-Za-z]:\\)')


def command_tokens(command: str) -> list[str]:
    """Split one supported shell command across POSIX and Windows path syntax."""

    windows_style = bool(_WINDOWS_EXECUTABLE.match(command))
    tokens = shlex.split(command, posix=not windows_style)
    return [token.strip('"') for token in tokens]


def executable_name(token: str) -> str:
    """Return a normalized executable basename for policy and event metadata."""

    name = re.split(r"[\\/]", token)[-1].lower()
    return name.removesuffix(".exe")


def _inside_workspace(workspace: Path, candidate: Path) -> bool:
    root = workspace.expanduser().resolve()
    resolved = candidate.expanduser()
    if not resolved.is_absolute():
        resolved = root / resolved
    resolved = resolved.resolve(strict=False)
    return resolved == root or root in resolved.parents


def _shell_segments(command: str) -> list[list[str]] | None:
    """Parse a bounded shell composition without evaluating expansions."""

    if _SHELL_EXPANSION.search(command):
        return None
    if _WINDOWS_EXECUTABLE.match(command) and not _SHELL_CONTROL.search(command):
        try:
            return [command_tokens(command)]
        except ValueError:
            return None
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return None
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in {"&&", "||", ";", "|"}:
            if not current:
                return None
            segments.append(current)
            current = []
        else:
            current.append(token)
    if not current:
        return None
    segments.append(current)
    return segments


def _normalized_segment(tokens: list[str]) -> tuple[list[str], list[str]] | None:
    """Separate a simple command from bounded file redirections."""

    command: list[str] = []
    redirects: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.isdigit() and index + 1 < len(tokens) and tokens[index + 1] in {
            ">", ">>", "<", "<<", ">&", "<&",
        }:
            index += 1
            token = tokens[index]
        if token in {">", ">>", "<", "<<", ">&", "<&"}:
            if index + 1 >= len(tokens):
                return None
            target = tokens[index + 1]
            if token not in {">&", "<&"} and target != "/dev/null":
                redirects.append(target)
            elif token in {">&", "<&"} and not target.isdigit():
                return None
            index += 2
            continue
        command.append(token)
        index += 1
    return (command, redirects) if command else None


def _segment_categories(workspace: Path, raw: list[str]) -> set[PermissionCategory] | None:
    normalized = _normalized_segment(raw)
    if normalized is None:
        return None
    tokens, redirects = normalized
    executable = executable_name(tokens[0])
    categories: set[PermissionCategory] = set()
    if executable in _READ_ONLY_PACKAGE_COMMANDS:
        if len(tokens) < 2 or tokens[1] not in _READ_ONLY_PACKAGE_COMMANDS[executable]:
            categories.add(PermissionCategory.PACKAGE_INSTALLATION)
    elif executable in _PACKAGE_COMMANDS:
        categories.add(PermissionCategory.PACKAGE_INSTALLATION)
    elif executable in _NETWORK_COMMANDS:
        categories.add(PermissionCategory.NETWORK_ACCESS)
    elif executable in _REMOTE_COMMANDS:
        categories.add(PermissionCategory.REMOTE_EXECUTION)
    elif executable in _DESTRUCTIVE_COMMANDS:
        categories.add(PermissionCategory.DESTRUCTIVE_COMMAND)
    elif executable == "git":
        git_arguments = tokens[1:]
        if git_arguments and git_arguments[0] == "--no-pager":
            git_arguments = git_arguments[1:]
        if not git_arguments or git_arguments[0] not in _SAFE_GIT_COMMANDS:
            categories.add(PermissionCategory.GIT_MUTATION)
    elif executable in _SYSTEM_COMMANDS:
        categories.add(PermissionCategory.SYSTEM_CHANGE)
    elif executable not in _SAFE_COMMANDS:
        categories.add(PermissionCategory.UNRECOGNIZED_ACTION)

    path_tokens = [*tokens[1:], *redirects]
    for token in path_tokens:
        if token.startswith("-") or token.isdigit():
            continue
        candidate = Path(token)
        if is_credential_path(candidate):
            categories.add(PermissionCategory.SENSITIVE_FILE_ACCESS)
        if ".." in candidate.parts or not _inside_workspace(workspace, candidate):
            categories.add(PermissionCategory.EXTERNAL_FILE_ACCESS)
    return categories


def _command_categories(workspace: Path, command: str) -> set[PermissionCategory] | None:
    segments = _shell_segments(command)
    if segments is None:
        return None
    categories: set[PermissionCategory] = set()
    for segment in segments:
        segment_categories = _segment_categories(workspace, segment)
        if segment_categories is None:
            return None
        categories.update(segment_categories)
    return categories


def _terminal_risk(workspace: Path, action: TerminalAction) -> SecurityRisk:
    command = action.command.strip()
    if action.is_input:
        return SecurityRisk.MEDIUM
    if not command:
        return SecurityRisk.HIGH
    categories = _command_categories(workspace, command)
    return SecurityRisk.LOW if categories == set() else SecurityRisk.HIGH


def classify_action(workspace: Path, event: ActionEvent) -> SecurityRisk:
    """Classify an action conservatively against a canonical repository root."""

    action = event.action
    if action is None and event.tool_name in _KNOWN_TOOL_NAMES:
        return SecurityRisk.LOW
    if isinstance(action, FileEditorAction):
        target = Path(action.path)
        if not _inside_workspace(workspace, target) or is_credential_path(target):
            return SecurityRisk.HIGH
        return SecurityRisk.LOW
    if isinstance(action, TerminalAction):
        return _terminal_risk(workspace, action)
    if isinstance(action, TaskTrackerAction):
        return SecurityRisk.LOW
    if isinstance(action, TcadDomainAction):
        if action.operation in {"search_web", "fetch_source"}:
            return SecurityRisk.HIGH
        return SecurityRisk.LOW
    if isinstance(action, (ThinkAction, FinishAction)):
        return SecurityRisk.LOW
    if isinstance(action, TaskAction):
        return SecurityRisk.MEDIUM
    return SecurityRisk.HIGH


def _terminal_permission_category(
    workspace: Path, action: TerminalAction
) -> PermissionCategory:
    categories = _command_categories(workspace, action.command.strip())
    if categories is None:
        return PermissionCategory.COMPLEX_SHELL
    if len(categories) == 1:
        return categories.pop()
    return PermissionCategory.UNRECOGNIZED_ACTION


def permission_category(workspace: Path, event: ActionEvent) -> PermissionCategory:
    """Group a risky action into a deterministic, run-scoped permission."""

    action = event.action
    if isinstance(action, FileEditorAction):
        target = Path(action.path)
        sensitive = is_credential_path(target)
        external = not _inside_workspace(workspace, target)
        if sensitive and external:
            return PermissionCategory.UNRECOGNIZED_ACTION
        if sensitive:
            return PermissionCategory.SENSITIVE_FILE_ACCESS
        if external:
            return PermissionCategory.EXTERNAL_FILE_ACCESS
    if isinstance(action, TerminalAction):
        return _terminal_permission_category(workspace, action)
    if isinstance(action, TcadDomainAction) and action.operation in {
        "search_web",
        "fetch_source",
    }:
        return PermissionCategory.NETWORK_ACCESS
    return PermissionCategory.UNRECOGNIZED_ACTION


_APPROVAL_EXPLANATIONS = {
    PermissionCategory.EXTERNAL_FILE_ACCESS: (
        "Agent Kronig wants to access a file outside the opened project."
    ),
    PermissionCategory.SENSITIVE_FILE_ACCESS: (
        "Agent Kronig wants to access a file that may contain passwords or credentials."
    ),
    PermissionCategory.PACKAGE_INSTALLATION: (
        "Agent Kronig wants to install or update software on this computer."
    ),
    PermissionCategory.NETWORK_ACCESS: (
        "Agent Kronig wants to connect to the internet or transfer data."
    ),
    PermissionCategory.REMOTE_EXECUTION: (
        "Agent Kronig wants to connect to another computer and run a remote operation."
    ),
    PermissionCategory.DESTRUCTIVE_COMMAND: (
        "Agent Kronig wants to delete files or stop a running process."
    ),
    PermissionCategory.GIT_MUTATION: (
        "Agent Kronig wants to change Git history or send changes to a remote repository."
    ),
    PermissionCategory.SYSTEM_CHANGE: (
        "Agent Kronig wants to change system settings, permissions, or managed services."
    ),
    PermissionCategory.COMPLEX_SHELL: (
        "Agent Kronig wants to run a combined shell command that can perform several operations."
    ),
    PermissionCategory.UNRECOGNIZED_ACTION: (
        "Agent Kronig wants to perform a higher-risk action that it cannot classify more narrowly."
    ),
}


def approval_explanation(
    workspace: Path,
    event: ActionEvent,
    category: PermissionCategory | None = None,
) -> str:
    """Explain an approval in plain language without exposing command contents."""

    selected = category or permission_category(workspace, event)
    return _APPROVAL_EXPLANATIONS[selected]


def action_summary(event: ActionEvent) -> str:
    """Return a content-free, bounded description safe for an approval dialog."""

    action = event.action
    if action is None and event.tool_name in _KNOWN_TOOL_NAMES:
        return f"{event.tool_name}: invalid or incomplete action"
    if isinstance(action, FileEditorAction):
        target = Path(action.path).expanduser().resolve(strict=False)
        return f"file_editor {action.command}: {target}"
    if isinstance(action, TerminalAction):
        command = " ".join(action.command.split())
        if len(command) > 220:
            command = f"{command[:217]}..."
        return f"terminal: {command}"
    if isinstance(action, TaskTrackerAction):
        if action.command == "view":
            return "task_tracker: view tasks"
        count = len(action.task_list or ())
        noun = "task" if count == 1 else "tasks"
        return f"task_tracker: update {count} {noun}"
    if isinstance(action, ThinkAction):
        return "think: internal planning"
    if isinstance(action, FinishAction):
        return "finish: complete response"
    if isinstance(action, TcadDomainAction):
        return f"tcad_domain: {action.operation}"
    if isinstance(action, TaskAction):
        description = (action.description or "delegated task").strip()
        return f"task {action.subagent_type}: {description[:180]}"
    return f"{event.tool_name}: unrecognized action"


class WorkspaceSecurityAnalyzer(SecurityAnalyzerBase):
    """Apply Agent Kronig's workspace policy to every OpenHands action."""

    workspace: Path
    permission_grants: set[PermissionCategory] = Field(default_factory=set)
    grant_checker: Callable[[PermissionCategory], bool] | None = Field(
        default=None, exclude=True
    )

    def security_risk(self, action: ActionEvent) -> SecurityRisk:
        risk = classify_action(self.workspace, action)
        if risk is not SecurityRisk.HIGH:
            return risk
        category = permission_category(self.workspace, action)
        if not is_run_grantable(category):
            return risk
        if category in self.permission_grants:
            return SecurityRisk.LOW
        if self.grant_checker is not None and self.grant_checker(category):
            return SecurityRisk.LOW
        return risk
