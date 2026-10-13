from pathlib import Path

import pytest

from tcad_agent.desktop.config import DesktopLaunchConfig, default_data_dir


def test_default_data_dir_uses_platform_conventions() -> None:
    home = Path("/users/researcher")

    assert default_data_dir("Linux", home, {}) == (
        home / ".local" / "share" / "Agent Kronig"
    )
    assert default_data_dir(
        "Linux", home, {"XDG_DATA_HOME": "/mnt/research-data"}
    ) == Path("/mnt/research-data/Agent Kronig")
    assert default_data_dir("Darwin", home, {}) == (
        home / "Library" / "Application Support" / "Agent Kronig"
    )
    assert default_data_dir(
        "Windows", Path("C:/Users/researcher"), {"APPDATA": "C:/Users/researcher/AppData/Roaming"}
    ) == Path("C:/Users/researcher/AppData/Roaming/Agent Kronig")


def test_desktop_launch_config_reads_valid_environment(tmp_path: Path) -> None:
    token = "a" * 43
    data_dir = tmp_path / "agent-kronig-data"
    runner = tmp_path / "agent-kronig-devsim"
    config = DesktopLaunchConfig.from_environment(
        {
            "AGENT_KRONIG_DESKTOP_TOKEN": token,
            "AGENT_KRONIG_DESKTOP_HOST": "127.0.0.1",
            "AGENT_KRONIG_DESKTOP_PORT": "0",
            "AGENT_KRONIG_DATA_DIR": str(data_dir),
            "AGENT_KRONIG_DEVSIM_RUNNER": str(runner),
        }
    )

    assert config.host == "127.0.0.1"
    assert config.port == 0
    assert config.launch_token == token
    assert config.data_dir == data_dir.resolve()
    assert config.protocol_version == 1
    assert config.devsim_runner == runner.resolve()


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({}, "launch token"),
        ({"AGENT_KRONIG_DESKTOP_TOKEN": "short"}, "at least 32 bytes"),
        (
            {
                "AGENT_KRONIG_DESKTOP_TOKEN": "a" * 43,
                "AGENT_KRONIG_DESKTOP_HOST": "0.0.0.0",
            },
            "127.0.0.1",
        ),
    ],
)
def test_desktop_launch_config_rejects_unsafe_environment(
    environment: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        DesktopLaunchConfig.from_environment(environment)


def test_owner_pipe_is_an_explicit_validated_launch_contract(tmp_path: Path) -> None:
    environment = {
        "AGENT_KRONIG_DESKTOP_TOKEN": "x" * 43,
        "AGENT_KRONIG_DATA_DIR": str(tmp_path),
        "AGENT_KRONIG_DESKTOP_OWNER_PIPE": "1",
    }
    assert DesktopLaunchConfig.from_environment(environment).owner_pipe is True
    environment.pop("AGENT_KRONIG_DESKTOP_OWNER_PIPE")
    assert DesktopLaunchConfig.from_environment(environment).owner_pipe is False
    environment["AGENT_KRONIG_DESKTOP_OWNER_PIPE"] = "invalid"
    with pytest.raises(ValueError, match="owner pipe"):
        DesktopLaunchConfig.from_environment(environment)
