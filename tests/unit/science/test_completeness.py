from tcad_agent.domain.models import ExperimentSpec, Observable
from tcad_agent.domain.units import QuantityValue
from tcad_agent.science.completeness import ScientificCompletenessEngine
from tcad_agent.science.models import InputAuthority, ResolutionStatus


def test_absolute_current_requires_area_without_device_name_branching(
    valid_spec: ExperimentSpec,
) -> None:
    spec = valid_spec.model_copy(
        update={
            "name": "arbitrary-research-structure",
            "observables": (Observable.ABSOLUTE_TERMINAL_CURRENT,),
        }
    )

    report = ScientificCompletenessEngine().evaluate(spec, "devsim")

    assert not report.ready
    missing = [record for record in report.records if record.status == "clarification_required"]
    assert {record.path for record in missing} == {
        f"contacts.{contact.id}.area" for contact in spec.contacts
    }
    assert all(record.authority is InputAuthority.RESEARCHER for record in missing)


def test_current_density_does_not_require_contact_area(valid_spec: ExperimentSpec) -> None:
    spec = valid_spec.model_copy(
        update={"observables": (Observable.TERMINAL_CURRENT_DENSITY,)}
    )

    report = ScientificCompletenessEngine().evaluate(spec, "devsim")

    assert report.ready
    assert not any(record.path.endswith(".area") for record in report.unresolved)


def test_provided_area_is_recorded_with_researcher_authority(
    valid_spec: ExperimentSpec,
) -> None:
    contacts = tuple(
        contact.model_copy(
            update={"area": QuantityValue.model_validate("2 um^2")}
        )
        for contact in valid_spec.contacts
    )
    spec = valid_spec.model_copy(
        update={
            "contacts": contacts,
            "observables": (Observable.ABSOLUTE_TERMINAL_CURRENT,),
        }
    )

    report = ScientificCompletenessEngine().evaluate(spec, "devsim")

    assert report.ready
    areas = [record for record in report.records if record.path.endswith(".area")]
    assert len(areas) == len(contacts)
    assert all(record.authority is InputAuthority.RESEARCHER for record in areas)
    assert all(record.status is ResolutionStatus.RESOLVED for record in areas)
