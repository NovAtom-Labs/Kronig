"""Independent finite-volume algebra across asymmetric sources and interfaces.

This is a manufactured operator test, not a claimed calibrated device model.
The source and boundary laws are chosen to expose signs and cross derivatives.
"""

import json
import subprocess
from pathlib import Path

import pytest

from tcad_agent.adapters.devsim import density_solver
from tcad_agent.adapters.registry import resolve_devsim_python

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_native_integrated_balance_matches_three_region_physical_rows_and_jacobian(tmp_path):
    program = """
import sys,json,math,devsim as d
sys.path.insert(0,sys.argv[1])
import density_solver as s
from devsim.python_packages.model_create import (
 CreateNodeModelDerivative,CreateEdgeModelDerivatives,CreateContinuousInterfaceModel,
)
d.set_parameter(name='extended_model',value=True)
d.set_parameter(name='extended_equation',value=True)
d.set_parameter(name='extended_solver',value=True)
d.create_1d_mesh(mesh='m')
positions=[0,.7e-4,1.6e-4,2.1e-4];names=['alpha','beta','gamma']
regions=[]
for i,x in enumerate(positions):d.add_1d_mesh_line(mesh='m',pos=x,ps=0.2e-4,tag='t'+str(i))
for i,r in enumerate(names):
 d.add_1d_region(mesh='m',region=r,material='Si',tag1='t'+str(i),tag2='t'+str(i+1))
 regions.append({'id':r,'material':'silicon','x0_cm':positions[i],'x1_cm':positions[i+1]})
for i in (1,2):d.add_1d_interface(mesh='m',name='join'+str(i),tag='t'+str(i))
for c,tag in [('left','t0'),('right','t3')]:
 d.add_1d_contact(mesh='m',name=c,material='metal',tag=tag)
d.finalize_mesh(mesh='m');d.create_device(mesh='m',device='d')
for i,r in enumerate(names):
 k={'device':'d','region':r}
 parameters=[('V_t',.025),('EffectiveDensityConduction',1.),
             ('EffectiveDensityValence',1.),('Permittivity',1.)]
 for name,value in parameters:d.set_parameter(**k,name=name,value=value)
 count=len(d.get_node_model_values(**k,name='x'))
 for name,value in [('Potential',.2),('Electrons',1.2+i),('Holes',2.7-.3*i)]:
  d.node_solution(**k,name=name);d.set_node_values(**k,name=name,values=[value]*count)
  d.edge_from_node_model(**k,node_model=name)
 sources=[('PotentialNode','1e5*Potential'),
          ('ElectronGeneration',str((i+1)*1e5)+'*(Electrons+0.3*Holes+0.1*Potential)'),
          ('HoleGeneration',str((i+2)*1e5)+'*(0.4*Electrons-0.8*Holes+Potential)')]
 for name,expr in sources:
  d.node_model(**k,name=name,equation=expr)
  CreateNodeModelDerivative('d',r,name,expr,'Potential','Electrons','Holes')
 for carrier in ('Electron','Hole'):
  den='Electrons' if carrier=='Electron' else 'Holes'
  expr='('+den+'@n0-'+den+'@n1)*EdgeInverseLength'
  d.edge_model(**k,name=carrier+'Current',equation=expr)
  for var in ('Potential','Electrons','Holes'):
   CreateEdgeModelDerivatives('d',r,carrier+'Current',expr,var)
  d.equation(**k,name=carrier+'ContinuityEquation',variable_name=den,node_model=carrier+'Generation',edge_model=carrier+'Current',variable_update='default')
 d.equation(**k,name='PotentialEquation',variable_name='Potential',node_model='PotentialNode',variable_update='default')
for i in (1,2):
 equations=[('Potential','PotentialEquation'),('Electrons','ElectronContinuityEquation'),
            ('Holes','HoleContinuityEquation')]
 for variable,equation in equations:
  model=CreateContinuousInterfaceModel('d','join'+str(i),variable)
  d.interface_equation(device='d',interface='join'+str(i),name=equation,interface_model=model,type='continuous')
for c,r,side in [('left','alpha','n0'),('right','gamma','n1')]:
 for carrier in ('Electron','Hole'):
  model=c+'_'+carrier;expr='3*Electrons@'+side+'-2*Holes@'+side+'+0.7*Potential@'+side
  d.edge_model(device='d',region=r,name=model,equation=expr)
  for var in ('Potential','Electrons','Holes'):CreateEdgeModelDerivatives('d',r,model,expr,var)
  d.contact_equation(device='d',contact=c,name=carrier+'ContinuityEquation',edge_model=model,edge_current_model=carrier+'Current')
payload={'regions':regions,'contacts':[{'id':'left','backend_id':'left','location':'x_min','kind':'metal_work_function'},{'id':'right','backend_id':'right','location':'x_max','kind':'metal_work_function'}]}
solver=s.NativeDensitySolver(d,'d',payload,None);solver.prepare()
assembled=d.get_matrix_and_rhs(format='csc');mm=assembled['static'];unknowns=solver._unknowns();out=[]
for equation,eligible in solver.eligible.items():
 rows={d.get_equation_numbers(device='d',region=r,equation=equation)[i] for r,i in eligible}
 residual,jac=solver._balance(equation,unknowns)
 direct=-math.fsum(mm['rhs'][row] for row in rows)
 discrepancies=[]
 for col in range(len(mm['ap'])-1):
  value=math.fsum(mm['av'][j] for j in range(mm['ap'][col],mm['ap'][col+1]) if mm['ai'][j] in rows)
  discrepancies.append(abs(value-jac.get(col,0)))
 out.append({'physical_rows':len(rows),'residual':residual,'direct_residual':direct,'jacobian_max_error':max(discrepancies)})
print('BALANCE_JSON='+json.dumps(out))
"""
    completed = subprocess.run(
        [
            str(resolve_devsim_python(ROOT)),
            "-c",
            program,
            str(Path(density_solver.__file__).parent),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    outcomes = json.loads(completed.stdout.rsplit("BALANCE_JSON=", 1)[1])
    assert len(outcomes) == 2
    for outcome in outcomes:
        assert outcome["physical_rows"] > 3
        assert outcome["residual"] == pytest.approx(
            outcome["direct_residual"], rel=2e-12, abs=2e-12
        )
        assert outcome["jacobian_max_error"] < 2e-8
