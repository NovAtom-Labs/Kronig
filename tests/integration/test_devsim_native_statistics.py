"""Native statistical kernel must preserve values and physical Jacobians."""

import json
import math
import subprocess
from pathlib import Path

import pytest

from tcad_agent.adapters.devsim import statistics
from tcad_agent.adapters.registry import resolve_devsim_python

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_native_forward_inverse_and_chain_derivative_remain_consistent(tmp_path):
    etas = [-100, -20, -5, -1, 0, 2, 4.84, 7.06, 10, 35, 100]
    program = """
import json,sys,devsim as d
sys.path.insert(0,sys.argv[1])
import statistics as s
d.set_parameter(name='extended_model',value=True)
d.create_1d_mesh(mesh='m')
d.add_1d_mesh_line(mesh='m',pos=0,ps=1,tag='a')
d.add_1d_mesh_line(mesh='m',pos=1,ps=1,tag='b')
d.add_1d_region(mesh='m',region='r',material='Si',tag1='a',tag2='b')
d.add_1d_contact(mesh='m',name='a',material='metal',tag='a')
d.add_1d_contact(mesh='m',name='b',material='metal',tag='b')
d.finalize_mesh(mesh='m');d.create_device(mesh='m',device='d')
k={'device':'d','region':'r'}
d.node_solution(**k,name='Argument');d.set_node_values(**k,name='Argument',values=[0,0])
kernel=s.NativeStatistics(d,variables=('Argument',))
expr=kernel.node_expression('d','r','3*Fermi(2*Argument)')
d.node_model(**k,name='Forward',equation=expr)
d.node_model(**k,name='Slope',equation='diff('+expr+',Argument)')
d.node_model(**k,name='Inverse',equation=s.inverse_fermi_expression('Forward/3'))
out=[]
for eta in json.loads(sys.argv[2]):
 d.set_node_values(**k,name='Argument',values=[eta/2,eta/2])
 out.append([d.get_node_model_values(**k,name=n)[0] for n in ('Forward','Slope','Inverse')])
d.node_model(**k,name='Dependent',equation='Argument^2')
d.node_model(**k,name='Dependent:Argument',equation='2*Argument')
d.node_model(**k,name='InverseDependent',equation=s.inverse_fermi_expression('Dependent'))
kernel.create_derivative('node',k,'InverseDependent','InvFermi(Dependent)','Argument')
inverse_slopes=[]
for ratio in [0.1,1,8.46296036621705,9,100]:
 d.set_node_values(**k,name='Argument',values=[ratio**0.5]*2)
 inverse_slopes.append(d.get_node_model_values(**k,name='InverseDependent:Argument')[0])
print('INVERSE_SLOPES_JSON='+json.dumps(inverse_slopes))
print('STATISTICS_JSON='+json.dumps(out))
"""
    completed = subprocess.run(
        [
            str(resolve_devsim_python(ROOT)),
            "-c",
            program,
            str(Path(statistics.__file__).parent),
            json.dumps(etas),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    values = json.loads(completed.stdout.rsplit("STATISTICS_JSON=", 1)[1])
    slopes = json.loads(completed.stdout.split("INVERSE_SLOPES_JSON=", 1)[1].splitlines()[0])
    for ratio, slope in zip([0.1, 1, 8.46296036621705, 9, 100], slopes, strict=True):
        step = ratio * 1e-5
        numerical = (
            statistics.inverse_fermi(ratio + step) - statistics.inverse_fermi(ratio - step)
        ) / (2 * step)
        assert slope == pytest.approx(2 * math.sqrt(ratio) * numerical, rel=1e-7)
    for eta, (forward, slope, inverse) in zip(etas, values, strict=True):
        assert forward > 0 and slope > 0
        assert inverse == pytest.approx(eta, abs=3e-12)
        # Independent finite differences of the physical inverse relation.
        ratio = forward / 3
        step = ratio * 1e-5
        numerical = (
            statistics.inverse_fermi(ratio + step) - statistics.inverse_fermi(ratio - step)
        ) / (2 * step)
        assert slope == pytest.approx(6 / numerical, rel=1e-7)
        assert math.isfinite(slope)
