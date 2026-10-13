"""Independent low-field uniform-transport reference, not broad physics calibration.

The reference is J = q (mu_n n + mu_p p) V/L with charge neutrality and
mass action. Mobilities are the independently frozen reviewed baseline;
no adapter functions, result densities, or derived result fields form the
expected current. This only calibrates uniform ohmic transport, 250-400 K,
1e15-1e18 cm^-3, 0.5-2 um, 5-40 nm meshes and |V| <= 0.05 V. It does
not calibrate junctions, high-field transport, Klaassen mobility, interfaces,
or temperature gradients. Fermi cases use the nondegenerate limit only.
The pinned DEVSIM 2.9.1 simple_physics baseline uses q=1.6e-19 C; therefore
this parity reference has a 0.136% charge-constant offset from exact SI q.
"""

from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget
from tcad_agent.validation.engine import ValidationEngine

ROOT = Path(__file__).parents[2]


# Independent table: baseline mu_n = 400 (T/300)^-2.42 cm^2/(V s).
# q is the pinned official DEVSIM baseline; minority current is negligible in
# these donor-dominated cases at the 0.05% comparison bound.
@pytest.mark.integration
@pytest.mark.parametrize(
    "density,length,spacing,bias,temperature,mobility,models",
    [
        (1e15, 1.0, 20, 0.01, 300, 400.0, ("boltzmann", "constant_mobility")),
        (1e16, 1.0, 10, -0.01, 300, 400.0, ("boltzmann", "constant_mobility", "srh")),
        (1e17, 0.5, 5, 0.025, 300, 400.0, ("boltzmann", "constant_mobility", "auger")),
        (
            1e18,
            2.0,
            40,
            0.05,
            300,
            400.0,
            ("boltzmann", "constant_mobility", "srh", "auger", "slotboom_bgn"),
        ),
        (1e15, 2.0, 10, -0.005, 250, 621.8399313658987, ("boltzmann", "constant_mobility", "srh")),
        (
            1e16,
            0.5,
            20,
            0.01,
            350,
            275.4537951782533,
            ("boltzmann", "constant_mobility", "srh", "auger"),
        ),
        (
            1e17,
            1.0,
            5,
            -0.025,
            400,
            199.3922383559036,
            ("boltzmann", "constant_mobility", "slotboom_bgn"),
        ),
        (1e15, 0.5, 10, 0.01, 300, 400.0, ("fermi", "constant_mobility", "srh")),
        (
            1e16,
            2.0,
            20,
            -0.01,
            350,
            275.4537951782533,
            ("fermi", "constant_mobility", "srh", "auger"),
        ),
    ],
)
def test_uniform_low_field_current_matches_independent_reference(
    density,
    length,
    spacing,
    bias,
    temperature,
    mobility,
    models,
    tmp_path: Path,
) -> None:
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "uniform transport reference",
            "dimension": 1,
            "regions": [
                {
                    "id": "medium",
                    "material": "silicon",
                    "x0": "0 m",
                    "x1": f"{length} um",
                    "mesh_spacing": f"{spacing} nm",
                }
            ],
            "profiles": [
                {
                    "kind": "constant",
                    "region": "medium",
                    "species": "donor",
                    "value": f"{density} cm^-3",
                }
            ],
            "contacts": [
                {"id": "left", "location": "x_min", "kind": "ohmic"},
                {"id": "right", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {
                "equations": ["poisson", "electron_continuity", "hole_continuity"],
                "models": models,
                "temperature": f"{temperature} K",
            },
            "study": {"kind": "dc_points", "contact": "right", "values": ["0 V", f"{bias} V"]},
            "observables": [
                "terminal_current",
                "potential",
                "electric_field",
                "electron_density",
                "hole_density",
                "electron_mobility",
                "hole_mobility",
            ],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "reference"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    assert all(point.converged for point in result.bias_points)
    expected = 1.6e-19 * density * 1e6 * mobility * 1e-4 * abs(bias) / (length * 1e-6)
    measured = abs(result.bias_points[-1].terminal_currents_a_per_m2["right"])
    assert measured == pytest.approx(expected, rel=5e-4)
    assert result.metadata["parameter_set_id"] == "novatom.silicon.baseline.2026-09-29.v1"
    report = ValidationEngine().validate(result, spec=spec)
    assert report.checks_by_id["terminal-current-conservation"].status == "passed"
    assert report.checks_by_id["electric-field-potential-gradient"].status == "passed"
    assert report.checks_by_id["nonnegative-carrier-density"].status == "passed"
