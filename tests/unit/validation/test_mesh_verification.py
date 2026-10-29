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
    [
        ((1e-8, 2e-8), (-2e-8, 1e-8), "passed", 1e-6, True, True),
        ((1e21, 2e21), (1e21, 3e21), "failed", 1e-6, True, True),
        ((1e12, 2e12), (1e12, 3e12), "failed", 1e-12, True, True),
        ((1e-8, 2e-8), (-2e-8, 1e-8), "failed", 1e-6, False, True),
        ((0, 0), (1e12, 1e12), "failed", 1e-6, True, False),
    ],
)
def test_rate_mesh_comparison_respects_the_continuity_current_noise_bound(
    old, new, expected, current_atol, domain, equilibrium
):
    def rate(values):
        result = curve(values)
        dataset = next(iter(result.datasets.values())).model_copy(
            update={"id": "net_rate", "unit": "m^-3/s", "label": "Net rate"}
        )
        return result.model_copy(
            update={
                "datasets": {"net_rate": dataset},
                "metadata": {
                    "region_domains": [{"id": "body", "x0_m": 0, "x1_m": 1e-6}] if domain else []
                },
            }
        )

    comparison = mesh_comparison(
        rate(old), rate(new), current_absolute_tolerance=current_atol, equilibrium=equilibrium
    )
    assert comparison["status"] == expected, comparison
    if expected == "passed":
        # Even the maximum accepted volumetric perturbation must induce less
        # current than the existing 1e-6 A/m² absolute continuity tolerance.
        metric = comparison["metrics"][0]
        induced_current = metric["absolute_floor"] * metric["tolerance"] * 1.602176634e-19 * 1e-6
        assert 0 < induced_current <= current_atol


def _partial_profile(x, values, valid, state="converged"):
    return CanonicalResult(
        backend="sentaurus",
        status="completed",
        axes={
            "bias": ScientificAxis(id="bias", kind="bias", label="V", unit="V", values=(0.0,)),
            "x": ScientificAxis(id="x", kind="position", label="x", unit="m", values=x),
        },
        datasets={
            "electron_density": Dataset(
                id="electron_density",
                label="n",
                unit="m^-3",
                axes=("bias", "x"),
                shape=(1, len(x)),
                centering="node",
                values=values,
                validity=valid,
            )
        },
        operating_points=(OperatingPoint(index=0, state=state, coordinates={"bias": 0.0}),),
    )


def test_a_profile_missing_where_the_quantity_does_not_exist_is_compared_where_it_does():
    # Carriers do not exist in an oxide: the first two samples are structurally absent.
    coarse = _partial_profile(
        (0.0, 1.0, 2.0, 3.0), (0.0, 0.0, 5.0, 7.0), (False, False, True, True)
    )
    fine = _partial_profile(
        (0.0, 0.5, 1.0, 1.5, 2.0, 3.0),
        (0, 0, 0, 0, 5.0, 7.0),
        (False, False, False, False, True, True),
    )
    comparison = mesh_comparison(coarse, fine)
    assert comparison["status"] == "passed", comparison
    assert comparison["metrics"][0]["relative_linf"] == 0


def test_the_valid_part_of_a_partial_profile_still_has_to_agree():
    coarse = _partial_profile(
        (0.0, 1.0, 2.0, 3.0), (0.0, 0.0, 5.0, 7.0), (False, False, True, True)
    )
    fine = _partial_profile((0.0, 1.0, 2.0, 3.0), (0.0, 0.0, 5.0, 9.0), (False, False, True, True))
    assert mesh_comparison(coarse, fine)["status"] == "failed"


def _profile(name, unit, x, values):
    return CanonicalResult(
        backend="sentaurus",
        status="completed",
        axes={
            "bias": ScientificAxis(id="bias", kind="bias", label="V", unit="V", values=(0.0,)),
            "x": ScientificAxis(id="x", kind="position", label="x", unit="m", values=x),
        },
        datasets={
            name: Dataset(
                id=name,
                label=name,
                unit=unit,
                axes=("bias", "x"),
                shape=(1, len(x)),
                centering="node",
                values=values,
            )
        },
        operating_points=(OperatingPoint(index=0, state="converged", coordinates={"bias": 0.0}),),
    )


