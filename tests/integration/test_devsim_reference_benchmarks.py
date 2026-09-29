import json
import math
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.results.derive import DerivationRegistry
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget
from tcad_agent.validation.engine import ValidationEngine

ROOT = Path(__file__).parents[2]
OFFICIAL_INVARIANTS = ROOT / "tests" / "fixtures" / "devsim" / "official-reference-invariants.json"
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def _official_source_root() -> Path:
    source_root = next(
        (
            candidate
            for candidate in (ROOT / "devsim" / "source", ROOT.parent / "devsim" / "source")
            if candidate.is_dir()
        ),
        None,
    )
    if source_root is None:
        pytest.skip("pinned DEVSIM source checkout is unavailable")
    return source_root


def _run_official(relative: str, tmp_path: Path) -> str:
    source_root = _official_source_root()
    script = source_root / relative
    tmp_path.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [resolve_devsim_python(ROOT), str(script)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def _official_invariants() -> dict[str, object]:
    return json.loads(OFFICIAL_INVARIANTS.read_text())


@pytest.mark.integration
def test_abrupt_equilibrium_reference_passes_canonical_physics_checks(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(
        (ROOT / "examples" / "al-pn-al-equilibrium-devsim.yaml").read_text()
    )
    payload["observables"] = sorted(
        set(payload["observables"])
        | {"electrostatic_flux", "charge_density"}
    )
    spec = ExperimentSpec.model_validate(payload)
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "equilibrium-reference"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)

    report = ValidationEngine().validate(result, spec=spec)

    assert result.status == "completed", native.stderr_path.read_text()
    assert report.checks_by_id["electric-field-potential-gradient"].status == "passed"
    assert report.checks_by_id["poisson-residual-consistency"].status == "passed"
    assert report.checks_by_id["built-in-potential-reference"].status == "passed"
    assert report.checks_by_id["equilibrium-terminal-current"].status == "passed"
    assert report.overall == "passed"


@pytest.mark.integration
def test_equilibrium_accepts_hyphenated_contact_identifiers(tmp_path: Path) -> None:
    payload = yaml.safe_load(
        (ROOT / "examples" / "al-pn-al-equilibrium-devsim.yaml").read_text()
    )
    payload["contacts"][0]["id"] = "p-contact"
    payload["contacts"][1]["id"] = "n-contact"
    spec = ExperimentSpec.model_validate(payload)
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "hyphenated-contact-identifiers"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert result.terminals == ("p-contact", "n-contact")
    assert set(result.bias_points[0].terminal_currents_a_per_m2) == {
        "p-contact",
        "n-contact",
    }


@pytest.mark.integration
def test_abrupt_equilibrium_derived_metrics_are_stable_under_mesh_refinement(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(
        (ROOT / "examples" / "al-pn-al-equilibrium-devsim.yaml").read_text()
    )
    payload["observables"] = ["potential", "electric_field"]
    adapter = DevsimAdapter.from_defaults()
    results = []
    for label, spacing in (("coarse", "20 nm"), ("refined", "10 nm")):
        candidate = yaml.safe_load(yaml.safe_dump(payload))
        for region in candidate["regions"]:
            region["mesh_spacing"] = spacing
        spec = ExperimentSpec.model_validate(candidate)
        native = LocalRunner(resolve_devsim_python(ROOT)).run(
            adapter.compile(spec, tmp_path / label), RunBudget(seconds=120)
        )
        result = adapter.normalize(native)
        assert result.status == "completed", native.stderr_path.read_text()
        results.append(result)

    registry = DerivationRegistry.default()
    metrics = []
    for result in results:
        built_in = registry.scalar(
            "built_in_potential", result.datasets["potential"], result.axes
        ).value
        peak = registry.scalar(
            "peak_magnitude", result.datasets["electric_field"], result.axes
        ).value
        metrics.append((built_in, peak))

    assert metrics[0][0] == pytest.approx(metrics[1][0], rel=0.01)
    assert metrics[0][1] == pytest.approx(metrics[1][1], rel=0.08)


@pytest.mark.integration
def test_terminal_current_is_stable_under_bias_step_refinement(tmp_path: Path) -> None:
    payload = yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())
    payload["observables"] = ["terminal_current"]
    adapter = DevsimAdapter.from_defaults()
    currents = []
    for label, step in (("coarse-bias", "0.1 V"), ("refined-bias", "0.05 V")):
        candidate = yaml.safe_load(yaml.safe_dump(payload))
        candidate["study"].update({"start": "0 V", "stop": "0.2 V", "step": step})
        spec = ExperimentSpec.model_validate(candidate)
        native = LocalRunner(resolve_devsim_python(ROOT)).run(
            adapter.compile(spec, tmp_path / label), RunBudget(seconds=120)
        )
        result = adapter.normalize(native)
        assert result.status == "completed", native.stderr_path.read_text()
        currents.append(result.bias_points[-1].terminal_currents_a_per_m2["anode"])

    scale = max(abs(currents[1]), 1e-20)
    assert abs(currents[0] - currents[1]) / scale < 0.01


@pytest.mark.integration
def test_parallel_plate_charge_matches_pinned_official_devsim_example(
    tmp_path: Path,
) -> None:
    source_root = _official_source_root()
    official = source_root / "examples" / "capacitance" / "cap1d.py"
    completed = subprocess.run(
        [resolve_devsim_python(ROOT), str(official)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    match = re.search(r"contact: contact1 charge:\s+([+-]?\d+\.\d+e[+-]\d+)", completed.stdout)
    assert match is not None
    official_charge_c_per_cm2 = float(match.group(1))

    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "official capacitance parity",
            "dimension": 1,
            "regions": [
                {
                    "id": "medium",
                    "material": "generic_dielectric",
                    "relative_permittivity": 3.9,
                    "x0": "0 cm",
                    "x1": "1 cm",
                    "mesh_spacing": "0.1 cm",
                }
            ],
            "profiles": [],
            "contacts": [
                {"id": "contact1", "location": "x_min", "kind": "ideal_gate"},
                {"id": "contact2", "location": "x_max", "kind": "ideal_gate"},
            ],
            "physics": {"equations": ["poisson"]},
            "study": {
                "kind": "dc_points",
                "contact": "contact1",
                "values": ["1 V"],
            },
            "observables": ["potential", "terminal_charge"],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "adapter-capacitance"), RunBudget(seconds=120)
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    adapter_charge_c_per_m2 = result.operating_points[0].terminal_charges_c_per_m2[
        "contact1"
    ]
    assert adapter_charge_c_per_m2 == pytest.approx(
        official_charge_c_per_cm2 * 1e4,
        rel=2e-5,
    )


@pytest.mark.integration
def test_transport_matches_pinned_official_diode_invariant(tmp_path: Path) -> None:
    fixture = _official_invariants()["diode_1d"]
    assert isinstance(fixture, dict)
    stdout = _run_official("examples/diode/diode_1d.py", tmp_path / "official-diode")
    official = {
        float(match.group(1)): float(match.group(2))
        for match in re.finditer(
            rf"^top[ \t]+({NUMBER})[ \t]+{NUMBER}[ \t]+{NUMBER}[ \t]+({NUMBER})$",
            stdout,
            re.MULTILINE,
        )
    }
    expected = {
        float(key): float(value)
        for key, value in dict(fixture["terminal_current_a_per_cm2"]).items()
    }
    assert official == pytest.approx(expected, rel=1e-10, abs=1e-20)

    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "pinned transport parity",
            "dimension": 1,
            "regions": [
                {
                    "id": "left",
                    "material": "silicon",
                    "x0": "0 cm",
                    "x1": "0.5e-5 cm",
                    "mesh_spacing": "1e-7 cm",
                },
                {
                    "id": "right",
                    "material": "silicon",
                    "x0": "0.5e-5 cm",
                    "x1": "1e-5 cm",
                    "mesh_spacing": "1e-7 cm",
                },
            ],
            "profiles": [
                {
                    "kind": "constant",
                    "region": "left",
                    "species": "acceptor",
                    "value": "1e18 cm^-3",
                },
                {
                    "kind": "constant",
                    "region": "right",
                    "species": "donor",
                    "value": "1e18 cm^-3",
                },
            ],
            "contacts": [
                {"id": "top", "location": "x_min", "kind": "ohmic"},
                {"id": "bot", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {
                "equations": ["poisson", "electron_continuity", "hole_continuity"],
                "models": ["boltzmann", "constant_mobility", "srh"],
                "parameters": {
                    "electron_lifetime": "1e-8 s",
                    "hole_lifetime": "1e-8 s",
                },
                "temperature": "300 K",
            },
            "study": {
                "kind": "dc_points",
                "contact": "top",
                "values": ["0 V", "0.1 V", "0.2 V", "0.3 V", "0.4 V", "0.5 V"],
            },
            "observables": [
                "terminal_current",
                "effective_intrinsic_carrier_concentration",
            ],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "adapter-diode"), RunBudget(seconds=120)
    )
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    adapter_current = result.bias_points[-1].terminal_currents_a_per_m2["top"]
    adapter_ni_cm3 = result.datasets[
        "effective_intrinsic_carrier_concentration"
    ].values[0] / 1e6
    official_coefficient = official[0.5] * 1e4 / 1e20
    adapter_coefficient = adapter_current / adapter_ni_cm3**2
    assert adapter_coefficient == pytest.approx(official_coefficient, rel=0.03)


@pytest.mark.integration
def test_small_signal_matches_pinned_official_capacitance_invariant(
    tmp_path: Path,
) -> None:
    fixture = _official_invariants()["ssac_cap"]
    assert isinstance(fixture, dict)
    stdout = _run_official("testing/ssac_cap.py", tmp_path / "official-ssac")
    rows = re.findall(
        rf"^V1\.I[ \t]+({NUMBER})[ \t]+({NUMBER})$|"
        rf"^topbias[ \t]+({NUMBER})[ \t]+({NUMBER})$",
        stdout,
        re.MULTILINE,
    )
    complex_rows = [
        complex(float(real or voltage_real), float(imaginary or voltage_imaginary))
        for real, imaginary, voltage_real, voltage_imaginary in rows
    ]
    assert len(complex_rows) == 4
    official_capacitances = []
    for frequency, current, voltage in zip(
        (1e10, 1e15), complex_rows[::2], complex_rows[1::2], strict=True
    ):
        admittance = -current / voltage
        official_capacitances.append(admittance.imag / (2 * math.pi * frequency))
    expected = float(fixture["capacitance_f_per_cm2"])
    assert official_capacitances == pytest.approx((expected, expected), rel=1e-10)

    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "pinned small signal parity",
            "dimension": 1,
            "regions": [
                {
                    "id": "medium",
                    "material": "generic_dielectric",
                    "relative_permittivity": 3.9,
                    "x0": "0 cm",
                    "x1": "1 cm",
                    "mesh_spacing": "0.1 cm",
                }
            ],
            "profiles": [],
            "contacts": [
                {"id": "top", "location": "x_min", "kind": "ideal_gate"},
                {"id": "bot", "location": "x_max", "kind": "ideal_gate"},
            ],
            "physics": {"equations": ["poisson"]},
            "study": {
                "kind": "frequency",
                "contact": "top",
                "start": "10 GHz",
                "stop": "1 PHz",
                "points": 2,
                "spacing": "log",
                "amplitude": "1 V",
            },
            "observables": ["potential", "terminal_charge"],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "adapter-ssac"), RunBudget(seconds=120)
    )
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    adapter_capacitance = result.datasets["ac_capacitance__top"].values
    assert adapter_capacitance == pytest.approx(
        tuple(value * 1e4 for value in official_capacitances), rel=2e-5
    )


