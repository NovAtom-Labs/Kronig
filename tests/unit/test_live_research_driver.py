import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))
from scripts.verify_live_research_workflows import researcher_answer


def test_researcher_answers_specific_question_not_broader_neighbor():
    question = {"id": "gate-step", "field_path": "study.bias_schedule.step"}
    assert (
        researcher_answer(question, {"study": "quasi-static", "study.bias_schedule": "0.1 V"})
        == "0.1 V"
    )


def test_unmapped_researcher_question_is_not_answered_by_assumption():
    assert (
        researcher_answer({"id": "area", "field_path": "contacts.area"}, {"temperature": "300 K"})
        is None
    )


def test_explicit_question_id_answer_has_priority():
    question = {"id": "gate-step", "field_path": "study.bias_schedule.step"}
    assert researcher_answer(question, {"gate-step": "0.2 V", "study": "0.1 V"}) == "0.2 V"
