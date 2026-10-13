"""Exercise the real runtime loop with deterministic solve failures, without a native process."""

import ast
import math
from pathlib import Path

import pytest

from tcad_agent.adapters.devsim import runtime


@pytest.mark.parametrize("retries", [0, 1, 3])
def test_initial_failed_dc_attempt_counts_toward_retry_budget(retries):
    tree = ast.parse(Path(runtime.__file__).read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    loop = next(
        n
        for n in main.body
        if isinstance(n, ast.For)
        and isinstance(n.target, ast.Name)
        and n.target.id == "requested_bias"
    )
    stop = next(
        i
        for i, n in enumerate(loop.body)
        if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "converged"
    )
    loop.body = loop.body[:stop]
    module = ast.fix_missing_locations(ast.Module(body=[loop], type_ignores=[]))
    state = {"bias": 0.0}
    attempts = []

    def solve(**kwargs):
        attempts.append(state["bias"])
        if state["bias"] != 0:
            raise RuntimeError("injected nonconvergence")

    namespace = {
        "math": math,
        "AdaptiveStepController": runtime.AdaptiveStepController,
        "TransientRecoveryExhausted": runtime.TransientRecoveryExhausted,
        "_initial_dc_bias": runtime._initial_dc_bias,
        "_bias_points": lambda study: [1.0],
        "payload": {
            "study": {"strategy": "adaptive", "minimum_step_v": 0.001, "maximum_retries": retries}
        },
        "requested_contact": "left",
        "study_backend_contact": "left",
        "temperature": 300,
        "current_bias": 0.0,
        "equilibrium_predictor": False,
        "solver_events": [],
        "dc_absolute_error": 1e-10,
        "solver": {"relative_error": 1e-5, "maximum_iterations": 20},
        "checkpoint_state": lambda *args, **kwargs: None,
        "predict_stationary_equilibrium": lambda bias: None,
        "set_dc_bias": lambda bias: state.update(bias=bias),
        "solve": solve,
    }
    exec(compile(module, "extracted-declared-runtime-loop", "exec"), namespace)
    assert len([bias for bias in attempts if bias != 0]) == retries + 1
    assert attempts[-1] == 0  # Native restoration is not another requested-point attempt.
