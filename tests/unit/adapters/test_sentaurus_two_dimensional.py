"""2D structure script, capability rules, and local export with a known synthetic result.

The TDR is a synthetic file in the documented structure, not licensed output. Its potential is
2*X + 3*Y so linear interpolation along a cut must reproduce it exactly.
"""

import copy
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "domain"))
from test_two_dimensional_spec import planar_device

from tcad_agent.adapters.sentaurus.compiler import SentaurusAdapter
from tcad_agent.adapters.sentaurus.mesh import build_sde_script
from tcad_agent.adapters.sentaurus.native_export import build_export
from tcad_agent.adapters.sentaurus.normalizer import SentaurusNormalizer
from tcad_agent.adapters.sentaurus.runtime import SentaurusJobManifest
from tcad_agent.capabilities.models import CapabilityManifest
from tcad_agent.capabilities.service import CapabilityService
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.models import NativeRunResult

VERSION = "O-2018.06-SP2"


def spec_with(mutator=None) -> ExperimentSpec:
    data = copy.deepcopy(planar_device())
    if mutator:
        mutator(data)
    return ExperimentSpec.model_validate(data)


def test_structure_script_places_rectangles_windows_and_contacts() -> None:
    script = build_sde_script(spec_with())
    assert '(position 0.1 0 0) (position 0.2 0.005 0) "Oxide" "insulator")' in script
    assert '(position 0 0.005 0) (position 0.3 0.205 0) "Silicon" "body")' in script
    assert '"win1" "Rectangle" (position 0 0.005 0) (position 0.1 0.055 0)' in script
    assert '"ArsenicActiveConcentration" 1e+20' in script
    assert '(find-edge-id (position 0.15 0 0)) "gate")' in script
    assert '(find-edge-id (position 0.05 0.005 0)) "left")' in script
    assert '(find-edge-id (position 0.15 0.205 0)) "back")' in script
    assert '"MaxLenInt"' not in script  # no region asked for grading here


def test_a_narrow_contact_span_inserts_vertices_so_it_owns_an_edge() -> None:
    script = build_sde_script(
        spec_with(lambda d: d["contacts"][1].update(span=["0 um", "0.08 um"]))
    )
    assert "(sdegeo:insert-vertex (position 0.08 0.005 0))" in script


def test_profiles_need_a_cut_and_absolute_current_needs_a_width() -> None:
    manifest = CapabilityManifest.from_backend("sentaurus")
    check = CapabilityService().check
    no_cut = check(spec_with(lambda d: d.update(profile_cuts=[])), manifest)
    assert [issue.code for issue in no_cut.issues] == ["missing_profile_cut"]
    absolute = check(
        spec_with(lambda d: d.update(observables=["absolute_terminal_current"])), manifest
    )
    assert [issue.code for issue in absolute.issues] == ["missing_device_width"]
    ready = check(
        spec_with(lambda d: d.update(observables=["absolute_terminal_current"], width="10 um")),
        manifest,
    )
    assert ready.status.value == "supported"


def test_devsim_refuses_two_dimensional_structures() -> None:
    decision = CapabilityService().check(spec_with(), CapabilityManifest.from_backend("devsim"))
    assert decision.status.value == "backend_unsupported"


