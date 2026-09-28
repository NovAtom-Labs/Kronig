from pathlib import Path

from openhands.sdk.skills import load_skills_from_dir

ROOT = Path(__file__).parents[3]
SKILLS_ROOT = ROOT / "skills"


def test_all_skills_load_through_openhands() -> None:
    _, _, skills = load_skills_from_dir(SKILLS_ROOT)
    assert set(skills) == {
        "specification",
        "capability-checking",
        "devsim-compilation",
        "solver-recovery",
        "result-validation",
        "source-citation",
        "reporting",
        "sentaurus-boundary",
        "tcad-research-method",
        "artifact-intent",
        "physics-model-selection",
        "mesh-design",
    }


def test_skill_descriptions_are_progressive_and_discriminating() -> None:
    _, _, skills = load_skills_from_dir(SKILLS_ROOT)
    for skill in skills.values():
        assert skill.description.startswith("Use when")
        assert len(skill.description) <= 500


def test_tcad_skills_contain_decision_guidance_and_knowledge_routes() -> None:
    required_sections = {
        "specification": ("## Decision guide", "search_knowledge"),
        "devsim-compilation": ("## DEVSIM mental model", "DEVSIM Manual"),
        "solver-recovery": ("## Failure taxonomy", "## Recovery ladder"),
        "result-validation": ("## Scientific checks", "## Numerical checks"),
        "reporting": ("## Deliverable policy", "evidence summary"),
        "tcad-research-method": (
            "## Physics selection",
            "## Adaptive evidence loop",
            "search_web",
            "fetch_source",
            "## Interpretation",
        ),
        "source-citation": (
            "## Source order",
            "## Local-first research loop",
            "untrusted evidence",
            "content hash",
        ),
        "artifact-intent": ("## Decision table", "standalone narrative report"),
    }
    for skill_name, phrases in required_sections.items():
        content = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for phrase in phrases:
            assert phrase in content, f"{skill_name} is missing {phrase!r}"
