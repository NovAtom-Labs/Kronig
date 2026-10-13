import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from tcad_agent.ide.changes import WorkspaceChangeTracker, attribute_changes
from tcad_agent.ide.models import IDEEvent


def _initialize_git_repo(root: Path) -> Path:
    root.mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "researcher@example.test"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Researcher"],
        cwd=root,
        check=True,
    )
    return root


def test_change_tracker_reports_only_changes_after_the_baseline(tmp_path: Path) -> None:
    root = _initialize_git_repo(tmp_path / "research")
    tracked = root / "model.py"
    unchanged_dirty = root / "notes.md"
    tracked.write_text("before run\n")
    unchanged_dirty.write_text("already dirty\n")
    baseline = WorkspaceChangeTracker().capture(root)

    tracked.write_text("before run\nafter run\n")
    changes = WorkspaceChangeTracker().compare(root, baseline)

    assert [(row.path, row.operation) for row in changes.files] == [("model.py", "modified")]
    assert changes.files[0].before_sha256 == baseline.files["model.py"].sha256
    assert changes.files[0].additions == 1
    assert changes.files[0].deletions == 0
    assert "notes.md" not in {row.path for row in changes.files}
    assert ".git/config" not in baseline.files


def test_change_tracker_marks_large_binary_comparison_uncertain(tmp_path: Path) -> None:
    target = tmp_path / "large.bin"
    target.write_bytes(b"x" * 64)
    tracker = WorkspaceChangeTracker(hash_limit=32)
    baseline = tracker.capture(tmp_path)

    target.write_bytes(b"y" * 64)
    changes = tracker.compare(tmp_path, baseline)

    assert changes.files[0].path == "large.bin"
    assert changes.files[0].operation == "modified"
    assert changes.files[0].uncertain is True
    assert changes.files[0].diff is None


def test_change_tracker_classifies_create_delete_and_exact_rename(tmp_path: Path) -> None:
    deleted = tmp_path / "deleted.txt"
    renamed = tmp_path / "before.txt"
    deleted.write_text("remove me\n")
    renamed.write_text("same content\n")
    baseline = WorkspaceChangeTracker().capture(tmp_path)

    deleted.unlink()
    renamed.rename(tmp_path / "after.txt")
    (tmp_path / "created.txt").write_text("new\n")
    changes = WorkspaceChangeTracker().compare(tmp_path, baseline)

    assert [(row.path, row.operation, row.previous_path) for row in changes.files] == [
        ("after.txt", "renamed", "before.txt"),
        ("created.txt", "created", None),
        ("deleted.txt", "deleted", None),
    ]


def test_change_tracker_caps_returned_text_diff(tmp_path: Path) -> None:
    target = tmp_path / "large.txt"
    target.write_text("a\n" * 200)
    tracker = WorkspaceChangeTracker(diff_limit=120)
    baseline = tracker.capture(tmp_path)

    target.write_text("b\n" * 200)
    change = tracker.compare(tmp_path, baseline).files[0]

    assert change.diff is not None
    assert len(change.diff.encode("utf-8")) <= 120
    assert change.diff_truncated is True


def test_change_tracker_marks_baseline_truncated_at_file_limit(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")

    baseline = WorkspaceChangeTracker(file_limit=1).capture(tmp_path)

    assert baseline.truncated is True
    assert len(baseline.files) == 1


def test_change_tracker_never_captures_credential_like_paths(tmp_path: Path) -> None:
    secret = "credential-content-must-not-persist"
    for relative in (
        ".env",
        ".env.local",
        ".env.production",
        ".netrc",
        ".npmrc",
        ".pypirc",
        ".gnupg/private.key",
        ".ssh/config",
        ".aws/credentials",
        "secrets/token.txt",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(secret)
    (tmp_path / "model.py").write_text("safe = True\n")

    baseline = WorkspaceChangeTracker().capture(tmp_path)

    assert set(baseline.files) == {"model.py"}
    assert secret not in baseline.model_dump_json()


def test_truncated_comparison_does_not_invent_create_delete_or_rename(
    tmp_path: Path,
) -> None:
    (tmp_path / "b.txt").write_text("b\n")
    tracker = WorkspaceChangeTracker(file_limit=1)
    baseline = tracker.capture(tmp_path)

    (tmp_path / "a.txt").write_text("a\n")
    changes = tracker.compare(tmp_path, baseline)

    assert changes.baseline_truncated is True
    assert changes.files == ()


def test_change_attribution_uses_explicit_successful_action_identity(
    tmp_path: Path,
) -> None:
    target = tmp_path / "model.py"
    target.write_text("before\n")
    tracker = WorkspaceChangeTracker()
    baseline = tracker.capture(tmp_path)
    target.write_text("after\n")
    change_set = tracker.compare(tmp_path, baseline)
    conversation_id = UUID("00000000-0000-0000-0000-000000000001")
    run_id = "00000000-0000-0000-0000-000000000002"
    now = datetime.now(UTC)
    events = (
        IDEEvent(
            id=1,
            conversation_id=conversation_id,
            kind="tool_call_started",
            payload={
                "run_id": run_id,
                "action_id": "edit-1",
                "tool_name": "file_editor",
                "phase": "edit",
                "arguments": {"command": "str_replace", "path": "model.py"},
            },
            created_at=now,
        ),
        IDEEvent(
            id=2,
            conversation_id=conversation_id,
            kind="tool_call_completed",
            payload={
                "run_id": run_id,
                "action_id": "edit-1",
                "tool_name": "file_editor",
                "is_error": False,
                "output": "done",
            },
            created_at=now,
        ),
        IDEEvent(
            id=3,
            conversation_id=conversation_id,
            kind="tool_call_started",
            payload={
                "run_id": run_id,
                "action_id": "validate-1",
                "tool_name": "terminal",
                "phase": "validate",
                "evidence_kind": "validation",
                "validation_scope": "workspace",
                "arguments": {"command": "pytest -q"},
            },
            created_at=now,
        ),
        IDEEvent(
            id=4,
            conversation_id=conversation_id,
            kind="tool_call_completed",
            payload={
                "run_id": run_id,
                "action_id": "validate-1",
                "tool_name": "terminal",
                "is_error": False,
                "output": "1 passed",
                "validated_files": {
                    "model.py": change_set.files[0].after_sha256,
                },
            },
            created_at=now,
        ),
    )

    attributed = attribute_changes(change_set, events)

    assert attributed.files[0].attributed_action_ids == ("edit-1",)
    assert attributed.files[0].attributed_tools == ("file_editor",)
    assert attributed.files[0].validation_action_ids == ("validate-1",)

    stale_validation_events = list(events)
    stale_validation_events[-1] = IDEEvent(
        id=4,
        conversation_id=conversation_id,
        kind="tool_call_completed",
        payload={
            **events[-1].payload,
            "validated_files": {"model.py": "f" * 64},
        },
        created_at=now,
    )
    stale = attribute_changes(change_set, tuple(stale_validation_events))
    assert stale.files[0].validation_action_ids == ()
