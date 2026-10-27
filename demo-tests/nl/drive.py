"""Opt-in backend researcher driver using the real product API and live provider.

Answers are researcher-authored files, never production prompt matching rules.
Unmapped questions remain unanswered until the test operator supplies a response.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from uuid import UUID


FALLBACK = []


def researcher_answer(question: dict, answers: dict[str, str]) -> str | None:
    if question["id"] in answers:
        return answers[question["id"]]
    path = question["field_path"]
    candidates = [key for key in answers if path == key or path.startswith(key + ".")]
    if candidates:
        return answers[max(candidates, key=len)]
    if "*" in answers:
        FALLBACK.append({"id": question["id"], "field_path": path, "prompt": question.get("prompt")})
        return answers["*"]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--deadline", type=float, default=900)
    args = parser.parse_args()

    from dotenv import load_dotenv
    from fastapi.testclient import TestClient

    from tcad_agent.agent.events import safe_event_text
    from tcad_agent.agent.runtime import OpenHandsRuntimeFactory, llm_from_environment
    from tcad_agent.agent.supervisor import AgentSupervisor
    from tcad_agent.ide.conversations import ConversationService
    from tcad_agent.ide.events import EventFeed
    from tcad_agent.ide.models import RunState
    from tcad_agent.ide.store import SqliteIDEStore
    from tcad_agent.ide.workspaces import WorkspaceManager
    from tcad_agent.prompting.service import build_default_prompt_preparation
    from tcad_agent.web.app import create_app
    from tcad_agent.web.ide_routes import IDEServices

    root = Path(r"C:\Development\NovAtom Labs\Kronig")
    load_dotenv(root / ".env", override=False)
    if not os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
        raise RuntimeError("Live provider credential is not configured")
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    repository = destination / "workspace"
    repository.mkdir()
    if args.context:
        (repository / "RESEARCH_CONTEXT.md").write_text(args.context.read_text())
    secret = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")

    def safe(value):
        if isinstance(value, str):
            return safe_event_text(value, (secret,))
        if isinstance(value, dict):
            return {key: safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [safe(item) for item in value]
        return value

    def save(name, value):
        (destination / name).write_text(json.dumps(safe(value), indent=2) + "\n")

    store = SqliteIDEStore(destination / "runtime" / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(WorkspaceManager(store), ConversationService(store, events), events)
    supervisor = AgentSupervisor(
        services,
        OpenHandsRuntimeFactory(services.runtime_root, llm=llm_from_environment()),
        preparation=build_default_prompt_preparation(root),
    )
    started = time.monotonic()
    history = []
    transitions = []
    cursor = 0
    last_state = None
    last_questions = None
    answered = set()
    terminal = {RunState.COMPLETED, RunState.FAILED, RunState.BLOCKED, RunState.CANCELLED}
    with TestClient(create_app(ide=services, agent_supervisor=supervisor)) as web:
        workspace = web.post("/api/workspaces", json={"path": str(repository)}).json()
        session = f"/api/workspaces/{workspace['id']}/session"
        conversation = web.post(session).json()
        message = web.post(f"{session}/messages", json={"content": args.prompt.read_text(encoding="utf-8")}).json()
        response = web.post(f"{session}/runs", json={"message_id": message["id"]})
        response.raise_for_status()
        run_id = UUID(response.json()["id"])
        save(
            "identity.json",
            {"workspace": workspace, "conversation": conversation, "run": str(run_id)},
        )
        while time.monotonic() - started < args.deadline:
            elapsed = round(time.monotonic() - started, 3)
            run = store.get_run(run_id)
            if run.state != last_state:
                transitions.append({"seconds": elapsed, "state": run.state.value})
                print(json.dumps(transitions[-1]), flush=True)
                last_state = run.state
            batch = events.list_after(UUID(conversation["id"]), cursor, 500)
            for event in batch:
                cursor = event.id
                record = {"seconds": elapsed, **event.model_dump(mode="json")}
                history.append(record)
                if event.kind in {
                    "prompt_preparation_progress",
                    "tool_call_started",
                    "tool_call_completed",
                    "plan_ready",
                    "result_ready",
                    "run_error",
                }:
                    print(
                        json.dumps(
                            {
                                "seconds": elapsed,
                                "event": event.kind,
                                "operation": event.payload.get("operation"),
                                "phase": event.payload.get("phase"),
                            }
                        ),
                        flush=True,
                    )
            save("events.json", history)
            save("transitions.json", transitions)
            if run.state in terminal:
                break
            if run.state is RunState.WAITING_FOR_USER:
                pending = web.get(f"/api/runs/{run_id}/preparation").json()
                save("preparation.json", pending)
                questions = pending["decision"]["questions"]
                signature = json.dumps(questions)
                if signature != last_questions:
                    print(json.dumps({"seconds": elapsed, "questions": questions}), flush=True)
                    last_questions = signature
                supplied = json.loads(args.answers.read_text(encoding="utf-8"))
                replies = [
                    {"question_id": q["id"], "answer": researcher_answer(q, supplied)}
                    for q in questions
                ]
                if all(item["answer"] for item in replies):
                    key = (pending["revision"], signature)
                    if key not in answered:
                        response = web.post(
                            f"/api/runs/{run_id}/clarifications",
                            json={"expected_revision": pending["revision"], "answers": replies},
                        )
                        response.raise_for_status()
                        answered.add(key)
                        save(
                            f"answers-{len(answered)}.json",
                            {"seconds": elapsed, "questions": questions, "answers": replies},
                        )
            elif run.state is RunState.WAITING_FOR_PLAN_APPROVAL:
                plan = web.get(f"/api/runs/{run_id}/plan").json()
                save("plan.json", plan)
                response = web.post(
                    f"/api/runs/{run_id}/plan/approve",
                    json={
                        "expected_revision": plan["revision"],
                        "plan_digest": plan["plan_digest"],
                        "mode": "unattended_local",
                    },
                )
                response.raise_for_status()
            elif run.state is RunState.WAITING_FOR_APPROVAL:
                approvals = web.get(f"{session}/approvals").json()
                save("unexpected-approvals.json", approvals)
                for approval in approvals:
                    allow = approval["permission_category"] == "simulation_execution"
                    endpoint = "approve-category" if allow else "deny"
                    payload = {"expected_revision": approval["revision"]}
                    if not allow:
                        payload["reason"] = (
                            "This local scientific evaluation does not authorize external "
                            "or system actions."
                        )
                    response = web.post(f"/api/approvals/{approval['id']}/{endpoint}", json=payload)
                    response.raise_for_status()
            time.sleep(0.25)
        else:
            supervisor.stop(run_id)
            supervisor.join(run_id, timeout=15)
        summary = {
            "seconds": round(time.monotonic() - started, 3),
            "state": store.get_run(run_id).state.value,
            "clarification_batches": len(answered),
            "transitions": transitions,
        }
        response = web.get(f"/api/runs/{run_id}/result")
        if response.status_code == 200:
            result = response.json()
            save("result.json", result)
            summary["assessment"] = result.get("assessment")
            summary["validation"] = result.get("validation")
        save("fallback.json", FALLBACK)
        save("messages.json", web.get(f"{session}/messages").json())
        save("summary.json", summary)
        print(
            json.dumps(
                {
                    "finished": summary["state"],
                    "seconds": summary["seconds"],
                    "clarification_batches": summary["clarification_batches"],
                }
            ),
            flush=True,
        )
    return 0 if summary["state"] == "completed" and response.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
