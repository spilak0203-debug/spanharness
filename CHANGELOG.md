# Changelog

## 0.1.1 - 2026-11-13

- New role `circuit` (fable · high) for circuit board (PCB) design in KiCad through `kicad-cli` and scripts, up to Gerber, BOM and placement files ready to order, plus wiring between modules; verified by calculation, and every design to be built and powered goes to `deep-reviewer` first.
- `coder` checks other holders of the same state, edge and hostile input, failure midway and repeats, and boundary tests before it returns, and does not return while a background command is still running.
- `architect`, `designer` and `modeler` report which of the requirement numbers they were handed their result does not meet.
- The orchestrator keeps the user's requirements and rejections as a numbered list in `docs/plan.md`, hands the list with every design or implementation hand-off, and checks the result against it before reporting.
- `designer` and `modeler` run on `fable` instead of `opus`.
- `architect` runs on `fable` at effort `high` instead of `opus` at `xhigh`.
- `scripts/prices.json` has Claude Fable 5.2 ($8 / $40 per million tokens, cache write $10, cache read $0.20).

## 0.1.0 - 2026-10-23

Initial release.

- 11 specialist subagents: architect, coder, reviewer, deep-reviewer, tester, experimenter, researcher, doc-writer, designer, modeler and harness-advisor.
- Orchestrator output style, opt-in: `/output-style spanharness:orchestrator`.
- `new-project` skill.
- Lessons recorder and `report` command, in Python (macOS, Linux) and PowerShell (Windows), both written to the specification in `docs/lessons-format.md`. Data goes to `~/.claude/lessons/`; `SPANHARNESS_RECORD=0` turns recording off.
- `lint` command that checks the repository against `tests/harness-rules.json`.
- Conformance tests that run the same cases through both implementations and compare the files byte for byte.
- CI on Windows (PowerShell 5.1), macOS and Linux, and on Python 3.8.
