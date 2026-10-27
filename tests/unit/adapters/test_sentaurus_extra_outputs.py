"""Native outputs beyond the basics (doping, band gap, recombination split, ...) reach the result.

The TDR is a synthetic file with the documented structure and the native dataset names seen
from Sentaurus Device, not licensed output.
"""

import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_sentaurus_generated_mesh import (
    VERSION,
    _write_tdr,
    pn_spec,
)

from tcad_agent.adapters.sentaurus.compiler import (
    SentaurusAdapter,
)
from tcad_agent.adapters.sentaurus.native_export import build_export
from tcad_agent.adapters.sentaurus.normalizer import SentaurusNormalizer
from tcad_agent.adapters.sentaurus.runtime import SentaurusJobManifest
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.models import NativeRunResult

EXTRA = [
    "net_doping",
    "band_gap",
    "effective_intrinsic_carrier_concentration",
    "lattice_temperature",
    "srh_recombination_rate",
    "total_current_density",
]


def extended_spec(observables=EXTRA, models=None):
    data = pn_spec().model_dump(mode="json")
    data["observables"] = [*data["observables"], *observables]
    if models is not None:
        data["physics"]["models"] = list(models)
    return ExperimentSpec.model_validate(data)


def _add_native_fields(path: Path) -> None:
    """Append the native fields of both regions the way Sentaurus writes them."""
    per_region = {
        0: {"p": True},
        1: {"p": False},
    }
    with h5py.File(path, "a") as handle:
        state = handle["collection/geometry_0/state_0"]
        number = len([key for key in state if key.startswith("dataset_")])
        for region, flags in per_region.items():
            acceptor = 1e17 if flags["p"] else 0.0
            donor = 0.0 if flags["p"] else 1e16
            entries = [
                ("DopingConcentration", [donor - acceptor] * 4, "cm^-3"),
                ("DonorConcentration", [donor] * 4, "cm^-3"),
                ("AcceptorConcentration", [acceptor] * 4, "cm^-3"),
                ("BandGap", [1.12] * 4, "eV"),
                ("EffectiveIntrinsicDensity", [1.08e10] * 4, "cm^-3"),
                ("LatticeTemperature", [300.0] * 4, "K"),
                ("srhRecombination", [2e3] * 4, "cm^-3*s^-1"),
                ("TotalCurrentDensity", [1e-6, 0.0] * 4, "A*cm^-2"),
            ]
            for name, values, unit in entries:
                node = state.create_group(f"dataset_{number}")
                node.attrs["name"] = np.bytes_(name)
                node.attrs["region"] = np.int32(region)
                node.attrs["unit:name"] = np.bytes_(unit)
                node.create_dataset("values", data=np.asarray(values, dtype=float))
                number += 1


def test_the_requested_native_fields_are_plotted_and_the_model_prerequisite_is_checked(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_SENTAURUS_VERSION", VERSION)
    job = SentaurusAdapter.from_defaults("sde").compile(extended_spec(), tmp_path / "job")
    deck = (job.entrypoint.parent / "sdevice.cmd").read_text(encoding="utf-8")
    donors = SentaurusAdapter.from_defaults("sde").compile(
        extended_spec(["donor_concentration", "acceptor_concentration"]), tmp_path / "doping"
    )
    donor_deck = (donors.entrypoint.parent / "sdevice.cmd").read_text(encoding="utf-8")
    # Donor and acceptor fields are not written by the net-doping keyword; each is plotted itself.
    assert "\n  DonorConcentration\n" in donor_deck
    assert "\n  AcceptorConcentration\n" in donor_deck
    for native in (
        "Doping",
        "BandGap",
        "EffectiveIntrinsicDensity",
        "LatticeTemperature",
        "SRHRecombination",
        "TotalCurrent/Vector",
    ):
        assert f"\n  {native}\n" in deck, native

    # Caught before any plan exists: the missing model is a question, not a late failure.
    from tcad_agent.capabilities.models import CapabilityManifest
    from tcad_agent.capabilities.service import CapabilityService

    decision = CapabilityService().check(
        extended_spec(["srh_recombination_rate"], models=["boltzmann", "constant_mobility"]),
        CapabilityManifest.from_backend("sentaurus"),
    )
    assert [issue.code for issue in decision.issues] == ["observable_needs_model"]
    assert decision.issues[0].supported[0] == "add the srh model"
    with pytest.raises(Exception, match="srh"):
        SentaurusAdapter.from_defaults("sde").compile(
            extended_spec(["srh_recombination_rate"], models=["boltzmann", "constant_mobility"]),
            tmp_path / "no-srh",
        )


def test_native_fields_are_exported_in_si_units_and_only_the_requested_doping_is_kept(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_SENTAURUS_VERSION", VERSION)
    spec = extended_spec()
    job = SentaurusAdapter.from_defaults("sde").compile(spec, tmp_path / "job")
    manifest = SentaurusJobManifest.model_validate_json(
        (job.entrypoint.parent / "job-manifest.json").read_bytes()
    )
    raw = tmp_path / "raw"
    raw.mkdir()
    for index in range(2):
        target = raw / f"point_{index:04d}_des.tdr"
        _write_tdr(target, 0.1 * index)
        _add_native_fields(target)
    (raw / "sdevice.stdout.log").write_text(f"***   Version {VERSION}   ***\n")

    path = build_export(raw, spec, manifest)
    result = SentaurusNormalizer().normalize(
        NativeRunResult(
            backend="sentaurus",
            status="completed",
            return_code=0,
            stdout_path=raw / "sdevice.stdout.log",
            stderr_path=raw / "sdevice.stdout.log",
            result_path=path,
            elapsed_seconds=1.0,
        )
    )

    assert result.datasets["net_doping"].unit == "m^-3"
    assert result.datasets["net_doping"].values[0] == pytest.approx(-1e23)  # p side, 1e17 /cm3
    assert result.datasets["net_doping"].values[-1] == pytest.approx(1e22)
    assert result.datasets["band_gap"].unit == "eV"
    assert result.datasets["effective_intrinsic_carrier_concentration"].values[0] == (
        pytest.approx(1.08e16)
    )
    assert result.datasets["srh_recombination_rate"].unit == "m^-3*s^-1"
    assert result.datasets["srh_recombination_rate"].values[0] == pytest.approx(2e9)
    assert result.datasets["lattice_temperature"].unit == "K"
    assert result.datasets["total_current_density"].values[0] == pytest.approx(1e-2)
    # The native Doping plot also wrote donors and acceptors; nobody asked for them.
    assert "donor_concentration" not in result.datasets
    assert "acceptor_concentration" not in result.datasets
