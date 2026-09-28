"""Stable experiment-engine failures."""

from tcad_agent.capabilities.models import CapabilityDecision


class ExperimentEngineError(RuntimeError):
    """Base class for deterministic experiment-engine failures."""


class ExperimentCapabilityError(ExperimentEngineError):
    """Raised when the selected backend cannot represent an experiment."""

    def __init__(self, decision: CapabilityDecision) -> None:
        self.decision = decision
        details = "; ".join(
            f"{issue.path}: {issue.message}" for issue in decision.issues
        )
        super().__init__(details or "experiment is unsupported by the selected backend")


class PlanDigestMismatchError(ExperimentEngineError):
    """Raised when execution approval does not match the prepared plan."""


class ExperimentExecutionError(ExperimentEngineError):
    """Raised when the simulator boundary cannot produce a result bundle."""
