"""Check one natural-language run against its ground truth and summarize what happened."""
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from catalog import TESTS  # noqa: E402
from tcad_agent.domain.models import ExperimentSpec  # noqa: E402


def close(a, b, rel=1e-3, absolute=1e-9):
    return math.isclose(a, b, rel_tol=rel, abs_tol=absolute)


def check_spec(spec: ExperimentSpec, expect: dict) -> list[tuple[str, bool, str]]:
    rows = []

    def add(label, ok, detail=""):
        rows.append((label, bool(ok), str(detail)))

    add("dimension", spec.dimension == expect["dimension"], spec.dimension)
    add("temperature", close(spec.physics.temperature.to("K"), expect["temperature_k"]), spec.physics.temperature)
    regions = sorted(spec.regions, key=lambda r: r.x0.to("um"))
    if "regions" in expect:
        got = [(r.material, round(r.x0.to("um"), 6), round(r.x1.to("um"), 6)) for r in regions]
        want = [(m, x0, x1) for m, x0, x1 in expect["regions"]]
        ok = len(got) == len(want) and all(g[0] == w[0] and close(g[1], w[1], 1e-3, 1e-6) and close(g[2], w[2], 1e-3, 1e-6) for g, w in zip(got, want, strict=False))
        add("regions", ok, got)
    for species, value, index in expect.get("doping", []):
        rid = regions[index].id if index < len(regions) else None
        hits = [p for p in spec.profiles if p.region == rid and str(p.species) == species]
        add(f"doping {species} {value:g} in region {index}", any(close(p.value.to("cm^-3"), value, 1e-3) for p in hits), [(str(p.species), p.value.to("cm^-3")) for p in spec.profiles if p.region == rid])
    if "doping2d" in expect:
        got = [(str(p.species), p.value.to("cm^-3")) for p in spec.profiles]
        acceptors = [v for sp, v in got if sp == "acceptor" and close(v, 1e17)]
        donors = [v for sp, v in got if sp == "donor" and close(v, 1e20)]
        stray = [g for g in got if not (close(g[1], 1e17) or close(g[1], 1e20))]
        add("doping 2d", bool(acceptors) and len(donors) >= 2 and not stray, got)
    study = expect.get("study")
    if study:
        s = spec.study
        kind = str(s.kind)
        if study["kind"] == "dc":
            # A list of explicit voltages and a start/stop/step range describe the same sweep.
            want = []
            value = study["start"]
            while value <= study["stop"] + 1e-9:
                want.append(round(value, 9))
                value += study["step"]
            if kind == "dc":
                got = [round(s.start.to("V") + i * s.step.to("V"), 9) for i in range(len(want))]
                ok = close(s.start.to("V"), study["start"], 1e-6, 1e-9) and close(s.stop.to("V"), study["stop"], 1e-6, 1e-9) and close(s.step.to("V"), study["step"], 1e-6, 1e-9)
                add("study range", ok, f"{s.start} -> {s.stop} step {s.step}")
            elif kind == "dc_points":
                got = sorted(round(v.to("V"), 9) for v in s.values)
                add("study points", got == want, got)
            else:
                add("study kind", False, kind)
            swept = {c.id: c for c in spec.contacts}[s.contact]
            add("swept contact", expect_swept(expect, study)(swept), f"{swept.id} {swept.location} {swept.kind}")
        else:
            add("study kind", kind == study["kind"], kind)
    for model in expect.get("models", []):
        add(f"model {model}", model in [str(m) for m in spec.physics.models], [str(m) for m in spec.physics.models])
    have = {str(o) for o in spec.observables}
    missing = [o for o in expect.get("observables", []) if o not in have]
    add("observables retained", not missing, f"missing {missing}" if missing else sorted(have))
    if "contacts" in expect:
        add("contact count", len(spec.contacts) == expect["contacts"], len(spec.contacts))
    if "contact_wf" in expect:
        add("work function", any(close(c.work_function.to("eV"), expect["contact_wf"]) for c in spec.contacts if c.work_function is not None), [(c.id, str(c.work_function)) for c in spec.contacts])
    if "profile_bias" in expect:
        got = sorted(spec.profile_bias_values_v()) if spec.profile_sampling is not None else None
        add("profile sampling biases", got == sorted(expect["profile_bias"]), got)
    if expect["dimension"] == 2:
        ox = [r for r in spec.regions if r.material == "silicon_dioxide"]
        si = [r for r in spec.regions if r.material == "silicon"]
        add("oxide thickness", bool(ox) and close(ox[0].x1.to("nm") - ox[0].x0.to("nm"), expect["oxide_nm"], 1e-3), [(r.id, str(r.x0), str(r.x1)) for r in ox])
        # Depths are measured from the oxide-silicon interface, so the origin of the x axis is free.
        interface = ox[0].x1.to("nm") if ox else 0
        deepest = (max(r.x1.to("nm") for r in si) - interface) if si else 0
        left = min(r.y0.to("um") for r in si) if si else 0
        right = max(r.y1.to("um") for r in si) if si else 0
        add("body extent", bool(si) and close(deepest, 200, 1e-3, 1) and close(left, 0, 0, 1e-6) and close(right, expect["body"][1], 1e-3, 1e-6), f"silicon {deepest} nm deep below the interface, lateral {left}-{right} um")
        cut = (spec.profile_cuts[0].at.to("nm") - interface) if spec.profile_cuts else None
        add("profile cut depth", cut is not None and close(cut, 1, 0.0, 0.2), f"{cut} nm below the oxide-silicon interface")
        add("device width", spec.width is not None and close(spec.width.to("um"), expect["width_um"]), spec.width)
        by_loc = {c.id: c for c in spec.contacts}
        drains = [c for c in spec.contacts if c.span is not None and close(c.span[0].to("um"), 0.2, 1e-3, 1e-6)]
        gates = [c for c in spec.contacts if c.kind == "metal_work_function"]
        if "drain_offset" in expect:
            add("drain bias held", bool(drains) and close(drains[0].voltage_offset.to("V"), expect["drain_offset"], 1e-6, 1e-9), [(c.id, str(c.voltage_offset)) for c in spec.contacts])
        if "gate_offset" in expect:
            add("gate bias held", bool(gates) and close(gates[0].voltage_offset.to("V"), expect["gate_offset"], 1e-6, 1e-9), [(c.id, str(c.voltage_offset)) for c in spec.contacts])
        del by_loc
    return rows


