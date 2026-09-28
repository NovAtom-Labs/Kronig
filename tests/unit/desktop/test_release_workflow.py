from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def load_workflow() -> dict[str, object]:
    payload = yaml.safe_load((ROOT / ".github/workflows/desktop-build.yml").read_text())
    assert isinstance(payload, dict)
    return payload


def test_linux_package_metadata_identifies_the_project_and_maintainer() -> None:
    package = json.loads((ROOT / "desktop" / "package.json").read_text())

    assert package["homepage"] == "https://github.com/NovAtom-Labs/Quiloo"
    assert package["author"] == {
        "name": "NovAtom Labs",
        "email": "admin@novatomlabs.com",
    }


def test_desktop_test_script_uses_cross_platform_discovery() -> None:
    package = json.loads((ROOT / "desktop" / "package.json").read_text())

    assert package["scripts"]["test"] == "node --test"


def test_release_workflow_gates_publication_on_every_native_build() -> None:
    workflow = load_workflow()
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)

    assert workflow["on"]["push"]["tags"] == ["v*"]
    assert set(jobs) == {"validate", "build", "release"}
    assert jobs["build"]["needs"] == "validate"
    assert jobs["release"]["needs"] == "build"
    assert jobs["release"]["permissions"]["contents"] == "write"
    assert jobs["release"]["if"] == "startsWith(github.ref, 'refs/tags/')"


def test_release_workflow_builds_all_supported_native_targets() -> None:
    workflow = load_workflow()
    rows = workflow["jobs"]["build"]["strategy"]["matrix"]["include"]

    assert {
        (row["runner"], row["platform"], row["arch"])
        for row in rows
    } == {
        ("ubuntu-24.04", "linux", "x64"),
        ("windows-latest", "win", "x64"),
        ("macos-15-intel", "mac", "x64"),
        ("macos-15", "mac", "arm64"),
    }


def test_release_workflow_uses_node_24_generation_actions_and_pinned_linux() -> None:
    workflow = load_workflow()
    jobs = workflow["jobs"]
    uses = {
        step["uses"]
        for job in jobs.values()
        for step in job["steps"]
        if "uses" in step
    }

    assert jobs["validate"]["runs-on"] == "ubuntu-24.04"
    assert jobs["release"]["runs-on"] == "ubuntu-24.04"
    assert uses == {
        "actions/checkout@v7",
        "actions/setup-python@v7",
        "pnpm/action-setup@v6",
        "actions/setup-node@v7",
        "actions/upload-artifact@v7",
        "actions/download-artifact@v7",
    }


def test_release_workflow_limits_write_permission_and_publishes_a_prerelease() -> None:
    workflow = load_workflow()
    assert workflow["permissions"] == {"contents": "read"}
    release = workflow["jobs"]["release"]
    commands = "\n".join(
        str(step.get("run", "")) for step in release["steps"] if isinstance(step, dict)
    )

    assert "scripts/release_artifacts.py collect" in commands
    assert "gh release create" in commands
    assert commands.index("scripts/release_artifacts.py collect") < commands.index(
        "gh release create"
    )
    assert "--prerelease" in commands
    assert "--verify-tag" in commands
    assert 'Agent Kronig 0.1.0 Alpha 12' in commands
    assert "docs/releases/v0.1.0-alpha.12.md" in commands
    assert release["steps"][-1]["env"] == {"GH_TOKEN": "${{ secrets.GITHUB_TOKEN }}"}


def test_signing_secrets_are_scoped_to_the_steps_and_platforms_that_need_them() -> None:
    workflow = load_workflow()
    build = workflow["jobs"]["build"]
    assert build["env"] == {
        "OPENHANDS_SUPPRESS_BANNER": "1",
        "PYTHONUTF8": "1",
    }

    steps = {step.get("name"): step for step in build["steps"] if "name" in step}
    installer_env = steps["Build native installers"]["env"]
    assert set(installer_env) == {
        "CSC_LINK",
        "CSC_KEY_PASSWORD",
        "CSC_IDENTITY_AUTO_DISCOVERY",
    }
    assert "matrix.platform == 'mac'" in installer_env["CSC_LINK"]
    assert "matrix.platform == 'win'" in installer_env["CSC_LINK"]
    assert "matrix.platform == 'mac'" in installer_env["CSC_KEY_PASSWORD"]
    assert "matrix.platform == 'win'" in installer_env["CSC_KEY_PASSWORD"]
    assert steps["Sign Linux update artifact"]["env"] == {
        "DESKTOP_LINUX_SIGNING_PRIVATE_KEY": "${{ secrets.DESKTOP_LINUX_SIGNING_PRIVATE_KEY }}"
    }


