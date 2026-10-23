"""The conditioned solver must work without an automatically installed callback."""

import subprocess
from pathlib import Path

import pytest

from tcad_agent.adapters.devsim import density_solver
from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.domain.studies import EquilibriumStudy
from tcad_agent.domain.units import QuantityValue

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_density_controller_loads_native_callback_when_backend_has_no_default():
    # reset_devsim clears the callback on POSIX too, reproducing the default
    # Windows MKL state without pretending to run a Windows binary locally.
    program = """
import array,runpy,sys,devsim as d
d.reset_devsim()
assert 'solver_callback' not in d.get_parameter_list()
controller = runpy.run_path(sys.argv[1])['NativeDensitySolver'](
    d, 'unused', {'regions': []}, lambda **kw: {})
callback = controller.original_callback
state = callback(action='init', n=2, transpose=False)
assert state['status'] and state['matrix_format'] == 'csc'
factored = callback(action='factor', solver_object=state['solver_object'],
    Ap=array.array('i',[0,1,2]), Ai=array.array('i',[0,1]),
    Ax=array.array('d',[2.,3.]), is_complex=False, is_same_symbolic=False)
assert factored['status']
solved = callback(action='solve', solver_object=state['solver_object'],
    b=array.array('d',[2.,6.]), is_complex=False)
assert solved['status'] and list(solved['x']) == [1.,2.], solved
"""
    result = subprocess.run(
        [str(resolve_devsim_python(ROOT)), "-c", program, density_solver.__file__],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration
def test_conditioned_fermi_solve_explicitly_selects_its_callback(valid_spec, tmp_path):
    spec = ExperimentSpec.model_validate(
        valid_spec.model_copy(
            update={
                "regions": (
                    valid_spec.regions[0].model_copy(
                        update={"mesh_spacing": QuantityValue.model_validate("0.1 um")}
                    ),
                ),
                "profiles": valid_spec.profiles[:1],
                "physics": valid_spec.physics.model_copy(
                    update={"models": ("fermi", "constant_mobility", "srh")}
                ),
                "study": EquilibriumStudy(kind="equilibrium"),
            }
        ).model_dump(warnings=False)
    )
    job = DevsimAdapter.from_defaults().compile(spec, tmp_path / "native")
    program = """
import runpy,sys,devsim as d
sys.argv=['run_devsim.py','input.json']
ns=runpy.run_path('run_devsim.py')
load=ns['_density_solver_module']
selected=False
def select_noncallback_backend():
    global selected
    if not selected:
        # Before conditioning, native startup may have selected another solver.
        # An invalid selection makes accidental bypass deterministic on POSIX too.
        d.set_parameter(name='direct_solver',value='not_the_conditioned_solver')
        selected=True
    return load()
ns['main'].__globals__['_density_solver_module']=select_noncallback_backend
assert ns['main']()==0
assert d.get_parameter(name='direct_solver')=='custom'
"""
    result = subprocess.run(
        [str(resolve_devsim_python(ROOT)), "-c", program],
        cwd=job.entrypoint.parent,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
