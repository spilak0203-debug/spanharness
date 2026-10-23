# spanharness

spanharness is a Claude Code plugin with three parts:

- An **orchestrator output style** that splits work and hands it to 11 specialist subagents, then checks and merges what they return.
- A **lessons log** that records every subagent run and every main-conversation turn: tokens, cost inputs, duration and a fingerprint of the harness (the roles, the style and the skills in use).
- A **harness advisor** that reads the log and proposes improvements to the roles, the style and the instructions, with evidence.

## Install

```
/plugin marketplace add spilak0203-debug/spanharness
/plugin install spanharness@spanharness
```

Requirements for the lessons log (the style and the agents need nothing extra):

- Windows: Windows PowerShell 5.1, which is built in.
- macOS and Linux: Python 3.8 or newer.
- macOS without the Command Line Tools: recording is silently off, and the `report` command prints a hint.

## Turn on the orchestrator style

```
/output-style spanharness:orchestrator
```

Use the full name. The bare name `orchestrator` does not select it.

The style is opt-in: installing the plugin does not change your main conversation. The choice is saved per project in `.claude/settings.local.json`. After you edit the style text, a new session picks up the change.

The style recommends opus with effort high or above for the main conversation. It does the small jobs itself (questions, one- or two-file fixes, running tests) and hands the larger ones to the roles below.

## Roles

Each role is a subagent named `spanharness:<name>`. The orchestrator picks the role; you can also ask for one by name.

