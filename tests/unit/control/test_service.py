from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import BackendBinding
from tcad_agent.control.models import ClarificationAnswer, RequestState
from tcad_agent.control.service import (
    ControlService,
    ExecutionNotApprovedError,
    PlanDigestMismatchError,
)
from tcad_agent.control.store import SqliteRequestStore
from tcad_agent.knowledge.models import Passage
from tcad_agent.knowledge.retrieve import KnowledgeIndex
from tcad_agent.model_gateway.base import (
    AgentContextPacket,
    AgentProposal,
    ScriptedModelGateway,
)
from tcad_agent.runners.remote import RemoteProtocolError


def proposal() -> AgentProposal:
    payload = yaml.safe_load(Path("examples/pn-junction.yaml").read_text())
    return AgentProposal(kind="spec", spec=payload)


def service(tmp_path: Path) -> ControlService:
    return ControlService(
        store=SqliteRequestStore(tmp_path / "requests.sqlite3"),
        gateway=ScriptedModelGateway((proposal(),)),
        workspace=tmp_path / "workspace",
    )


def test_approval_requires_exact_digest_and_is_idempotent(tmp_path: Path) -> None:
    control = service(tmp_path)
    submitted = control.submit("simulate the complete approved reference", backend="devsim")
    assert submitted.state is RequestState.USER_CONFIRMATION_REQUIRED
    with pytest.raises(PlanDigestMismatchError):
        control.approve(submitted.id, "wrong-digest")
    approved = control.approve(submitted.id, submitted.plan_digest or "")
    duplicate = control.approve(submitted.id, submitted.plan_digest or "")
    assert approved.state is RequestState.COMPILED
    assert duplicate == approved


def test_execution_before_approval_is_refused(tmp_path: Path) -> None:
    control = service(tmp_path)
    submitted = control.submit("simulate the complete approved reference", backend="devsim")
    with pytest.raises(ExecutionNotApprovedError):
        control.execute(submitted.id)


def test_concurrent_execution_creates_at_most_one_bundle(tmp_path: Path) -> None:
    control = service(tmp_path)
    submitted = control.submit("simulate the complete approved reference", backend="devsim")
    control.approve(submitted.id, submitted.plan_digest or "")
    with ThreadPoolExecutor(max_workers=2) as executor:
        views = tuple(executor.map(lambda _: control.execute(submitted.id), range(2)))
    final = control.get(submitted.id)
    assert final.state is RequestState.COMPLETED
    assert {view.state for view in views} <= {
        RequestState.RUNNING,
        RequestState.VALIDATING,
        RequestState.COMPLETED,
    }
    assert len(tuple((tmp_path / "workspace" / "bundles").glob("*"))) == 1


def test_clarification_answers_and_retrieved_knowledge_reach_model_context(
    tmp_path: Path,
) -> None:
    class RecordingGateway:
        context: AgentContextPacket | None = None

        def propose(self, request, context: AgentContextPacket) -> AgentProposal:
            del request
            self.context = context
            return proposal()

    index_path = tmp_path / "knowledge.sqlite3"
    KnowledgeIndex.build(
        index_path,
        (
            Passage.create(
                id="reviewed:0",
                source_id="reviewed",
                title="Reviewed equilibrium note",
                url="internal://reviewed",
                license="internal",
                access="restricted",
                trust="internal-reviewed",
                backend="devsim",
                version="2.9.1",
                reviewed=True,
                content="Aluminum silicon equilibrium requires explicit contact treatment.",
            ),
        ),
    )
    gateway = RecordingGateway()
    control = ControlService(
        store=SqliteRequestStore(tmp_path / "requests.sqlite3"),
        gateway=gateway,
        workspace=tmp_path / "workspace",
        knowledge_index=index_path,
    )
    prompt = Path("examples/prompts/al-pn-al-equilibrium.md").read_text()
    submitted = control.submit(prompt, backend="devsim")
    planned = control.answer(
        submitted.id,
        (
            ClarificationAnswer(field="geometry.p_region_thickness", value="1 um"),
            ClarificationAnswer(field="geometry.n_region_thickness", value="1 um"),
            ClarificationAnswer(field="contacts.treatment", value="ohmic"),
        ),
    )
    assert gateway.context is not None
    assert planned.prompt == prompt
    assert planned.clarification_answers == {
        "geometry.p_region_thickness": "1 um",
        "geometry.n_region_thickness": "1 um",
        "contacts.treatment": "ohmic",
    }
    assert gateway.context.clarification_answers == {
        "geometry.p_region_thickness": "1 um",
        "geometry.n_region_thickness": "1 um",
        "contacts.treatment": "ohmic",
    }
    assert gateway.context.knowledge[0].citation.source_id == "reviewed"
    assert gateway.context.knowledge[0].reviewed
    manifest = gateway.context.capabilities["manifest"]
    assert isinstance(manifest, dict)
    assert manifest["backend"] == "devsim"
    assert "potential" in manifest["observables"]
    assert any(
        "Building Simulator-Neutral Experiments" in item
        for item in gateway.context.procedures
    )


def test_execution_transport_failure_becomes_terminal_request_failure(
    tmp_path: Path,
) -> None:
    class BrokenRunner:
        def run(self, job, budget):
            del job, budget
            raise RemoteProtocolError("runner connection failed")

    binding = BackendBinding(
        adapter=DevsimAdapter.from_defaults(),
        runner=BrokenRunner(),
    )
    control = ControlService(
        store=SqliteRequestStore(tmp_path / "requests.sqlite3"),
        gateway=ScriptedModelGateway((proposal(),)),
        workspace=tmp_path / "workspace",
        backend_resolver=lambda _backend: binding,
    )
    submitted = control.submit("simulate the complete approved reference", backend="devsim")
    control.approve(submitted.id, submitted.plan_digest or "")
    failed = control.execute(submitted.id)
    assert failed.state is RequestState.FAILED
    assert failed.error_code == "execution_transport"
    assert control.events(submitted.id)[-1].kind.value == "failed"
