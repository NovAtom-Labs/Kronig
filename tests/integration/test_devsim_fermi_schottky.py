"""Independent thermionic supply and physical metal/Fermi boundary references."""

import json
import math
import subprocess
from pathlib import Path

import pytest

from tcad_agent.adapters.devsim import runtime
from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import Contact, ExperimentSpec
from tcad_agent.domain.studies import DCPointsStudy, EquilibriumStudy
from tcad_agent.domain.units import QuantityValue
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget
from tcad_agent.validation.engine import ValidationEngine

ROOT = Path(__file__).parents[2]


def test_adaptive_initial_bias_is_bounded_by_thermal_scale_not_device_label():
    study = {"strategy": "adaptive", "minimum_step_v": 0.001}
    assert runtime._initial_dc_bias(0, 2, 300, study) == pytest.approx(0.10340799914574)
    assert runtime._initial_dc_bias(2, -2, 300, study) == pytest.approx(1.89659200085426)
    assert runtime._initial_dc_bias(0, 0.01, 300, study) == 0.01
    assert runtime._initial_dc_bias(0, 2, 300, {"strategy": "fixed"}) == 2


def _supply_reference(eta: float) -> float:
    """Independent direct quadrature of integral t/(1+exp(t-eta)) dt."""
    count = 32768
    stop = max(eta, 0) + 64
    step = stop / count

    def integrand(index):
        t = index * step
        delta = t - eta
        exponent = math.exp(-abs(delta))
        occupation = exponent / (1 + exponent) if delta >= 0 else 1 / (1 + exponent)
        return t * occupation

    return (
        step
        / 3
        * (
            integrand(0)
            + integrand(count)
            + 4 * math.fsum(integrand(i) for i in range(1, count, 2))
            + 2 * math.fsum(integrand(i) for i in range(2, count, 2))
        )
    )


@pytest.mark.integration
def test_native_fermi_supply_matches_independent_integral_and_smooth_derivative(tmp_path):
    models = runtime._fermi_one_models("test", "Eta")
    etas = [-500, -100, -50, -20, -4, -0.001, 0, 0.001, 4, 40, 100]
    program = """
import json,sys,devsim as d
models,etas=json.loads(sys.argv[1])
d.set_parameter(name='extended_model',value=True)
d.create_1d_mesh(mesh='m')
d.add_1d_mesh_line(mesh='m',pos=0,ps=1,tag='left')
d.add_1d_mesh_line(mesh='m',pos=1,ps=1,tag='right')
d.add_1d_region(mesh='m',region='r',material='Si',tag1='left',tag2='right')
d.add_1d_contact(mesh='m',name='left',material='metal',tag='left')
d.add_1d_contact(mesh='m',name='right',material='metal',tag='right')
d.finalize_mesh(mesh='m');d.create_device(mesh='m',device='device')
d.set_parameter(device='device',region='r',name='Eta',value=0)
for name,expr in models.items():
 d.edge_model(device='device',region='r',name=name,equation=expr)
out=[]
for eta in etas:
 d.set_parameter(device='device',region='r',name='Eta',value=eta)
 values=[d.get_edge_model_values(device='device',region='r',name=n)[0]
         for n in ('test_supply','test_derivative')]
 out.append(values)
print(json.dumps(out))
"""
    completed = subprocess.run(
        [str(resolve_devsim_python(ROOT)), "-c", program, json.dumps([models, etas])],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=45,
    )
    assert completed.returncode == 0, completed.stderr
    values = json.loads(completed.stdout.splitlines()[-1])
    for eta, (supply, derivative) in zip(etas, values, strict=True):
        assert supply > 0 and derivative > 0
        assert supply == pytest.approx(_supply_reference(eta), rel=2e-11, abs=0)
        assert derivative == pytest.approx(
            max(eta, 0) + math.log1p(math.exp(-abs(eta))), rel=2e-13, abs=0
        )
    assert values[etas.index(0)][0] == pytest.approx(math.pi**2 / 12, rel=1e-14)


