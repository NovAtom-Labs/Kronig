# TCAD Study Design and Interpretation

Status: source-grounded internal guidance awaiting TCAD domain-lead review.

## From question to study

A simulation study should identify the response variable, independent variable, controlled quantities, physical regime, and decision to be supported. Build a baseline before variants. Change one interpretable factor at a time unless the study explicitly examines interactions.

Choose the smallest set of operating points that reveals the expected behavior. A dense sweep is not automatically better and can conceal failed points, waste compute, or make accidental trends look authoritative.

## Hierarchy of confidence

Keep four confidence levels distinct:

1. **Execution:** the simulator ran and produced parseable output.
2. **Numerical validity:** convergence, completeness, conservation, finiteness, and mesh sensitivity meet declared checks.
3. **Model validity:** selected equations, parameters, contacts, and material descriptions represent the intended regime.
4. **Predictive calibration:** results agree with suitable experimental or trusted reference data over the intended domain.

A result cannot skip levels. A converged uncalibrated model is exploratory, not fabrication-predictive.

## Analytical estimates

Use analytical relations to detect order-of-magnitude mistakes and guide meshes. State assumptions beside the estimate. Examples include thermal voltage, charge neutrality, depletion approximation, low-field conductivity, and equilibrium mass action. Do not force a numerical solution to match an analytical approximation outside its regime.

## Sensitivity and identifiability

When a conclusion depends on uncertain parameters, vary them within cited ranges. Report whether the qualitative conclusion survives. Multiple parameter sets can reproduce one terminal curve, so fitting is not proof that each physical parameter is identified.

Calibration should separate training and validation conditions, use bounded parameters, preserve provenance, and compare physically meaningful residuals. Never allow an optimizer or agent to change model families silently merely to reduce error.

## Comparing backends

Align geometry, mesh intent, materials, parameters, statistics, mobility, recombination, band-gap narrowing, contacts, temperature, bias history, observable definitions, and units. Compare semantic outputs and selected metrics. Different discretizations and default models make raw deck equality meaningless.

## Interpreting spatial fields

Inspect both magnitude and position. Relate field peaks to charge, doping transitions, interfaces, and boundary conditions. Check carrier dominance and quasi-equilibrium expectations where applicable. Integrate charge or recombination when the scientific question concerns a total effect rather than a local peak.

## Communicating results

Every numeric statement must trace to canonical fields or an explicit derived calculation. Present validation before conclusions. Separate computed facts, cited background, interpretation, and limitations. Keep the automatic evidence summary for every run, but create a standalone narrative report only when requested or when a durable comparison is the primary deliverable.

## Source basis

- Agent Kronig portable contracts and validators
- DEVSIM official documentation and examples: https://devsim.net/
- NIST semiconductor measurement publications: https://www.nist.gov/publications
- Primary model papers cited in `transport-mobility-recombination.md`
