import pytest

from tcad_agent.results.datasets import Dataset, ScientificAxis
from tcad_agent.results.models import CanonicalResult, OperatingPoint
from tcad_agent.validation.refinement import mesh_comparison, refined_spec


def test_refinement_also_halves_automatically_resolved_profile_landmarks(tmp_path, valid_spec):
    import json

    from tcad_agent.adapters.devsim.compiler import DevsimAdapter
    from tcad_agent.domain.models import ExperimentSpec

    payload = valid_spec.model_dump(mode="json")
    payload["profiles"] = [
        {
            "kind": "gaussian",
            "region": valid_spec.regions[0].id,
            "species": "acceptor",
            "peak": "1e16 cm^-3",
            "center": "0.5 um",
            "standard_deviation": "1 nm",
        }
    ]
    spec = ExperimentSpec.model_validate(payload)
    adapter = DevsimAdapter.from_defaults()
    adapter.compile(spec, tmp_path / "coarse")
    fine = refined_spec(spec)
    adapter.compile(fine, tmp_path / "fine")
    old = json.loads((tmp_path / "coarse/input.json").read_text())
    new = json.loads((tmp_path / "fine/input.json").read_text())

    def anchor(p):
        return next(a for a in p["mesh_anchors"] if a["source"] == "profile:gaussian:center")

    assert anchor(old)["spacing_cm"] == pytest.approx(2.5e-8)
    assert anchor(new)["spacing_cm"] == pytest.approx(1.25e-8)
    assert fine.profiles == spec.profiles


def test_exact_discontinuous_edge_fields_compare_only_inside_material_regions():
    def stack(x):
        return CanonicalResult(
            backend="devsim",
            status="completed",
            axes={"x": ScientificAxis(id="x", kind="position", label="x", unit="m", values=x)},
            datasets={
                "electric_field": Dataset(
                    id="electric_field",
                    label="E",
                    unit="V/m",
                    axes=("x",),
                    shape=(4,),
                    centering="edge",
                    values=(1, 1, 2, 2),
                )
            },
            operating_points=(OperatingPoint(index=0, state="converged", coordinates={"bias": 0}),),
            metadata={
                "region_domains": [
                    {"id": "first", "x0_m": 0, "x1_m": 1},
                    {"id": "second", "x0_m": 1, "x1_m": 2},
                ]
            },
        )

    comparison = mesh_comparison(stack((0.5, 0.9, 1.1, 1.5)), stack((0.6, 0.95, 1.05, 1.4)))
    assert comparison["status"] == "passed", comparison
    assert comparison["metrics"][0]["relative_linf"] == 0


def test_mesh_comparison_must_compare_the_imaginary_response_too():
    coarse = curve((0.003, 0.004))
    fine = curve((0.003, 0.004))
    name = "capacitance__random"
    coarse = coarse.model_copy(
        update={
            "datasets": {
                name: coarse.datasets[name].model_copy(update={"imaginary_values": (0.003, 0.004)})
            }
        }
    )
    fine = fine.model_copy(
        update={
            "datasets": {
                name: fine.datasets[name].model_copy(update={"imaginary_values": (0.006, 0.008)})
            }
        }
    )
    assert mesh_comparison(coarse, fine)["status"] == "failed"


def curve(values):
    return CanonicalResult(
        backend="devsim",
        status="completed",
        simulator_version="2.9.1",
        axes={"bias": ScientificAxis(id="bias", kind="bias", label="V", unit="V", values=(0, 1))},
        datasets={
            "capacitance__random": Dataset(
                id="capacitance__random",
                label="C",
                unit="F/m^2",
                axes=("bias",),
                shape=(2,),
                values=values,
            )
        },
        operating_points=(
            OperatingPoint(index=0, state="converged", coordinates={"bias": 0}),
            OperatingPoint(index=1, state="converged", coordinates={"bias": 1}),
        ),
    )


def test_refinement_changes_only_mesh_not_physics_or_requested_units(valid_spec):
    fine = refined_spec(valid_spec)
    assert fine.physics == valid_spec.physics
    assert fine.study == valid_spec.study
    assert fine.profiles == valid_spec.profiles
    assert fine.contacts == valid_spec.contacts
    assert fine.display_units == valid_spec.display_units
    for coarse, refined in zip(valid_spec.regions, fine.regions, strict=True):
        assert refined.mesh_spacing.to("m") == pytest.approx(coarse.mesh_spacing.to("m") / 2)


def test_mesh_curve_comparison_has_independent_numerical_criterion():
    good = mesh_comparison(curve((0.003, 0.004)), curve((0.00301, 0.00401)))
    assert good["status"] == "passed"
    bad = mesh_comparison(curve((0.003, 0.004)), curve((0.005, 0.006)))
    assert bad["status"] == "failed"


def test_failed_refinement_cannot_pass_mesh_validation():
    failed = curve((0.003, 0.004)).model_copy(update={"status": "timed_out"})
    assert mesh_comparison(curve((0.003, 0.004)), failed)["status"] == "failed"


@pytest.mark.parametrize(
    ("old", "new", "expected", "current_atol", "domain", "equilibrium"),
    [((1e-8, 2e-8), (-2e-8, 1e-8), "passed", 1e-6, True, True),
     ((1e21, 2e21), (1e21, 3e21), "failed", 1e-6, True, True),
     ((1e12, 2e12), (1e12, 3e12), "failed", 1e-12, True, True),
     ((1e-8, 2e-8), (-2e-8, 1e-8), "failed", 1e-6, False, True),
     ((0, 0), (1e12, 1e12), "failed", 1e-6, True, False)],
)
def test_rate_mesh_comparison_respects_the_continuity_current_noise_bound(
    old, new, expected, current_atol, domain, equilibrium
):
    def rate(values):
        result = curve(values)
        dataset = next(iter(result.datasets.values())).model_copy(
            update={"id": "net_rate", "unit": "m^-3/s", "label": "Net rate"}
        )
        return result.model_copy(update={
            "datasets": {"net_rate": dataset},
            "metadata": {"region_domains": [{"id": "body", "x0_m": 0, "x1_m": 1e-6}]
                         if domain else []},
        })

    comparison = mesh_comparison(rate(old), rate(new), current_absolute_tolerance=current_atol,
                                 equilibrium=equilibrium)
    assert comparison["status"] == expected, comparison
    if expected == "passed":
        # Even the maximum accepted volumetric perturbation must induce less
        # current than the existing 1e-6 A/m² absolute continuity tolerance.
        metric = comparison["metrics"][0]
        induced_current = metric["absolute_floor"] * metric["tolerance"] * 1.602176634e-19 * 1e-6
        assert 0 < induced_current <= current_atol