def _metal_fermi(spec: ExperimentSpec, *, both=False, bgn=False) -> ExperimentSpec:
    contacts = tuple(
        Contact.model_validate(
            {
                "id": contact.id,
                "location": contact.location,
                "kind": "metal_work_function",
                "work_function": "4.10 eV",
            }
        )
        if both or index == 0
        else contact
        for index, contact in enumerate(spec.contacts)
    )
    models = tuple("fermi" if str(m) == "boltzmann" else m for m in spec.physics.models)
    if bgn:
        models = (*models, "auger", "slotboom_bgn")
    return spec.model_copy(
        update={
            "contacts": contacts,
            "physics": spec.physics.model_copy(update={"models": models}),
            "study": EquilibriumStudy(kind="equilibrium"),
            "observables": (
                *spec.observables,
                "conduction_band",
                "valence_band",
                "electron_quasi_fermi_level",
                "hole_quasi_fermi_level",
            ),
        }
    )


def _run(spec, workspace):
    spec = ExperimentSpec.model_validate(spec.model_dump(warnings=False))
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, workspace), RunBudget(seconds=180)
    )
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    return result


@pytest.mark.integration
@pytest.mark.parametrize("both,bgn", [(False, False), (True, True)])
def test_fermi_metal_equilibrium_satisfies_detailed_balance(valid_spec, tmp_path, both, bgn):
    result = _run(_metal_fermi(valid_spec, both=both, bgn=bgn), tmp_path / "native")
    currents = result.bias_points[0].terminal_currents_a_per_m2.values()
    assert max(abs(value) for value in currents) < 1e-3
    for field in ("electron_quasi_fermi_level", "hole_quasi_fermi_level"):
        assert max(abs(value) for value in result.datasets[field].values) < 1e-7
    assert "fermi" in result.metadata["parameter_sources"]["schottky_transport"]["version"]


@pytest.mark.integration
@pytest.mark.parametrize("temperature", [280, 340])
def test_fermi_metal_barrier_and_zero_current_hold_at_other_temperatures(
    valid_spec, tmp_path, temperature
):
    spec = _metal_fermi(valid_spec, both=True, bgn=True)
    spec = spec.model_copy(
        update={
            "physics": spec.physics.model_copy(
                update={"temperature": QuantityValue.model_validate(f"{temperature} K")}
            )
        }
    )
    result = _run(spec, tmp_path / "native")
    # Explicit affinity4.05eV plus work function4.10eV defines this barrier.
    conduction = result.datasets["conduction_band"].values
    assert conduction[0] == pytest.approx(0.05, abs=1e-8)
    assert conduction[-1] == pytest.approx(0.05, abs=1e-8)
    assert max(abs(v) for v in result.bias_points[0].terminal_currents_a_per_m2.values()) < 1e-3
    for field in ("electron_quasi_fermi_level", "hole_quasi_fermi_level"):
        assert max(abs(v) for v in result.datasets[field].values) < 1e-7


