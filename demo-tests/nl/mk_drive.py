import pathlib
src = pathlib.Path(r"C:\Development\NovAtom Labs\Kronig\scripts\verify_live_research_workflows.py").read_text(encoding="utf-8")
src = src.replace('''    return answers[max(candidates, key=len)] if candidates else None''', '''    if candidates:
        return answers[max(candidates, key=len)]
    if "*" in answers:
        FALLBACK.append({"id": question["id"], "field_path": path, "prompt": question.get("prompt")})
        return answers["*"]
    return None''')
src = src.replace("def researcher_answer(", "FALLBACK = []\n\n\ndef researcher_answer(", 1)
src = src.replace('''        save("messages.json", web.get(f"{session}/messages").json())''', '''        save("fallback.json", FALLBACK)
        save("messages.json", web.get(f"{session}/messages").json())''')
src = src.replace("root = Path(__file__).resolve().parents[1]", 'root = Path(r"C:\\Development\\NovAtom Labs\\Kronig")')
src = src.replace("answers.read_text())", 'answers.read_text(encoding="utf-8"))').replace("args.prompt.read_text()", 'args.prompt.read_text(encoding="utf-8")')
pathlib.Path(r"C:\Development\NovAtom Labs\Kronig\demo-tests\nl\drive.py").write_text(src, encoding="utf-8")
print("ok", "FALLBACK.append" in src, "fallback.json" in src)