| Role | Model · effort | Purpose |
|---|---|---|
| `spanharness:architect` | opus · xhigh | Large designs, changes spanning 3 or more modules, structural refactors, and bugs whose cause is unknown (before the fix). |
| `spanharness:coder` | sonnet · high | Implementation or bug fixes with a defined scope. |
| `spanharness:reviewer` | opus · high | Routine review of a change of more than 2 files or 50 changed lines. Finds what will break, missing tests and risky changes; fixes nothing. |
| `spanharness:deep-reviewer` | fable · xhigh | Review of changes of 5 or more files or 300 or more changed lines, and anything touching money, orders, security, personal data or irreversible data changes. Gives the fit-to-ship judgment; fixes nothing. |
| `spanharness:tester` | sonnet · high | Writes and runs tests to confirm the code works (pass or fail), and lists candidate causes on failure. |
| `spanharness:experimenter` | opus · high | Finds out by numbers whether a candidate beats a baseline: frozen setup, repeated runs, mean ± SEM, a verdict. Logs every attempt in `docs/experiments.md`. |
| `spanharness:researcher` | sonnet · medium | Researches a question across several sources, checks each key claim against two independent sources, and writes findings to `docs/research.md`. |
| `spanharness:doc-writer` | sonnet · high | Writes or fixes README files, user guides, changelogs and comments. Does not modify code. |
| `spanharness:designer` | opus · high | Creative work: names, wording, screens and usage flows, concepts. Produces several options and recommends one. |
| `spanharness:modeler` | opus · medium | 3D shapes, materials and lighting. Makes model code and preview images, and checks collisions, thickness and manufacturability by calculation. |
| `spanharness:harness-advisor` | opus · high | Proposes harness improvements from the lessons, or plans an A/B comparison. Runs only when you ask (see [Harness advisor](#harness-advisor)). |

The plugin also ships one skill, `spanharness:new-project`, which settles requirements by asking questions before any code or design when you start a new project in an empty folder.

### If `fable` is not available to you

`deep-reviewer` runs on the `fable` model. If your account cannot use it, ask the orchestrator to call it with `model: opus` for that run. To change it for good, edit `model:` in `agents/deep-reviewer.md` of a local clone (see [Development](#development)). The repository's own `lint` pins `fable`, so a clone edited this way fails `lint` until the rule `agent.deep-reviewer.frontmatter` in `tests/harness-rules.json` is changed too.

## Optional skills

Both are used only if you already have them. Nothing breaks without them.

- `ponytail`: `coder` lists it as a preloaded skill. Preloading works when `ponytail` is installed as a user skill, in `~/.claude/skills/ponytail/`. If it is missing, `coder` starts normally without it. This README does not say where to get `ponytail`; use it if you have it.
- `frontend-design`: `designer` reads its `SKILL.md` for screen and visual UI work, if it finds one at `~/.claude/skills/frontend-design/SKILL.md` or under `~/.claude/plugins/`. Without it, `designer` goes on without it. Use it if you have it.

## Context windows

Every agent ships with an `autoCompactWindow` of 300000 tokens (`coder`: 500000). That is the size at which that agent's conversation is compacted.

A plugin cannot set the window of your main conversation. Set it yourself, in one of three ways:

- Run `/autocompact <tokens>`. It saves `modelSettings.<model>.autoCompactWindow` in `~/.claude/settings.json`.
- Add a top-level `"autoCompactWindow": 300000` to `~/.claude/settings.json` to apply it to all models.
- Set the environment variable `CLAUDE_CODE_AUTO_COMPACT_WINDOW`. It has the highest precedence and blocks `/autocompact`.

The value is from 100000 to 1000000, or `"auto"`.

## Lessons and privacy

**Where.** `~/.claude/lessons/`, or `$CLAUDE_CONFIG_DIR/lessons` when `CLAUDE_CONFIG_DIR` is set. It sits outside the plugin's own data folder on purpose, so reinstalling or switching the install source keeps your history.

**What is recorded.** For each subagent run and each main-conversation turn, one line in `runs/YYYY-MM.jsonl` with:

- token counts (input, output, cache read, cache write), tool count, turn count and duration;
- the model and effort, and the role's configured model and effort;
- the harness fingerprint (8 hex characters);
- the project folder name, the working directory (`cwd`), the session id and the agent id.

**What is not recorded.** No prompt, no answer and no transcript text. The only text taken from a transcript is the model id. Nothing is sent over the network.

**Read positions.** To count only what is new, the hook keeps one small file per session and per agent in `state/`, with the transcript path and how far it has been read. These files are deleted after 30 days without change.

**One more file has text.** `events.md` is written by the orchestrator, not by the hook. When something notable happens (a fix request, a blocked review, a repeated failure), it appends one line: date, project, signal, work type, role and a one-line fact. Open it if you want to see exactly what it says.

The full file layout and line formats are in [docs/lessons-format.md](docs/lessons-format.md).

**How it records.** One synchronous hook runs on `SubagentStop` and on `Stop`. On Linux and macOS the whole hook takes under 100 ms; on Windows about 1.5 s, most of it the start of PowerShell, plus about 0.7 s per MB of a subagent's transcript (a main-conversation turn reads only from its last prompt, so its time does not grow with the session). A failure never blocks you: `record` always exits 0 and logs the reason to `errors.log` in the lessons folder.

**Opt out.** Set `SPANHARNESS_RECORD=0`. Nothing is read or written while it is set. To set it for every session, put it in `~/.claude/settings.json`:

```json
{
  "env": { "SPANHARNESS_RECORD": "0" }
}
```

**Delete.** Remove the folder `~/.claude/lessons/`.

**Read the summary.** Run `report` and open `~/.claude/lessons/report.md`. It covers the last 2 months by default; `--months N` takes 1 to 120.

```
sh "<plugin root>/scripts/spanharness.sh" report
```

On Windows:

```
powershell -NoProfile -ExecutionPolicy Bypass -File "<plugin root>/scripts/spanharness.ps1" report
```

`<plugin root>` is the folder of the installed plugin; for a local clone, it is the clone. The advisor runs this for you.

**Permission prompts.** The orchestrator appends to `events.md` and the advisor writes proposals, both inside the lessons folder. To avoid a prompt each time, allow edits there in `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": ["Edit(~/.claude/lessons/**)"]
  }
}
```

## Harness advisor

The orchestrator calls `spanharness:harness-advisor` only when you say one of: "advisor", "harness improvement", "let's look at the lessons" or "A/B". It never runs on its own.

The advisor reads the report, then writes numbered proposals with evidence to `~/.claude/lessons/proposals/`. A difference the report labels "noise / inconclusive" is not treated as evidence. It changes a file only after you approve a numbered item, one item at a time. An A/B request produces a plan and, after your go-ahead, a blind comparison of a role against a variant of it.

Applying a change needs the plugin loaded from a git clone, not from the marketplace cache. The setup is short and is in [docs/development.md](docs/development.md#apply-mode-setup). Without it, the advisor returns these setup steps when you ask it to apply.

Applied changes are left uncommitted in the clone. After one, run `/reload-plugins`, or start a new session if the output style changed.

## Uninstall

```
/plugin uninstall spanharness@spanharness
/plugin marketplace remove spanharness
```

Then pick another style with `/output-style`, in each project where you turned this one on. The lessons data stays in `~/.claude/lessons/` until you delete the folder.

## Development

Local install, apply-mode setup, validation, tests and release steps are in [docs/development.md](docs/development.md). To check a clone:

```
python3 scripts/spanharness.py lint --root .
python3 tests/run_tests.py
```

## License

MIT. See [LICENSE](LICENSE).