@pytest.mark.integration
def test_original_aluminum_structure_with_fermi_executes_both_bias_polarities(valid_spec, tmp_path):
    spec = _metal_fermi(valid_spec, both=True, bgn=True)
    spec = spec.model_copy(
        update={
            "regions": tuple(
                region.model_copy(
                    update={
                        "x0": QuantityValue.model_validate(f"{index} um"),
                        "x1": QuantityValue.model_validate(f"{index + 1} um"),
                    }
                )
                for index, region in enumerate(spec.regions)
            ),
            "profiles": tuple(
                profile.model_copy(update={"value": QuantityValue.model_validate("1e17 cm^-3")})
                for profile in spec.profiles
            ),
            "study": DCPointsStudy.model_validate(
                {
                    "kind": "dc_points",
                    "contact": "anode",
                    "values": ["0 V", "2 V", "-2 V"],
                    "strategy": "adaptive",
                    "minimum_step": "0.001 V",
                    "maximum_retries": 24,
                }
            ),
            "observables": (
                "terminal_current_density",
                "potential",
                "electric_field",
                "electron_density",
                "hole_density",
                "charge_density",
                "conduction_band",
                "valence_band",
                "electron_quasi_fermi_level",
                "hole_quasi_fermi_level",
                "electron_current_density",
                "hole_current_density",
                "electron_mobility",
                "hole_mobility",
                "srh_recombination_rate",
                "auger_recombination_rate",
                "total_recombination_rate",
                "band_gap_narrowing",
            ),
        }
    )
    spec = ExperimentSpec.model_validate(spec.model_dump(warnings=False))
    result = _run(spec, tmp_path / "native")
    assert [point.bias_v for point in result.bias_points] == [0, 2, -2]
    assert all(point.converged for point in result.bias_points)
    bands = result.datasets["conduction_band"]
    assert bands.axes[0] == "bias" and bands.shape[0] == 3
    count = bands.shape[1]
    for index, bias in enumerate((0, 2, -2)):
        # Ec-EFmetal is the actual aluminum barrier at each biased end.
        assert bands.values[index * count] + bias == pytest.approx(0.05, abs=1e-8)
        assert bands.values[(index + 1) * count - 1] == pytest.approx(0.05, abs=1e-8)
    for name, unit in (
        ("electron_density", "m^-3"),
        ("hole_density", "m^-3"),
        ("electric_field", "V/m"),
        ("electron_current_density", "A/m^2"),
        ("hole_current_density", "A/m^2"),
        ("electron_mobility", "m^2/V/s"),
        ("hole_mobility", "m^2/V/s"),
        ("total_recombination_rate", "m^-3/s"),
    ):
        assert result.datasets[name].unit == unit
    currents = [point.terminal_currents_a_per_m2["anode"] for point in result.bias_points]
    assert currents[1] * currents[2] < 0
    assert max(abs(v) for v in result.bias_points[0].terminal_currents_a_per_m2.values()) < 1e-3
    for point in result.bias_points:
        values = tuple(point.terminal_currents_a_per_m2.values())
        assert abs(sum(values)) <= 1e-6 + 0.005 * max(abs(v) for v in values)
    validation = ValidationEngine().validate(result, spec=spec)
    assert validation.overall == "passed", validation.model_dump_json(indent=2)


@pytest.mark.integration
def test_degenerate_metal_contact_is_not_boltzmann_substitution(valid_spec, tmp_path):
    spec = _metal_fermi(valid_spec)
    spec = spec.model_copy(
        update={
            "contacts": (
                spec.contacts[0].model_copy(
                    update={"work_function": QuantityValue.model_validate("3.95 eV")}
                ),
                spec.contacts[1],
            )
        }
    )
    result = _run(spec, tmp_path / "native")
    # eta=(chi-Phi)/Vt=0.1/0.025852; MB predicts ~1.5e21cm^-3.
    # Native Fermi population is far below that and has n/Nc>1.
    density = result.datasets["electron_density"].values[0] * 1e-6
    classical = 2.8e19 * math.exp(0.1 / (8.617333262145e-5 * 300))
    assert density > 2.8e19
    assert density < 0.4 * classical
    assert max(abs(v) for v in result.datasets["electron_quasi_fermi_level"].values) < 1e-7


