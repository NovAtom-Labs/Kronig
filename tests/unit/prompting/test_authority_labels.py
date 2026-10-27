from pathlib import Path

import yaml

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.prompting.authority import plan_authority_issues
from tcad_agent.prompting.models import IntentField, ResolvedResearchIntent

ROOT = Path(__file__).resolve().parents[3]


def _spec():
    return ExperimentSpec.model_validate(
        yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())
    )


def _intent(path, value):
    return ResolvedResearchIntent(
        task_kind="simulation",
        objective="x",
        fields=(IntentField(path=path, value=value, origin="researcher"),),
    )


def test_a_differently_labelled_record_holding_the_confirmed_value_is_accepted():
    assert plan_authority_issues(_spec(), _intent("profiles.body.species", "acceptor")) == []


def test_a_label_cannot_hide_a_value_that_no_record_holds():
    issues = plan_authority_issues(_spec(), _intent("profiles.body.value", "5e20 cm^-3"))
    assert [issue["intent_path"] for issue in issues] == ["profiles.body.value"]