def test_a_charge_step_is_compared_by_its_integral_not_by_one_cell():
    # Same total charge, but the step sits one cell apart on the two meshes.
    coarse = _profile("charge_density", "C/m^3", (0.0, 1.0, 2.0, 3.0, 4.0), (0, 0, 8, 8, 8))
    fine = _profile("charge_density", "C/m^3", (0.0, 1.0, 2.0, 3.0, 4.0), (0, 0, 0, 8, 8))
    pointwise = mesh_comparison(coarse, fine)
    assert pointwise["metrics"][0]["unit"] == "C/m^2"
    assert pointwise["metrics"][0]["compared_as"] == "running integral over position"
    # Pointwise the step would differ by 100%; the integrals differ by one cell of charge (8 of 20).
    assert pointwise["metrics"][0]["relative_linf"] == pytest.approx(0.4)
    more_charge = _profile("charge_density", "C/m^3", (0.0, 1.0, 2.0, 3.0, 4.0), (0, 0, 8, 16, 16))
    assert mesh_comparison(coarse, more_charge)["status"] == "failed"


def test_energies_and_currents_below_their_noise_floor_are_not_compared_relatively():
    noise_a = _profile("fermi_level", "eV", (0.0, 1.0), (1e-9, 2e-9))
    noise_b = _profile("fermi_level", "eV", (0.0, 1.0), (3e-9, -1e-9))
    assert mesh_comparison(noise_a, noise_b)["status"] == "passed"
    real_a = _profile("fermi_level", "eV", (0.0, 1.0), (0.5, 0.6))
    real_b = _profile("fermi_level", "eV", (0.0, 1.0), (0.6, 0.7))
    assert mesh_comparison(real_a, real_b)["status"] == "failed"
    current_a = _profile("terminal_current", "A/m^2", (0.0, 1.0), (1.0, 2.0))
    current_b = _profile("terminal_current", "A/m^2", (0.0, 1.0), (2.0, 1.0))
    assert mesh_comparison(current_a, current_b)["status"] == "failed"
    assert mesh_comparison(current_a, current_b, current_absolute_tolerance=100.0)["status"] == (
        "passed"
    )


def test_invalid_samples_from_a_failed_solve_are_still_a_failure():
    coarse = _partial_profile(
        (0.0, 1.0, 2.0, 3.0), (1, 1, 5.0, 7.0), (False, True, True, True), state="failed"
    )
    fine = _partial_profile((0.0, 1.0, 2.0, 3.0), (1, 1, 5.0, 7.0), (True, True, True, True))
    comparison = mesh_comparison(coarse, fine)
    assert comparison["status"] == "failed"


def test_a_step_function_of_doping_does_not_fail_on_the_shared_interface_vertex():
    # The interface appears twice (the copies differ by rounding) and the shared vertex carries
    # the left-hand value, so interpolating across it would measure the cell size.
    coarse = _profile(
        "band_gap_narrowing",
        "eV",
        (0.0, 1.0, 2.0, 2.0 + 1e-12, 4.0, 6.0, 8.0),
        (6, 6, 6, 6, 1, 1, 1),
    )
    fine = _profile(
        "band_gap_narrowing",
        "eV",
        (0.0, 1.0, 2.0, 2.0 + 1e-12, 3.0, 4.0, 5.0, 6.0, 8.0),
        (6, 6, 6, 6, 1, 1, 1, 1, 1),
    )
    assert mesh_comparison(coarse, fine)["status"] == "passed"


def test_a_doping_step_is_compared_by_its_integral_across_meshes():
    # The same step, stored on a coarse and a fine mesh: a vertex-based profile can only place
    # it to within one cell, so the maxima differ by half the step however fine the mesh.
    coarse = _profile("net_doping", "m^-3", (0.0, 1.0, 2.0, 3.0), (-8, -8, 2, 2))
    fine = _profile("net_doping", "m^-3", (0.0, 0.5, 1.0, 1.5, 2.0, 3.0), (-8, -8, -8, 2, 2, 2))
    metric = mesh_comparison(coarse, fine)["metrics"][0]
    assert metric["unit"] == "m^-2" and metric["compared_as"] == "running integral over position"
    assert metric["relative_linf"] < 0.5  # pointwise this is a 100% disagreement at x = 1.5

def test_leakage_below_the_current_tolerance_is_not_a_response_to_compare_when_biased():
    coarse = _profile("terminal_current", "A/m^2", (0.0, 1.0), (1e-9, 1e-9))
    fine = _profile("terminal_current", "A/m^2", (0.0, 1.0), (5.9e-6, -2e-9))
    assert mesh_comparison(coarse, fine, current_absolute_tolerance=1e-5)["status"] == "passed"
    real = _profile("terminal_current", "A/m^2", (0.0, 1.0), (1.0, 2.0))
    assert mesh_comparison(real, fine, current_absolute_tolerance=1e-5)["status"] == "failed"