@pytest.mark.integration
def test_thermionic_richardson_constant_changes_actual_contact_resistance(valid_spec, tmp_path):
    spec = _metal_fermi(valid_spec)
    first = spec.regions[0].model_copy(update={"x1": QuantityValue.model_validate("1 um")})
    profile = spec.profiles[0].model_copy(
        update={"species": "donor", "value": QuantityValue.model_validate("1e16 cm^-3")}
    )
    spec = spec.model_copy(
        update={
            "regions": (first,),
            "profiles": (profile,),
            "study": DCPointsStudy.model_validate(
                {"kind": "dc_points", "contact": "anode", "values": ["0 V", "0.05 V"]}
            ),
        }
    )
    high = _run(spec, tmp_path / "high")
    low_spec = spec.model_copy(
        update={
            "contacts": (
                spec.contacts[0].model_copy(
                    update={
                        "electron_richardson_constant": QuantityValue.model_validate(
                            "0.0001 A/cm^2/K^2"
                        )
                    }
                ),
                spec.contacts[1],
            )
        }
    )
    low = _run(low_spec, tmp_path / "low")
    high_current = abs(high.bias_points[-1].terminal_currents_a_per_m2["anode"])
    low_current = abs(low.bias_points[-1].terminal_currents_a_per_m2["anode"])
    assert (
        high.bias_points[-1].terminal_currents_a_per_m2["anode"]
        * low.bias_points[-1].terminal_currents_a_per_m2["anode"]
    ) > 0
    assert high_current > 1e-6
    assert low_current < 0.1 * high_current


@pytest.mark.integration
def test_right_hole_metal_contact_is_passive_and_conserves_current(valid_spec, tmp_path):
    base = _metal_fermi(valid_spec)
    contact = base.contacts[0].model_copy(
        update={"location": "x_max", "work_function": QuantityValue.model_validate("5.12 eV")}
    )
    spec = base.model_copy(
        update={
            "regions": (
                base.regions[0].model_copy(update={"x1": QuantityValue.model_validate("1 um")}),
            ),
            "profiles": (
                base.profiles[0].model_copy(
                    update={"value": QuantityValue.model_validate("1e16 cm^-3")}
                ),
            ),
            "contacts": (contact, base.contacts[1].model_copy(update={"location": "x_min"})),
            "study": DCPointsStudy.model_validate(
                {"kind": "dc_points", "contact": "anode", "values": ["0 V", "0.05 V"]}
            ),
        }
    )
    high = _run(spec, tmp_path / "high")
    low = _run(
        spec.model_copy(
            update={
                "contacts": (
                    contact.model_copy(
                        update={
                            "hole_richardson_constant": QuantityValue.model_validate(
                                "0.0001 A/cm^2/K^2"
                            )
                        }
                    ),
                    spec.contacts[1],
                )
            }
        ),
        tmp_path / "low",
    )
    high_current = high.bias_points[-1].terminal_currents_a_per_m2["anode"]
    low_current = low.bias_points[-1].terminal_currents_a_per_m2["anode"]
    assert high_current * low_current > 0
    assert abs(low_current) < 0.1 * abs(high_current)
    for result in (high, low):
        values = tuple(result.bias_points[-1].terminal_currents_a_per_m2.values())
        assert abs(sum(values)) <= 1e-6 + 0.005 * max(abs(v) for v in values)


@pytest.mark.integration
def test_dilute_metal_fermi_equilibrium_matches_boltzmann_reference(valid_spec, tmp_path):
    base = _metal_fermi(valid_spec, both=True)
    spec = base.model_copy(
        update={
            "contacts": tuple(
                c.model_copy(update={"work_function": QuantityValue.model_validate("4.61 eV")})
                for c in base.contacts
            )
        }
    )
    fermi = _run(spec, tmp_path / "fermi")
    classical = _run(
        spec.model_copy(
            update={
                "physics": spec.physics.model_copy(
                    update={
                        "models": tuple(
                            "boltzmann" if str(m) == "fermi" else m for m in spec.physics.models
                        )
                    }
                )
            }
        ),
        tmp_path / "classical",
    )
    for field in ("electron_density", "hole_density"):
        for actual, expected in zip(
            fermi.datasets[field].values, classical.datasets[field].values, strict=True
        ):
            assert actual == pytest.approx(expected, rel=0.03)
    assert fermi.datasets["potential"].values == pytest.approx(
        classical.datasets["potential"].values, abs=0.001
    )


