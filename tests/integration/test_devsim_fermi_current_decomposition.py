"""Independent manufactured fields for the native Fermi edge diagnostics."""

import json
import math
import subprocess
from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.domain.studies import EquilibriumStudy
from tcad_agent.domain.units import QuantityValue

ROOT = Path(__file__).parents[2]


def _half_fermi_integral(eta: float) -> float:
    """Normalized F_1/2 by direct Simpson quadrature, t=s^2 removes sqrt(t)."""
    count = 8192
    step = math.sqrt(max(eta, 0) + 64) / count

    def integrand(index: int) -> float:
        s = index * step
        delta = s * s - eta
        exponent = math.exp(-abs(delta))
        occupation = exponent / (1 + exponent) if delta >= 0 else 1 / (1 + exponent)
        return s * s * occupation

    return (
        4
        / math.sqrt(math.pi)
        * step
        / 3
        * (
            integrand(0)
            + integrand(count)
            + 4 * math.fsum(integrand(i) for i in range(1, count, 2))
            + 2 * math.fsum(integrand(i) for i in range(2, count, 2))
        )
    )


@pytest.mark.integration
def test_fermi_components_match_isolated_physical_gradients(valid_spec, tmp_path):
    """Catches classical Einstein substitution, reversed hole signs, and missing BGN."""
    spec = valid_spec.model_copy(
        update={
            "regions": (
                valid_spec.regions[0].model_copy(
                    update={
                        "x1": QuantityValue.model_validate("1 um"),
                        "mesh_spacing": QuantityValue.model_validate("0.5 um"),
                    }
                ),
            ),
            "profiles": (
                valid_spec.profiles[0].model_copy(
                    update={
                        "species": "donor",
                        "value": QuantityValue.model_validate("1e16 cm^-3"),
                    }
                ),
            ),
            "physics": valid_spec.physics.model_copy(
                update={"models": ("fermi", "constant_mobility", "srh", "slotboom_bgn")}
            ),
            "study": EquilibriumStudy(kind="equilibrium"),
            "observables": (
                "electron_drift_current_density",
                "electron_diffusion_current_density",
                "hole_drift_current_density",
                "hole_diffusion_current_density",
                "current_decomposition_residual",
            ),
        }
    )
    job = DevsimAdapter.from_defaults().compile(
        ExperimentSpec.model_validate(spec.model_dump(warnings=False)), tmp_path / "native"
    )
    # Densities are supplied from an independent integral, not native Fermi/InvFermi.
    samples = {
        "dilute": [_half_fermi_integral(eta) for eta in (-12, -10, -8)],
        "degenerate": [_half_fermi_integral(eta) for eta in (8, 9, 10)],
        # Independently evaluated matched Sommerfeld approximation at the
        # quadrature populations, using 3*sqrt(pi)/4 and the JD joining offset.
        "pinned_degenerate_eta": [7.988315763372532, 8.987666716674745, 9.987268064884553],
    }
    program = """
import json,sys,runpy,devsim as d
samples=json.loads(sys.argv[1]);sys.argv=['run_devsim.py','input.json']
ns=runpy.run_path('run_devsim.py');assert ns['main']()==0
device='novatom_device';region=d.get_region_list(device=device)[0]
kw={'device':device,'region':region}
x=list(d.get_node_model_values(**kw,name='x'));assert len(x)==3
q=d.get_parameter(**kw,name='ElectronCharge');vt=d.get_parameter(**kw,name='V_t')
nc=d.get_parameter(**kw,name='EffectiveDensityConduction')
nv=d.get_parameter(**kw,name='EffectiveDensityValence')
mu_n=d.get_parameter(**kw,name='mu_n');mu_p=d.get_parameter(**kw,name='mu_p')
# Replace the fixed-doping BGN expression once with an independently set input
# solution. set_node_values signals dependency changes, unlike model replacement
# followed by reading already-cached edge diagnostics.
d.node_solution(**kw,name='BandGapNarrowing')
rows={}
for case in ('field','dilute','degenerate','local_gradient','band_gradient',
             'equilibrium_n','equilibrium_p','residual_probe'):
 ratios=samples['dilute'] if case=='dilute' else samples['degenerate']
 if case=='local_gradient':ratios=[2-1e-5,2,2+1e-5]
 varying=case in ('dilute','degenerate','local_gradient','equilibrium_n','equilibrium_p')
 n=[nc*r for r in ratios] if varying else [nc*ratios[0]]*3
 p=[nv*r for r in ratios] if varying else [nv*ratios[0]]*3
 potential=[0.0]*3
 if case=='field':potential=[-100.0*position for position in x]
 if case=='equilibrium_n':potential=[vt*eta for eta in samples['pinned_degenerate_eta']]
 if case=='equilibrium_p':potential=[-vt*eta for eta in samples['pinned_degenerate_eta']]
 for name,values in (('Potential',potential),('Electrons',n),('Holes',p)):
  d.set_node_values(**kw,name=name,values=values)
 d.set_node_values(**kw,name='BandGapNarrowing',
                   values=[200*position for position in x] if case=='band_gradient' else [0.0]*3)
 if case=='residual_probe':
  d.edge_model(**kw,name='ElectronCurrent',equation='123')
  d.edge_model(**kw,name='HoleCurrent',equation='-17')
 names=('ElectronCurrent','HoleCurrent','ElectronDriftCurrent','ElectronDiffusionCurrent',
        'HoleDriftCurrent','HoleDiffusionCurrent','ElectronDensityDiffusionCurrent',
        'HoleDensityDiffusionCurrent','ElectronBandGradientCurrent','HoleBandGradientCurrent',
        'CurrentDecompositionResidual')
 rows[case]={name:list(d.get_edge_model_values(**kw,name=name)) for name in names}
 rows[case]['bgn_nodes']=list(d.get_node_model_values(**kw,name='BandGapNarrowing'))
 rows[case]['bgn_n0']=list(d.get_edge_model_values(**kw,name='BandGapNarrowing@n0'))
 rows[case]['bgn_n1']=list(d.get_edge_model_values(**kw,name='BandGapNarrowing@n1'))
 rows[case]['n']=n;rows[case]['p']=p
print('COMPONENTS_JSON='+json.dumps({'x':x,'q':q,'vt':vt,'mu_n':mu_n,'mu_p':mu_p,'cases':rows}))
"""
    completed = subprocess.run(
        [str(resolve_devsim_python(ROOT)), "-c", program, json.dumps(samples)],
        cwd=job.entrypoint.parent,
        text=True,
        capture_output=True,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stderr[-6000:] + completed.stdout[-2000:]
    data = json.loads(completed.stdout.split("COMPONENTS_JSON=")[-1])
    q, vt = data["q"], data["vt"]
    for case, row in data["cases"].items():
        if case == "residual_probe":
            # A deliberately unreconciled native current must survive reporting.
            assert row["CurrentDecompositionResidual"] == pytest.approx([106, 106])
            continue
        for index in (0, 1):
            dx = data["x"][index + 1] - data["x"][index]
            for carrier, density_key, sign, mobility in (
                ("Electron", "n", 1, data["mu_n"]),
                ("Hole", "p", -1, data["mu_p"]),
            ):
                density = 0.5 * (row[density_key][index] + row[density_key][index + 1])
                prefactor = q * mobility * density
                if case == "field":
                    assert row[f"{carrier}DriftCurrent"][index] == pytest.approx(
                        prefactor * 100, rel=1e-12
                    )
                    assert row[f"{carrier}DiffusionCurrent"][index] == pytest.approx(0, abs=1e-20)
                elif case in {"dilute", "degenerate", "local_gradient"}:
                    # These references do not invoke the native primitive or production
                    # helper: dilute uses quadrature; degenerate uses hand-checked values
                    # of the matched expansion; local uses its analytic derivative.
                    delta_eta = {
                        "dilute": (2.0, 2.0),
                        "degenerate": (0.9993509533022129, 0.9996013482098078),
                        "local_gradient": (0.8353920407654294e-5, 0.8353920407654294e-5),
                    }[case][index]
                    actual = row[f"{carrier}DensityDiffusionCurrent"][index]
                    assert actual == pytest.approx(
                        sign * prefactor * vt * delta_eta / dx,
                        rel=0.005
                        if case == "dilute"
                        else (1e-12 if case == "degenerate" else 1e-5),
                    )
                    assert row[f"{carrier}DriftCurrent"][index] == pytest.approx(0, abs=1e-20)
                    if case == "degenerate":
                        classical = (
                            sign
                            * q
                            * mobility
                            * vt
                            * (row[density_key][index + 1] - row[density_key][index])
                            / dx
                        )
                        assert abs(actual) > 4 * abs(classical)
                        exact_integral_reference = sign * prefactor * vt / dx
                        # The formerly inherited ~45% error is not accepted.
                        assert actual / exact_integral_reference == pytest.approx(1, rel=0.003)
                elif case == "band_gradient":
                    expected = -sign * prefactor * 0.5 * 200
                    assert row[f"{carrier}BandGradientCurrent"][index] == pytest.approx(
                        expected, rel=1e-12
                    ), (row["bgn_nodes"], row["bgn_n0"], row["bgn_n1"])
                    assert row[f"{carrier}DensityDiffusionCurrent"][index] == pytest.approx(
                        0, abs=1e-20
                    )
                    assert row[f"{carrier}DiffusionCurrent"][index] == pytest.approx(
                        expected, rel=1e-12
                    )
                elif case == f"equilibrium_{density_key}":
                    scale = abs(row[f"{carrier}DriftCurrent"][index])
                    assert abs(row[f"{carrier}Current"][index]) < 1e-12 * scale
            scale = max(abs(values[index]) for name, values in row.items() if "Current" in name)
            assert abs(row["CurrentDecompositionResidual"][index]) < scale * 1e-12