def test_convergence_summary_reports_observed_order_and_a_fine_grid_index() -> None:
    from tcad_agent.validation.refinement import convergence_summary

    def comparison(error):
        return {"metrics": [{"dataset": "potential", "relative_linf": error}]}

    summary = convergence_summary([comparison(0.16), comparison(0.08), comparison(0.04)])
    entry = summary["datasets"]["potential"]
    assert entry["observed_order"] == pytest.approx(1.0)
    assert entry["gci_fine"] == pytest.approx(1.25 * 0.04)  # Fs * e / (2**1 - 1)
    assert summary["worst_gci"] == entry["gci_fine"]
    wobble = convergence_summary([comparison(0.02), comparison(0.05)])
    assert wobble["datasets"]["potential"]["gci_fine"] is None  # no index without contraction
    fast = convergence_summary([comparison(0.8), comparison(0.001)])
    assert fast["datasets"]["potential"]["observed_order"] == 2.0  # clamped, never claimed higher


def test_the_current_noise_floor_follows_the_highest_doping_whatever_its_shape() -> None:
    from types import SimpleNamespace

    from tcad_agent.domain.units import QuantityValue
    from tcad_agent.validation.engine import _peak_doping_cm3

    def q(text):
        return QuantityValue.model_validate(text)

    spec = SimpleNamespace(
        profiles=(
            SimpleNamespace(kind="constant", value=q("1e17 cm^-3")),
            SimpleNamespace(kind="box", value=q("1e20 cm^-3")),
            SimpleNamespace(kind="gaussian", peak=q("5e19 cm^-3")),
            SimpleNamespace(kind="fixed_charge", value=q("1e12 cm^-2")),
        )
    )
    assert _peak_doping_cm3(spec) == pytest.approx(1e20)


def _with_current(result, values):
    current = Dataset(
        id="terminal_current__drain",
        label="I",
        unit="A/m^2",
        axes=("bias",),
        shape=(2,),
        values=values,
    )
    return result.model_copy(update={"datasets": {**result.datasets, current.id: current}})


def test_by_products_do_not_decide_the_verdict_unless_requested():
    coarse = _with_current(curve((0.003, 0.004)), (1.0, 2.0))
    fine = _with_current(curve((0.005, 0.006)), (1.001, 2.001))
    # A requested current is stable; the unrequested capacitance moved 40-60%.
    only_current = mesh_comparison(coarse, fine, requested=frozenset({"terminal_current"}))
    assert only_current["status"] == "passed"
    flagged = {m["dataset"] for m in only_current["metrics"] if m.get("informational")}
    assert flagged == {"capacitance__random"}
    # Asking for the capacitance puts it back in the verdict.
    asked = mesh_comparison(
        coarse, fine, requested=frozenset({"terminal_current", "capacitance"})
    )
    assert asked["status"] == "failed"
    # Nothing is set aside when the request is unknown.
    assert mesh_comparison(coarse, fine)["status"] == "failed"


def test_an_unstable_requested_current_still_fails_with_by_products_set_aside():
    coarse = _with_current(curve((0.003, 0.004)), (1.0, 2.0))
    fine = _with_current(curve((0.003, 0.004)), (1.5, 2.5))
    result = mesh_comparison(coarse, fine, requested=frozenset({"terminal_current_density"}))
    assert result["status"] == "failed"


def _current_pair(result, density, area=0.01):
    datasets = {}
    for name, unit, scale in (
        ("terminal_current_density__body", "A/m^2", 1.0),
        ("absolute_terminal_current__body", "A", area),
    ):
        datasets[name] = Dataset(
            id=name,
            label="I",
            unit=unit,
            axes=("bias",),
            shape=(2,),
            values=tuple(v * scale for v in density),
        )
    return result.model_copy(update={"datasets": {**result.datasets, **datasets}})


def test_a_current_in_amperes_shares_the_noise_floor_of_its_density():
    base = curve((0.003, 0.004))
    # Leakage a million times below the 1e-6 A/m^2 tolerance moves 40% between meshes: noise.
    quiet = mesh_comparison(
        _current_pair(base, (1e-12, 2e-12)),
        _current_pair(base, (1.4e-12, 2.8e-12)),
        current_absolute_tolerance=1e-6,
    )
    body = {m["dataset"]: m["relative_linf"] for m in quiet["metrics"]}
    assert body["terminal_current_density__body"] == 0.0
    assert body["absolute_terminal_current__body"] == 0.0
    # A real current that moves 40% is still a failure in both forms.
    loud = mesh_comparison(
        _current_pair(base, (1.0, 2.0)),
        _current_pair(base, (1.4, 2.8)),
        current_absolute_tolerance=1e-6,
    )
    body = {m["dataset"]: m["relative_linf"] for m in loud["metrics"]}
    assert body["absolute_terminal_current__body"] > 0.2
    assert loud["status"] == "failed"