@pytest.mark.integration
def test_interface_flux_matches_pinned_official_two_region_invariant(
    tmp_path: Path,
) -> None:
    fixture = _official_invariants()["cap2_interface"]
    assert isinstance(fixture, dict)
    stdout = _run_official("testing/cap2.py", tmp_path / "official-interface")
    charges = [
        float(value)
        for value in re.findall(r"^([+-]?\d+\.\d+e[+-]\d+)$", stdout, re.MULTILINE)
    ]
    expected = float(fixture["terminal_charge_c_per_cm2"])
    assert charges[0] == pytest.approx(expected, rel=1e-10)
    assert charges[1] == pytest.approx(-expected, rel=1e-10)

    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "pinned interface parity",
            "dimension": 1,
            "regions": [
                {
                    "id": "left",
                    "material": "generic_dielectric",
                    "relative_permittivity": 11.1,
                    "x0": "0 cm",
                    "x1": "0.5 cm",
                    "mesh_spacing": "0.1 cm",
                },
                {
                    "id": "right",
                    "material": "silicon_dioxide",
                    "x0": "0.5 cm",
                    "x1": "1 cm",
                    "mesh_spacing": "0.1 cm",
                },
            ],
            "interfaces": [
                {"id": "boundary", "left_region": "left", "right_region": "right"}
            ],
            "profiles": [],
            "contacts": [
                {"id": "top", "location": "x_min", "kind": "ideal_gate"},
                {"id": "bot", "location": "x_max", "kind": "ideal_gate"},
            ],
            "physics": {"equations": ["poisson"]},
            "study": {"kind": "dc_points", "contact": "top", "values": ["1 V"]},
            "observables": ["potential", "terminal_charge", "electrostatic_flux"],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "adapter-interface"), RunBudget(seconds=120)
    )
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    point = result.operating_points[0]
    assert point.terminal_charges_c_per_m2["top"] == pytest.approx(
        expected * 1e4, rel=2e-5
    )
    flux = result.datasets["electrostatic_flux"].values
    assert max(flux) == pytest.approx(min(flux), rel=1e-10)