def test_native_build_forces_utf8_and_uses_the_signing_safe_builder_wrapper() -> None:
    workflow = load_workflow()
    build = workflow["jobs"]["build"]
    steps = {step.get("name"): step for step in build["steps"] if "name" in step}

    assert build["env"]["PYTHONUTF8"] == "1"
    assert steps["Build native installers"]["run"].startswith(
        "python scripts/build_native_installers.py"
    )


def test_native_build_fetches_the_exact_public_devsim_knowledge_revision() -> None:
    workflow = load_workflow()
    steps = workflow["jobs"]["build"]["steps"]
    names = [step.get("name") for step in steps]
    fetch = steps[names.index("Fetch pinned DEVSIM knowledge source")]
    build = names.index("Build reviewed knowledge index")

    assert names.index("Fetch pinned DEVSIM knowledge source") < build
    assert "https://github.com/devsim/devsim.git" in fetch["run"]
    assert "43b41ca845184c47e22b72d144db7e7db8509377" in fetch["run"]
    assert "--depth 1" in fetch["run"]


def test_native_build_fetches_pinned_official_devsim_documentation() -> None:
    workflow = load_workflow()
    steps = workflow["jobs"]["build"]["steps"]
    names = [step.get("name") for step in steps]
    fetch = steps[names.index("Fetch pinned DEVSIM documentation")]
    build = names.index("Build reviewed knowledge index")

    assert names.index("Fetch pinned DEVSIM documentation") < build
    assert "https://github.com/devsim/devsim_documentation.git" in fetch["run"]
    assert "8fbe81b5719307d654f37d630cf043dc6ae0512e" in fetch["run"]
    assert "devsim/documentation" in fetch["run"]


def test_native_build_configures_a_portable_devsim_runtime_before_tests() -> None:
    workflow = load_workflow()
    steps = workflow["jobs"]["build"]["steps"]
    names = [step.get("name") for step in steps]

    configure = steps[names.index("Configure simulator runtime")]
    verify = names.index("Verify Python application")

    assert names.index("Configure simulator runtime") < verify
    assert configure["run"] == "python scripts/configure_ci_environment.py"


def test_linux_build_installs_the_devsim_math_runtime_before_importing() -> None:
    workflow = load_workflow()
    steps = workflow["jobs"]["build"]["steps"]
    names = [step.get("name") for step in steps]

    install = steps[names.index("Install Linux DEVSIM math runtime")]

    assert install["if"] == "matrix.platform == 'linux'"
    assert "libopenblas-dev" in install["run"]
    assert names.index("Install Linux DEVSIM math runtime") < names.index(
        "Verify Python application"
    )


def test_windows_build_installs_the_official_devsim_math_runtime() -> None:
    workflow = load_workflow()
    steps = workflow["jobs"]["build"]["steps"]
    names = [step.get("name") for step in steps]

    install = steps[names.index("Install Windows DEVSIM math runtime")]

    assert install["if"] == "matrix.platform == 'win'"
    assert 'mkl==2025.2.0' in install["run"]
    assert names.index("Install Windows DEVSIM math runtime") < names.index(
        "Verify Python application"
    )


def test_native_build_executes_the_frozen_devsim_sidecar_before_packaging() -> None:
    workflow = load_workflow()
    steps = workflow["jobs"]["build"]["steps"]
    names = [step.get("name") for step in steps]

    smoke = steps[names.index("Smoke test frozen DEVSIM sidecar")]

    assert "scripts/smoke_desktop_sidecars.py" in smoke["run"]
    assert "desktop/resources" in smoke["run"]
    assert names.index("Build target-native Python sidecars") < names.index(
        "Smoke test frozen DEVSIM sidecar"
    )
    assert names.index("Smoke test frozen DEVSIM sidecar") < names.index(
        "Build native installers"
    )
