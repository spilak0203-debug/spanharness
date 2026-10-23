# Changelog

## 0.1.0 - 2026-10-23

Initial release.

- 11 specialist subagents: architect, coder, reviewer, deep-reviewer, tester, experimenter, researcher, doc-writer, designer, modeler and harness-advisor.
- Orchestrator output style, opt-in: `/output-style spanharness:orchestrator`.
- `new-project` skill.
- Lessons recorder and `report` command, in Python (macOS, Linux) and PowerShell (Windows), both written to the specification in `docs/lessons-format.md`. Data goes to `~/.claude/lessons/`; `SPANHARNESS_RECORD=0` turns recording off.
- `lint` command that checks the repository against `tests/harness-rules.json`.
- Conformance tests that run the same cases through both implementations and compare the files byte for byte.
- CI on Windows (PowerShell 5.1), macOS and Linux, and on Python 3.8.