def test_vector_fields_are_refused_along_a_line_cut(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TCAD_SENTAURUS_VERSION", VERSION)
    spec = spec_with(lambda d: d.update(observables=["electric_field"]))
    with pytest.raises(Exception, match="vector fields"):
        SentaurusAdapter.from_defaults("sde").compile(spec, tmp_path / "job")


def _write_tdr(path: Path, drain_volts: float, drain_amps: float) -> None:
    """Silicon rectangle X 0..2 um (lateral), Y 0..1 um (depth); potential = 2X + 3Y."""
    ids = {(ix, iy): ix * 2 + iy for ix in range(3) for iy in range(2)}
    vertices = np.array(
        [(ix, iy) for ix in range(3) for iy in range(2)], dtype=[("x", "<f8"), ("y", "<f8")]
    )
    triangles: list[int] = []
    for ix in range(2):
        a, b, c, d = ids[(ix, 0)], ids[(ix + 1, 0)], ids[(ix, 1)], ids[(ix + 1, 1)]
        triangles += [2, a, b, c, 2, b, d, c]
    with h5py.File(path, "w") as handle:
        geometry = handle.create_group("collection/geometry_0")
        geometry.create_dataset("vertex", data=vertices)
        regions = {
            0: ("body", 0, triangles, b"Silicon"),
            1: ("left", 1, [1, 0, 2], None),
            2: ("drain", 1, [1, 6, 8], None),
        }
        for index, (name, kind, elements, material) in regions.items():
            group = geometry.create_group(f"region_{index}")
            group.attrs["name"] = np.bytes_(name)
            group.attrs["type"] = np.int32(kind)
            if material:
                group.attrs["material"] = np.bytes_(material)
            group.create_dataset("elements_0", data=np.array(elements, dtype=np.int32))
        state = geometry.create_group("state_0")
        potential = [2.0 * x + 3.0 * y for x, y in vertices]
        entries = [
            ("ElectrostaticPotential", 0, potential, "V"),
            ("ContactExternalVoltage", 1, [0.0], "V"),
            ("ContactExternalVoltage", 2, [drain_volts], "V"),
            ("ContactCurrentFlux", 1, [-drain_amps], "A"),
            ("ContactCurrentFlux", 2, [drain_amps], "A"),
            ("ContactCharge", 1, [0.0], "C"),
            ("ContactCharge", 2, [0.0], "C"),
        ]
        for number, (name, region, values, unit) in enumerate(entries):
            node = state.create_group(f"dataset_{number}")
            node.attrs["name"] = np.bytes_(name)
            node.attrs["region"] = np.int32(region)
            node.attrs["unit:name"] = np.bytes_(unit)
            node.create_dataset("values", data=np.asarray(values, dtype=float))


def _two_contact_spec() -> ExperimentSpec:
    def shape(data: dict) -> None:
        data["regions"] = [data["regions"][1]]
        data["regions"][0].update(x0="0 um", x1="1 um", y0="0 um", y1="2 um")
        data["profiles"] = [data["profiles"][0]]
        data["contacts"] = [
            {
                "id": "left",
                "region": "body",
                "location": "x_min",
                "span": ["0 um", "1 um"],
                "kind": "ohmic",
            },
            {
                "id": "drain",
                "region": "body",
                "location": "x_min",
                "span": ["1 um", "2 um"],
                "kind": "ohmic",
            },
        ]
        data["study"] = {
            "kind": "dc",
            "contact": "drain",
            "start": "0 V",
            "stop": "0.1 V",
            "step": "0.1 V",
        }
        data["profile_cuts"] = [{"id": "cut", "at": "0.5 um"}]
        data["observables"] = ["potential", "absolute_terminal_current"]
        data["width"] = "10 um"

    return spec_with(shape)


def test_export_interpolates_the_cut_and_scales_current_by_width(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TCAD_SENTAURUS_VERSION", VERSION)
    spec = _two_contact_spec()
    job = SentaurusAdapter.from_defaults("sde").compile(spec, tmp_path / "job")
    manifest = SentaurusJobManifest.model_validate_json(
        (job.entrypoint.parent / "job-manifest.json").read_bytes()
    )
    assert manifest.mesh_generation == "sde_2d"
    raw = tmp_path / "raw"
    raw.mkdir()
    _write_tdr(raw / "point_0000_des.tdr", 0.0, 0.0)
    _write_tdr(raw / "point_0001_des.tdr", 0.1, 2e-4)  # 2e-4 A per um of width
    (raw / "sdevice.stdout.log").write_text("*** Version O-2018.06-SP2 ***")
    path = build_export(raw, spec, manifest)
    result = SentaurusNormalizer().normalize(
        NativeRunResult(
            backend="sentaurus",
            status="completed",
            return_code=0,
            stdout_path=path,
            stderr_path=path,
            result_path=path,
            elapsed_seconds=1.0,
        )
    )
    potential = result.datasets["potential"]
    assert potential.shape == (2, 3)
    # Cut at depth 0.5 um: 2X + 1.5 at X = 0, 1, 2 um.
    assert potential.values[:3] == pytest.approx((1.5, 3.5, 5.5))
    # 2e-4 A/um over a 10 um device is 2e-3 A at the drain, positive into the device.
    assert result.datasets["absolute_terminal_current__drain"].values[1] == pytest.approx(2e-3)
    # Density is per contact area (1 um contact length x the 1 um native depth): width-free.
    assert result.bias_points[1].terminal_currents_a_per_m2["drain"] == pytest.approx(2e-4 / 1e-12)
    assert all(point.state == "converged" for point in result.operating_points)


def test_two_dimensional_ladder_starts_iterative_and_ends_on_the_direct_solver(
    tmp_path, monkeypatch
) -> None:
    from tcad_agent.adapters.sentaurus.native_export import escalation_notes

    monkeypatch.setenv("TCAD_SENTAURUS_VERSION", VERSION)
    root = SentaurusAdapter.from_defaults("sde").compile(spec_with(), tmp_path / "job").entrypoint.parent
    decks = [(root / name).read_text(encoding="utf-8") for name in (
        "sdevice.cmd", "sdevice.r1.cmd", "sdevice.r2.cmd", "sdevice.r3.cmd")]
    base, first, second, third = decks
    assert "SubMethod=ILS" in base and "-DoZero" not in base
    assert "-DoZero" in first and "Digits=8" in first
    assert "Digits=6" in second and "-DoZero" in second
    assert "SubMethod=ILS" not in third and "-DoZero" in third
    assert "direct" in escalation_notes("KRONIG numerics level 3 stalled: 0 1 2", two_dimensional=True)[0]
