from tcad_agent.domain.models import ExperimentSpec


def test_legacy_version_one_spec_loads_without_new_optional_fields() -> None:
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "legacy",
            "dimension": 1,
            "regions": [{"id": "bulk", "material": "silicon", "x0": "0 um", "x1": "1 um"}],
            "profiles": [],
            "contacts": [
                {"id": "left", "location": "x_min", "kind": "ohmic"},
                {"id": "right", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {"equations": ["poisson"]},
            "study": {"kind": "equilibrium"},
            "observables": ["potential"],
        }
    )

    assert spec.interfaces == ()
    assert spec.profiles == ()