@pytest.mark.integration
def test_native_contact_jacobians_match_finite_differences_at_both_endpoints(valid_spec, tmp_path):
    spec = ExperimentSpec.model_validate(
        _metal_fermi(valid_spec, both=True, bgn=True).model_dump(warnings=False)
    )
    job = DevsimAdapter.from_defaults().compile(spec, tmp_path / "native")
    program = """
import json,sys,runpy,devsim as d
sys.argv=['run_devsim.py','input.json']
ns=runpy.run_path('run_devsim.py');assert ns['main']()==0
device='novatom_device'
payload=json.load(open('input.json'))
out=[]
for region in d.get_region_list(device=device):
 models=d.get_edge_model_list(device=device,region=region)
 for flux in [n for n in models if n.endswith('_thermionic')]:
  variables=('Potential','Electrons','Holes')
  values={v:list(d.get_node_model_values(device=device,region=region,name=v)) for v in variables}
  # The thermionic contact is on the outer endpoint of the associated region.
  index=0 if region==payload['regions'][0]['id'] else -1
  edge=0 if index==0 else -1
  endpoint='n0' if index==0 else 'n1'
  for variable, original in values.items():
   expected=d.get_edge_model_values(device=device,region=region,name=f'{flux}:{variable}@{endpoint}')[edge]
   h=1e-6 if variable=='Potential' else max(abs(original[index])*1e-4,1e-30)
   evaluated=[]
   for sign in (1,-1):
    changed=original.copy();changed[index]+=sign*h
    d.set_node_values(device=device,region=region,name=variable,values=changed)
    evaluated.append(d.get_edge_model_values(device=device,region=region,name=flux)[edge])
   d.set_node_values(device=device,region=region,name=variable,values=original)
   measured=(evaluated[0]-evaluated[1])/(2*h)
   out.append([flux,variable,measured,expected])
print('JACOBIAN_JSON='+json.dumps(out))
"""
    completed = subprocess.run(
        [str(resolve_devsim_python(ROOT)), "-c", program],
        cwd=job.entrypoint.parent,
        text=True,
        capture_output=True,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stderr[-6000:]
    rows = json.loads(completed.stdout.split("JACOBIAN_JSON=")[-1])
    assert len(rows) == 12
    for flux, variable, measured, expected in rows:
        assert measured == pytest.approx(expected, rel=2e-5, abs=1e-15), (
            flux,
            variable,
            measured,
            expected,
        )


@pytest.mark.integration
def test_biased_fermi_schottky_current_converges_under_mesh_refinement(valid_spec, tmp_path):
    base = _metal_fermi(valid_spec)
    region = base.regions[0].model_copy(update={"x1": QuantityValue.model_validate("1 um")})
    profile = base.profiles[0].model_copy(
        update={"species": "donor", "value": QuantityValue.model_validate("1e16 cm^-3")}
    )
    study = DCPointsStudy.model_validate(
        {"kind": "dc_points", "contact": "anode", "values": ["0 V", "0.05 V"]}
    )
    currents = []
    for spacing in ("5 nm", "2.5 nm"):
        spec = base.model_copy(
            update={
                "regions": (
                    region.model_copy(
                        update={"mesh_spacing": QuantityValue.model_validate(spacing)}
                    ),
                ),
                "profiles": (profile,),
                "study": study,
            }
        )
        result = _run(spec, tmp_path / spacing.replace(" ", "-"))
        currents.append(result.bias_points[-1].terminal_currents_a_per_m2["anode"])
        assert all(point.converged for point in result.bias_points)
        values = tuple(result.bias_points[-1].terminal_currents_a_per_m2.values())
        assert abs(sum(values)) < 1e-6 + 0.005 * max(abs(value) for value in values)
    assert currents[0] == pytest.approx(currents[1], rel=0.02)