def expect_swept(expect, study):
    kind = expect.get("swept") or {
        "t2": "x_min", "t3": "x_min", "t5": "metal", "t7": "metal", "t8": "metal", "t9": "metal",
    }
    return None


def swept_rule(name):
    return {"t2": lambda c: c.location == "x_min", "t3": lambda c: c.location == "x_min",
            "t5": lambda c: c.kind == "metal_work_function", "t7": lambda c: c.kind == "metal_work_function",
            "t8": lambda c: c.kind == "metal_work_function",
            "t9a": lambda c: c.kind == "metal_work_function",
            "t9b": lambda c: c.span is not None and 0.2 - 1e-6 <= c.span[0].to("um") <= 0.2 + 0.03}


def main(run_dir: pathlib.Path, name: str) -> int:
    out = run_dir / "out"
    expect = TESTS[name]["expect"]
    report = {"test": name, "experiment": TESTS[name]["experiment"], "prompt": TESTS[name]["prompt"]}
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8")) if (out / "summary.json").exists() else {}
    report["run_state"] = summary.get("state")
    batches = sorted(out.glob("answers-*.json"))
    report["clarification_batches"] = len(batches)
    questions = []
    for b in batches:
        for q in json.loads(b.read_text(encoding="utf-8"))["questions"]:
            questions.append({"field": q.get("field_path"), "prompt": q.get("prompt")})
    report["questions"] = questions
    fb = out / "fallback.json"
    report["fallback_answers"] = json.loads(fb.read_text(encoding="utf-8")) if fb.exists() else []
    plan = out / "plan.json"
    rows = []
    if plan.exists():
        spec = ExperimentSpec.model_validate(json.loads(plan.read_text(encoding="utf-8"))["prepared"]["spec"])
        # the swept-contact rule is test specific
        global expect_swept
        rules = swept_rule(name)
        rule = rules.get(name) or rules.get(name.removesuffix("d")) or rules.get(name[:2]) or (lambda c: True)
        expect_swept = lambda e, s: rule  # noqa: E731
        rows = check_spec(spec, expect)
    else:
        rows = [("plan produced", False, "no plan.json")]
    report["spec_checks"] = [{"check": a, "ok": b, "detail": c} for a, b, c in rows]
    v = summary.get("validation") or {}
    report["validation_overall"] = v.get("overall")
    checks = v.get("checks") or []
    report["validation_failed"] = [{"id": c["id"], "measured": c.get("measured_value"), "limit": c.get("limit")} for c in checks if c.get("status") == "failed"]
    report["validation_counts"] = {s: sum(1 for c in checks if c.get("status") == s) for s in ("passed", "failed", "not_applicable")}
    (run_dir / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    bad = [r for r in rows if not r[1]]
    print(f"{name} state={report['run_state']} validation={report['validation_overall']} counts={report['validation_counts']} "
          f"batches={len(batches)} questions={len(questions)} fallback={len(report['fallback_answers'])} spec_mismatches={len(bad)}")
    for a, _, c in bad:
        print(f"   SPEC MISMATCH {a}: {str(c)[:160]}")
    for f in report["validation_failed"]:
        print(f"   VALIDATION FAIL {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(pathlib.Path(sys.argv[1]), sys.argv[2]))