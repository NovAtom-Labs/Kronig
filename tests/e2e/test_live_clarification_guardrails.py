"""Opt-in varied researcher requests, not production prompt matching rules."""

import json
import os
from pathlib import Path

import pytest

from tcad_agent.prompting.clarifications import bind_answers
from tcad_agent.prompting.models import ClarificationAnswer
from tcad_agent.prompting.service import build_default_prompt_preparation

CASES = [
    (
        "unequal-metal-equilibrium",
        "Model a 2.4 um long one-dimensional silicon slab uniformly doped with phosphorus "
        "at 3e15 cm^-3. The left metal work function is 4.25 eV and the right is 4.70 eV. "
        "Both contacts are grounded. Find the equilibrium potential, electric field, bands, "
        "carrier profiles and current densities using Fermi statistics and Klaassen mobility.",
        {
            "physics": "315 K. Fermi statistics and Klaassen mobility. No additional recombination "
            "model is requested for this equilibrium study.",
            "contacts": "Both grounded metal contacts. Left 4.25 eV, right 4.70 eV. Treat metal "
            "semiconductor boundaries physically, not as ohmic substitutes.",
            "regions": "One silicon slab from 0 to 2.4 um, phosphorus 3e15 cm^-3 throughout.",
        },
    ),
    (
        "quasistatic-gate-stack",
        "Study a one-dimensional MOS stack with 7 nm SiO2 over 0.8 um of p-silicon, "
        "uniform boron 8e15 cm^-3, and a 4.25 eV gate. Sweep -2 to +2 V, plot the C-V "
        "curve and compare potential and charge profiles across the stack.",
        {
            "study": "Quasi-static dQ/dV, not AC. Gate -2 to +2 V in 0.1 V increments; "
            "back contact grounded. Extract profiles at -1.5, 0 and +1.5 V.",
            "physics": "300 K. Use Fermi statistics and Klaassen mobility. No extra recombination "
            "model is requested for the quasi-static electrostatic study.",
            "profile_sampling": "Extract spatial profiles at -1.5, 0 and +1.5 V.",
            "contacts": "Metal gate 4.25 eV, grounded ohmic substrate contact. Report capacitance "
            "density in F/cm^2, not absolute capacitance.",
            "regions": "SiO2 7 nm, silicon 0.8 um, planar one-dimensional stack. Relative "
            "permittivities 3.9 for SiO2 and 11.7 for silicon.",
        },
    ),
    (
        "temperature-comparison",
        "Take a 3 um long one-dimensional silicon bar uniformly doped with phosphorus "
        "at 2e16 cm^-3, with ohmic contacts. Hold left at 0 V and right at +0.05 V. "
        "Compare current density and electron mobility at 280, 300 and 330 K using "
        "Fermi statistics and Klaassen mobility. Plot their temperature dependence.",
        {
            "study": "Compare those three temperatures at the same +0.05 V right contact bias; "
            "left grounded. No additional voltage sweep.",
            "physics": "The temperatures are 280, 300 and 330 K. Fermi statistics and Klaassen "
            "mobility, no extra recombination or band-gap model requested.",
            "regions": "One uniform silicon region from 0 to 3 um, phosphorus 2e16 cm^-3.",
            "contacts": "Ohmic at both ends, left 0 V, right +0.05 V. Current density only.",
        },
    ),
    (
        "absolute-current-area",
        "At 300 K, find the total current through a one-dimensional 3 um silicon bar "
        "with uniform phosphorus at 2e16 cm^-3, ohmic ends at 0 and +0.1 V. Use Fermi "
        "statistics and the reviewed constant-mobility model. "
        "Show current and the potential profile.",
        {
            "contacts": "Cross-sectional area is 2 um^2. Left ohmic contact at 0 V, right "
            "ohmic contact at +0.1 V. Report total current in A.",
            "geometry": "One-dimensional bar from 0 to 3 um; cross-sectional area 2 um^2.",
            "study": "A single +0.1 V operating point on the right contact, left grounded.",
            "physics": "300 K, Fermi statistics and the reviewed constant-mobility model. "
            "No additional recombination or BGN is requested.",
        },
    ),
]


@pytest.mark.live_bedrock
@pytest.mark.parametrize("name,prompt,replies", CASES, ids=[case[0] for case in CASES])
def test_live_varied_clarifications_keep_confirmed_inputs(
    pytestconfig, tmp_path, name, prompt, replies
):
    if not pytestconfig.getoption("--run-live-bedrock"):
        pytest.skip("requires --run-live-bedrock")
    if not os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
        pytest.skip("configured Bedrock credential required")
    root = Path(__file__).resolve().parents[2]
    service = build_default_prompt_preparation(root)
    previous, answers, history, records = None, (), [], []
    for revision in range(5):
        outcome = service.prepare(
            root=tmp_path,
            original_prompt=prompt,
            answers=answers,
            previous_decision=previous,
            prior_decisions=history,
        )
        records.append(outcome.decision.model_dump(mode="json"))
        (tmp_path / "clarification-evidence.json").write_text(json.dumps(records, indent=2))
        if outcome.decision.status == "ready":
            assert outcome.compiled_request is not None
            assert all(
                field.origin.value != "platform_default"
                or field.path.startswith(("numerics.", "execution.", "presentation."))
                for field in outcome.decision.intent.fields
            )
            return
        assert outcome.decision.status == "clarification", outcome.decision.summary
        if name in {"unequal-metal-equilibrium", "quasistatic-gate-stack"}:
            assert not any(
                q.reason_kind == "missing" and q.field_path.endswith("work_function")
                for q in outcome.decision.questions
            ), outcome.decision
        supplied = []
        for question in outcome.decision.questions:
            matching = [key for key in replies if question.field_path.startswith(key)]
            response = replies[max(matching, key=len)] if matching else " ".join(replies.values())
            supplied.append(ClarificationAnswer(question_id=question.id, answer=response))
        answers = (*answers, *bind_answers(supplied, outcome.decision.questions, revision))
        previous = outcome.decision
        history.append(previous)
    pytest.fail(f"{name} did not reach a compiled request within the evaluation's five rounds")


@pytest.mark.live_bedrock
def test_live_explicit_unrepresentable_physics_is_not_silently_dropped(pytestconfig, tmp_path):
    if not pytestconfig.getoption("--run-live-bedrock"):
        pytest.skip("requires --run-live-bedrock")
    if not os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
        pytest.skip("configured Bedrock credential required")
    service = build_default_prompt_preparation(Path(__file__).resolve().parents[2])
    outcome = service.prepare(
        root=tmp_path,
        answers=(),
        original_prompt=(
            "At 300 K, calculate current density through a 3 um uniform silicon bar doped "
            "with phosphorus at 2e16 cm^-3. The left ohmic contact is grounded and the right "
            "is at +0.1 V. Use Fermi statistics with explicitly specified constant electron "
            "mobility 0.135 m^2/V/s and hole mobility 0.048 m^2/V/s. These numerical "
            "mobilities are required, do not substitute the simulator defaults."
        ),
    )
    (tmp_path / "clarification-evidence.json").write_text(
        outcome.decision.model_dump_json(indent=2)
    )
    assert outcome.decision.status == "blocked", outcome.decision
    assert outcome.compiled_request is None
