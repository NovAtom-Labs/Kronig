# Meshing, Numerics, and Convergence

Status: source-grounded internal guidance awaiting TCAD domain-lead review.

## Mesh follows the quantity of interest

Mesh adequacy is defined relative to a reported quantity, not a universal spacing. Resolve region boundaries, material interfaces, abrupt or graded doping transitions, depletion regions, inversion and accumulation layers, narrow layers, high-field peaks, generation hotspots, and geometric corners that control current crowding.

A physically motivated first estimate may use layer thickness, depletion width, Debye length, or expected field-gradient scale. These estimates depend on regime and assumptions. They guide the baseline mesh but do not replace convergence testing.

## Mesh-convergence study

Hold scientific inputs fixed and vary only the mesh. Preserve each run separately. Compare predeclared metrics such as integrated charge, terminal current density, built-in potential, depletion width, field peak and position, or recombination integral.

Use both absolute and relative differences. Relative error alone behaves badly near zero. A smooth plot or a successful nonlinear solve does not establish mesh convergence.

Peak values require special care because the discrete maximum can rise as the mesh resolves a narrow feature. Record whether the value is nodal, edge-based, cell-centred, or interpolated. Compare location as well as magnitude.

## Nonlinear solution sequence

Semiconductor equations are strongly coupled and nonlinear. A common robust sequence is electrostatic initialization, equilibrium carrier solution, then continuation through voltage or time. Each converged state can initialize the next. This sequence is a numerical strategy and must not change the requested physical endpoints.

Potential remedies for convergence failure include equilibrium restart, smaller continuation step, last-converged-state restart, bounded local refinement, scaling review, and a justified solver-tolerance change. Do not automatically change doping, geometry, material, contacts, model set, temperature, or requested outputs.

## Residual and update criteria

Solver termination may be based on residual norms, variable updates, or both. Learn the backend's exact criteria from the versioned manual. A small update can coexist with an unacceptable residual when a solve stagnates. A residual threshold without physical validation does not guarantee a meaningful solution.

Record absolute error, relative error, maximum iterations, damping or line-search behavior, linear solver, precision mode, and any continuation parameters that affect reproducibility.

## Discrete conservation

Finite-volume methods are designed around flux balance over control volumes. Validate terminal current conservation and, where available, local equation residuals. Sign and orientation conventions must be normalized before comparing terminals.

## DEVSIM diagnostics

Search version-matched official documentation for the `solve` command, convergence information, problem-node diagnostics, precision controls, and solver selection. Do not assume that an option from the current online manual exists in the installed 2.9.x runtime.

## Failure classification

Distinguish invalid input, unsupported capability, infrastructure failure, initialization failure, continuation failure, mesh insufficiency, model expression error, parser failure, and post-solve physical-validation failure. Retrying is useful only for classes that can plausibly change under permitted numerical recovery.

## Source basis

- DEVSIM Manual, equation, meshing, and solver chapters: https://devsim.net/
- DEVSIM pinned source and regression tests: https://github.com/devsim/devsim
- D. L. Scharfetter and H. K. Gummel, IEEE Transactions on Electron Devices 16 (1969), https://doi.org/10.1109/T-ED.1969.16566
