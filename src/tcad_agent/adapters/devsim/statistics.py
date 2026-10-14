"""Continuous Joyce-Dixon statistics, owned and benchmarked by the adapter.

The normalized F_(1/2) integral is approximated, not claimed exact. Matched
Joyce-Dixon/Sommerfeld branches avoid the inconsistent constants and slope in
the pinned native primitives. Forward and inverse use one statistical law.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

BREAKPOINT = 8.46296036621705
OFFSET = -0.0137050034663995
VERSION = "kronig.joyce-dixon.matched.v1"


def inverse_fermi(ratio: float) -> float:
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError("Fermi carrier ratio must be positive and finite")
    if ratio < BREAKPOINT:
        return (
            math.log(ratio)
            + ratio / math.sqrt(8)
            - 0.0049500897298752622 * ratio**2
            + 0.00014838577128872821 * ratio**3
            - 0.0000044256301190009895 * ratio**4
        )
    return math.sqrt((0.75 * math.sqrt(math.pi) * ratio) ** (4 / 3) - math.pi**2 / 6) + OFFSET


def inverse_fermi_derivative(ratio: float) -> float:
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError("Fermi carrier ratio must be positive and finite")
    if ratio < BREAKPOINT:
        return (
            1 / ratio
            + 1 / math.sqrt(8)
            - 2 * 0.0049500897298752622 * ratio
            + 3 * 0.00014838577128872821 * ratio**2
            - 4 * 0.0000044256301190009895 * ratio**3
        )
    return (
        math.sqrt(math.pi)
        / 2
        * (0.75 * math.sqrt(math.pi) * ratio) ** (1 / 3)
        / math.sqrt((0.75 * math.sqrt(math.pi) * ratio) ** (4 / 3) - math.pi**2 / 6)
    )


def fermi(eta: float) -> float:
    if not math.isfinite(eta):
        raise ValueError("Fermi statistical argument must be finite")
    ratio = (
        math.exp(eta)
        if eta < 0
        else 4 / (3 * math.sqrt(math.pi)) * (eta**2 + math.pi**2 / 6) ** 0.75
    )
    if ratio == 0:
        raise ValueError("Fermi density is outside the representable positive range")
    for _ in range(24):
        difference = eta - inverse_fermi(ratio)
        update = difference / inverse_fermi_derivative(ratio)
        new = max(0.5 * ratio, ratio + update)
        if abs(new - ratio) <= 2e-15 * ratio:
            return new
        ratio = new
    raise ValueError("Forward Fermi inversion did not converge")


def inverse_fermi_expression(ratio: str, *, derivative: bool = False) -> str:
    """Native syntax with finite inactive branches, including near zero density."""
    low = f"min(({ratio}),{BREAKPOINT:.17g})"
    high = f"max(({ratio}),{BREAKPOINT:.17g})"
    if derivative:
        small = (
            f"(1/({low})+{1 / math.sqrt(8):.17g}"
            f"-2*0.0049500897298752622*({low})"
            f"+3*0.00014838577128872821*({low})^2"
            f"-4*0.0000044256301190009895*({low})^3)"
        )
        large = (
            f"({math.sqrt(math.pi) / 2:.17g}"
            f"*pow({0.75 * math.sqrt(math.pi):.17g}*({high}),1/3)"
            f"/pow(pow({0.75 * math.sqrt(math.pi):.17g}*({high}),4/3)"
            f"-{math.pi**2 / 6:.17g},0.5))"
        )
    else:
        small = (
            f"(log({low})+{1 / math.sqrt(8):.17g}*({low})"
            f"-0.0049500897298752622*({low})^2"
            f"+0.00014838577128872821*({low})^3"
            f"-0.0000044256301190009895*({low})^4)"
        )
        large = (
            f"(pow(pow({0.75 * math.sqrt(math.pi):.17g}*({high}),4/3)"
            f"-{math.pi**2 / 6:.17g},0.5)+({OFFSET:.17g}))"
        )
    return f"ifelse(({ratio})<{BREAKPOINT:.17g},{small},{large})"


def fermi_models(prefix: str, eta: str) -> dict[str, str]:
    """Positive native inversion; each named step preserves native precision."""
    models = {
        f"{prefix}Eta": eta,
        f"{prefix}R0": (
            f"ifelse({prefix}Eta<0,exp(min({prefix}Eta,0)),"
            f"{4 / (3 * math.sqrt(math.pi)):.17g}"
            f"*pow({prefix}Eta^2+{math.pi**2 / 6:.17g},0.75))"
        ),
    }
    for index in range(8):
        ratio = f"{prefix}R{index}"
        models[f"{prefix}Inv{index}"] = inverse_fermi_expression(ratio)
        models[f"{prefix}DInv{index}"] = inverse_fermi_expression(ratio, derivative=True)
        models[f"{prefix}R{index + 1}"] = (
            f"max(0.5*{ratio},{ratio}+({prefix}Eta-{prefix}Inv{index})/{prefix}DInv{index})"
        )
    models[f"{prefix}Derivative"] = (
        f"1/({inverse_fermi_expression(f'{prefix}R8', derivative=True)})"
    )
    return models


def rewrite_inverse(expression: str) -> str:
    """Replace balanced primitive calls, not arbitrary model identifiers."""
    for function in ("dInvFermidx", "InvFermi"):
        while f"{function}(" in expression:
            start = expression.index(f"{function}(")
            begin = start + len(function) + 1
            end, depth = begin, 1
            while depth and end < len(expression):
                depth += (expression[end] == "(") - (expression[end] == ")")
                end += 1
            if depth:
                raise ValueError("Unbalanced inverse Fermi expression")
            expression = (
                expression[:start]
                + inverse_fermi_expression(
                    expression[begin : end - 1], derivative=function == "dInvFermidx"
                )
                + expression[end:]
            )
    return expression


class NativeStatistics:
    """Named forward models with explicit chain derivatives in native precision."""

    def __init__(
        self, backend: Any, *, variables: tuple[str, ...] = ("Potential", "Electrons", "Holes")
    ) -> None:
        self.backend = backend
        self.variables = variables
        self.prepared: set[tuple[str, str, str]] = set()

    def node_expression(
        self, device: str, region: str, expression: str, *, expand_inverse: bool = True
    ) -> str:
        if expand_inverse:
            expression = rewrite_inverse(expression)
        while match := re.search(r"(?<![A-Za-z0-9_])Fermi\(", expression):
            start, begin = match.start(), match.end()
            end, depth = begin, 1
            while depth and end < len(expression):
                depth += (expression[end] == "(") - (expression[end] == ")")
                end += 1
            if depth:
                raise ValueError("Unbalanced forward Fermi expression")
            eta = expression[begin : end - 1]
            prefix = "FermiStat_" + hashlib.sha256(eta.encode()).hexdigest()[:16] + "_"
            key = device, region, prefix
            if key not in self.prepared:
                kw = {"device": device, "region": region}
                for name, equation in fermi_models(prefix, eta).items():
                    self.backend.node_model(**kw, name=name, equation=equation)
                for variable in self.variables:
                    # SYMDIFF treats a named model's derivative as another named
                    # model. Only the converged forward value needs this chain;
                    # intermediate inversion iterations are not physical unknowns.
                    self.backend.node_model(
                        **kw, name=f"{prefix}Eta:{variable}", equation=f"diff({eta},{variable})"
                    )
                    self.backend.node_model(
                        **kw,
                        name=f"{prefix}R8:{variable}",
                        equation=f"{prefix}Derivative*{prefix}Eta:{variable}",
                    )
                self.prepared.add(key)
            expression = expression[:start] + f"{prefix}R8" + expression[end:]
        return expression

    def create_derivative(
        self, kind: str, scope: dict[str, str], model: str, expression: str, variable: str
    ) -> None:
        """Differentiate opaque primitives first, then substitute matched slopes.

        Native-context differentiation retains named dependency partials.
        Expanding piecewise inverse statistics first creates unnecessarily large
        symbolic trees. Both orders yield the same physical Jacobian.
        """
        if kind not in {"node", "edge", "contact_node"}:
            raise ValueError("Unsupported native statistical model centering")
        if kind != "edge":
            region = (
                scope.get("region")
                or self.backend.get_region_list(device=scope["device"], contact=scope["contact"])[0]
            )
            expression = self.node_expression(
                scope["device"], region, expression, expand_inverse=False
            )
        creator = getattr(self.backend, kind + "_model")
        name = f"{model}:{variable}"
        derivative = creator(
            **scope, name=name, equation=f"simplify(diff({expression},{variable}))"
        )
        creator(**scope, name=name, equation=rewrite_inverse(derivative))
