from pathlib import Path

from tcad_agent.agent.runtime import build_runtime

ROOT = Path(__file__).parents[3]


def test_runtime_defaults_to_pilot_bedrock_model(monkeypatch) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("TCAD_REASONING_EFFORT", raising=False)

    profile = build_runtime(ROOT)

    assert profile.model == "bedrock/global.anthropic.claude-sonnet-4-6"
    assert profile.reasoning_effort == "medium"


def test_runtime_preserves_model_override_for_future_routing(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "bedrock/openai.gpt-5.6-sol")
    monkeypatch.setenv("TCAD_REASONING_EFFORT", "high")

    profile = build_runtime(ROOT)

    assert profile.model == "bedrock/openai.gpt-5.6-sol"
    assert profile.reasoning_effort == "high"


def test_runtime_loads_product_skills_for_an_empty_research_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_SKILLS_ROOT", str(ROOT / "skills"))

    profile = build_runtime(tmp_path)

    skill_names = {skill.name for skill in profile.context.skills}
    assert "specification" in skill_names
    assert "tcad-research-method" in skill_names
    assert "artifact-intent" in skill_names


def test_runtime_allows_additional_workspace_skills_without_replacing_product_skills(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_SKILLS_ROOT", str(ROOT / "skills"))
    skill_dir = tmp_path / "skills" / "laboratory-convention"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: laboratory-convention\n"
        "description: Use when applying this laboratory's local naming rules.\n"
        "---\n\n"
        "# Laboratory Convention\n\n"
        "Keep sample identifiers unchanged.\n",
        encoding="utf-8",
    )

    profile = build_runtime(tmp_path)

    skill_names = {skill.name for skill in profile.context.skills}
    assert "specification" in skill_names
    assert "laboratory-convention" in skill_names


def test_runtime_carries_always_on_artifact_policy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TCAD_SKILLS_ROOT", str(ROOT / "skills"))

    profile = build_runtime(tmp_path)

    suffix = profile.context.system_message_suffix or ""
    assert "evidence summary" in suffix.lower()
    assert "standalone narrative report" in suffix.lower()
    assert "do not create" in suffix.lower()


def test_runtime_carries_adaptive_scientific_research_policy(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_SKILLS_ROOT", str(ROOT / "skills"))

    profile = build_runtime(tmp_path)

    suffix = (profile.context.system_message_suffix or "").lower()
    assert "local knowledge first" in suffix
    assert "web research" in suffix
    assert "untrusted evidence" in suffix
    assert "do not stop merely because" in suffix
    assert "compile" in suffix and "validate" in suffix
