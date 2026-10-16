"""Opt-in relative performance gate, with unchanged native mathematical values."""

import json
import os
import subprocess

import pytest

from tcad_agent.adapters.devsim import statistics
from tcad_agent.adapters.registry import resolve_devsim_python


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("KRONIG_RUN_PERFORMANCE_TESTS") != "1",
    reason="relative timing benchmark is opt-in, not a hardware-independent acceptance limit",
)
def test_uniform_statistics_skip_inactive_native_branch(tmp_path):
    program = r"""
import json,statistics as std,time,sys,devsim as d
sys.path.insert(0,sys.argv[1])
import devsim_statistics as s
d.set_parameter(name='extended_model',value=True)
d.create_1d_mesh(mesh='m')
d.add_1d_mesh_line(mesh='m',pos=0,ps=.001,tag='a')
d.add_1d_mesh_line(mesh='m',pos=1,ps=.001,tag='b')
d.add_1d_region(mesh='m',region='r',material='Si',tag1='a',tag2='b')
d.add_1d_contact(mesh='m',name='a',material='metal',tag='a')
d.add_1d_contact(mesh='m',name='b',material='metal',tag='b')
d.finalize_mesh(mesh='m');d.create_device(mesh='m',device='d')
k=dict(device='d',region='r');d.node_solution(**k,name='Ratio')
size=len(d.get_node_model_values(**k,name='Ratio'))
low='min(Ratio,8.46296036621705)';high='max(Ratio,8.46296036621705)'
small=f'(log({low})+0.35355339059327373*({low})-0.0049500897298752622*({low})^2+0.00014838577128872821*({low})^3-0.0000044256301190009895*({low})^4)'
large=f'(pow(pow(1.329340388179137*({high}),4/3)-1.6449340668482264,0.5)+(-0.0137050034663995))'
legacy=f'ifelse(Ratio<8.46296036621705,{small},{large})'
d.node_model(**k,name='Legacy',equation=legacy)
d.node_model(**k,name='Candidate',equation=s.inverse_fermi_expression('Ratio'))
errors=[]
for lo,hi in ((1e-5,.2),(10,30),(.1,30)):
 values=[lo+(hi-lo)*i/(size-1) for i in range(size)]
 d.set_node_values(**k,name='Ratio',values=values)
 a=d.get_node_model_values(**k,name='Legacy');b=d.get_node_model_values(**k,name='Candidate')
 errors.append(max(abs(x-y) for x,y in zip(a,b,strict=True)))
values=[1e-5+.2*i/(size-1) for i in range(size)]
times={'Legacy':[],'Candidate':[]}
for repeat in range(3):
 for name in (('Legacy','Candidate') if repeat%2 else ('Candidate','Legacy')):
  start=time.monotonic()
  for step in range(30):
   d.set_node_values(**k,name='Ratio',values=values)
   d.get_node_model_values(**k,name=name)
  times[name].append(time.monotonic()-start)
print('BENCHMARK_JSON='+json.dumps(dict(errors=errors,times=times)))
"""
    # The reviewed helper is copied under its standalone runtime import name.
    import shutil
    import statistics as std

    shutil.copyfile(statistics.__file__, tmp_path / "devsim_statistics.py")
    completed = subprocess.run(
        [str(resolve_devsim_python()), "-c", program, str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    data = json.loads(completed.stdout.rsplit("BENCHMARK_JSON=", 1)[1])
    assert max(data["errors"]) < 1e-12
    legacy = std.median(data["times"]["Legacy"])
    candidate = std.median(data["times"]["Candidate"])
    assert candidate < 0.85 * legacy, data
