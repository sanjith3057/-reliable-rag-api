"""Writes eval/QUESTION_BANK.md: every reported question grouped by difficulty level and by document
format, with the result of the last saved run of its set. No LLM is called.

python eval/question_bank.py
"""

import json
import re
from collections import defaultdict
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent

# set name: (title, results file)
SETS = {
    "test": ("Test set: 8 made-up company documents", "results.md"),
    "real": ("Real set: the 88-page GDPR regulation", "results_real.md"),
    "report": ("Report set: a 48-page student project report", "results_report.md"),
    "forms": ("Forms set: a filled-in form and a handwritten scan", "results_forms.md"),
}
LEVELS = {
    1: ("One fact", "The answer is one fact stated in one place"),
    2: ("Several facts, one passage", "A list or a few facts that sit together"),
    3: ("Facts from different places", "The answer needs two passages, or two documents"),
    4: ("A near-miss sits close by", "A similar but wrong value is in another document, version or section"),
    5: ("Must be refused", "The documents are on topic but do not state the fact, or it is off topic"),
}
# PDFs that are not ordinary typed prose
SPECIAL = {
    "medical_intake_form.pdf": "PDF form (labels and values)",
    "handwritten_assignment_scan.pdf": "Scanned PDF (read with OCR)",
}
BY_EXTENSION = {".pdf": "PDF (typed)", ".md": "Markdown", ".txt": "Plain text"}
NO_DOCUMENT = "No document (must be refused)"


def document_format(sources: list[str]) -> str:
    kinds = {SPECIAL.get(name) or BY_EXTENSION[Path(name).suffix.lower()] for name in sources}
    if not kinds:
        return NO_DOCUMENT
    return kinds.pop() if len(kinds) == 1 else "Mixed (" + " + ".join(sorted(kinds)) + ")"


def read_results(path: Path) -> tuple[dict[str, bool], str]:
    """Return {question id: passed} and a one-line description of the run, from a saved results file."""
    if not path.is_file():
        return {}, "not run yet"
    text = path.read_text(encoding="utf-8")
    passed = {
        match.group(1): match.group(2) == "yes" for match in re.finditer(r"^\| (\w+) \| \w+ \| (yes|NO) \|", text, re.M)
    }
    run = re.search(r"^Run: (\S+)", text, re.M)
    model = re.search(r"llm=([^,]+)", text)
    return passed, f"{run.group(1)[:10] if run else '?'}, {model.group(1) if model else '?'}"


def tally(rows: list[dict], key: str) -> dict:
    groups: dict = defaultdict(lambda: [0, 0, 0])  # questions, with a result, passed
    for row in rows:
        group = groups[row[key]]
        group[0] += 1
        if row["passed"] is not None:
            group[1] += 1
            group[2] += row["passed"]
    return groups


def score(group: list[int]) -> str:
    return f"{group[2]} / {group[1]}" if group[1] else "not run yet"


def build() -> str:
    rows, runs = [], {}
    for name, (_, results_file) in SETS.items():
        passed, runs[name] = read_results(EVAL_DIR / results_file)
        for item in json.loads((EVAL_DIR / f"questions_{name}.json").read_text(encoding="utf-8")):
            rows.append(
                {
                    "set": name,
                    "id": item["id"],
                    "level": item["level"],
                    "format": document_format(item.get("expected_sources", [])),
                    "question": item["question"],
                    "passed": passed.get(item["id"]),
                }
            )

    lines = [
        "# Question bank",
        "",
        f"All {len(rows)} reported questions, grouped two ways: by how hard the question is, and by the kind of",
        "document it is asked about. The pass marks come from the last saved run of each set.",
        "Written by `python eval/question_bank.py`; do not edit by hand.",
        "",
        "## Results by difficulty level",
        "",
        "| Level | Kind of question | What makes it hard | Questions | Passed |",
        "| --- | --- | --- | --- | --- |",
    ]
    by_level = tally(rows, "level")
    for level, (title, why) in LEVELS.items():
        lines.append(f"| {level} | {title} | {why} | {by_level[level][0]} | {score(by_level[level])} |")
    total = [len(rows), sum(r["passed"] is not None for r in rows), sum(bool(r["passed"]) for r in rows)]
    lines += [f"| | **All** | | {total[0]} | {score(total)} |", ""]

    lines += [
        "## Results by document format",
        "",
        "| Format of the document that holds the answer | Questions | Passed |",
        "| --- | --- | --- |",
    ]
    by_format = tally(rows, "format")
    for name in sorted(by_format, key=lambda n: (n == NO_DOCUMENT, n)):
        lines.append(f"| {name} | {by_format[name][0]} | {score(by_format[name])} |")
    lines.append("")

    lines += [
        "## Level by set",
        "",
        "| Set | " + " | ".join(f"Level {n}" for n in LEVELS) + " | Run |",
        "| --- |" + " --- |" * 6,
    ]
    for name in SETS:
        in_set = tally([r for r in rows if r["set"] == name], "level")
        cells = " | ".join(score(in_set[n]) if in_set[n][0] else "-" for n in LEVELS)
        lines.append(f"| {name} | {cells} | {runs[name]} |")
    lines.append("")

    for name, (title, _) in SETS.items():
        lines += [f"## {title}", "", "| ID | Level | Format | Question | Passed |", "| --- | --- | --- | --- | --- |"]
        for row in sorted((r for r in rows if r["set"] == name), key=lambda r: (r["level"], r["id"])):
            mark = "not run" if row["passed"] is None else ("yes" if row["passed"] else "NO")
            lines.append(f"| {row['id']} | {row['level']} | {row['format']} | {row['question']} | {mark} |")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    target = EVAL_DIR / "QUESTION_BANK.md"
    target.write_text(build(), encoding="utf-8")
    print(f"wrote {target}")
