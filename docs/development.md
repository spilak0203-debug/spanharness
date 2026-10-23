# Development

## Local install for development

Load the working tree directly for one session:

```
claude --plugin-dir .
```

Or register a clone as a directory marketplace. The plugin is then loaded in place from the clone:

```
claude plugin marketplace add <clone>
claude plugin install spanharness@spanharness
```

## Apply mode setup

The harness advisor applies changes to a local clone registered as a directory marketplace. Set it up once:

```
git clone https://github.com/spilak0203-debug/spanharness ~/src/spanharness
claude plugin marketplace remove spanharness     # if the GitHub marketplace was added
claude plugin marketplace add ~/src/spanharness
claude plugin install spanharness@spanharness
```

Lessons data is kept outside the plugin data, so nothing is lost by switching. Update later with `git pull` in the clone.

## Validate

```
claude plugin validate . --strict
```

This does not check agent frontmatter values, so `lint` is the real check.

## Tests

```
python3 tests/run_tests.py                 # Python implementation, plus PowerShell when it is found
python3 tests/run_tests.py --impl py       # Python only
python3 tests/run_tests.py --impl ps1      # PowerShell only
python3 tests/run_tests.py --impl both     # both
python3 tests/run_tests.py -v -k report    # verbose, only tests whose name contains "report"
python3 tests/run_tests.py --bless         # rewrite the expected files from the Python implementation
```

Only the standard library is used (Python 3.8 or newer). PowerShell is `powershell.exe` on Windows, otherwise `pwsh` on PATH; set `SPANHARNESS_PWSH` to use another executable. A missing runtime is skipped on a local run and is a failure when `CI=true`. On a host that is not Windows the PowerShell recorder does nothing by design, so the runner runs a temporary copy of `scripts/spanharness.ps1` with that one guard line blanked; it fails loudly if the line is not found exactly once.

| File | What it checks |
|---|---|
| `tests/test_conformance.py` | Every case in `tests/fixtures/cases/` through each selected implementation; the files written must match `expected/` byte for byte. |
| `tests/test_record.py` | Unit tests of `record` (Python): transcript summary, project name, harness fingerprint, record flows, locking. |
| `tests/test_robust.py` | Through each implementation: records at the same moment (none lost, none counted twice), the redo and the 4th try of step 12 and the clock of step 13 (the test-only gate of spec 3.9 holds a record after its summary while the test moves the read position), a transcript that is a pipe, a device or a folder, `errors.log` without paths or ids, bad arguments on stderr, and that the JSON reader of Windows PowerShell 5.1 accepts exactly what Python accepts (the strict reader runs on every host; on Windows it is also the one in use). |
| `tests/test_report.py` | Unit tests of `report` (Python): number formats, tables, cost, events join, command line, and that the spec examples appear in the fixtures. |
| `tests/test_harness.py` | `lint` of each implementation on the repository (must pass), on the small trees in `tests/fixtures/lint/` and on copies of the repository with one change each (must fail with the expected rule ids); `claude plugin validate . --strict` when `claude` is on PATH. |

`tests/bench_record.py` is not a test: `python3 tests/bench_record.py --impl py|ps1` times the first `record` on synthetic transcripts of 1, 4 and 16 MB (kinds agent and turn) and prints one table. The `test` job of the CI runs it with `--impl ps1` on Windows, after the tests, so the log shows the timings of Windows PowerShell 5.1.

`docs/lessons-format.md` is the specification; the cases are the contract that both implementations must meet.

### Conformance cases

A case is a folder `tests/fixtures/cases/<name>/`:

- `args.txt`: one invocation per line, as the arguments after the script name; a prefix `[N] ` is the expected exit code (default 0); a suffix ` < file` names the file fed to stdin (for `record` the default is `hook-input.json`). `{ROOT}` is the sandbox folder and `{PLUGIN}` is `tests/fixtures/plugin`.
- `input/`: copied to a fresh sandbox. A folder named `_git` becomes `.git`. `{ROOT}` inside a file is replaced by the sandbox path.
- `expected/`: every file the run created or changed, byte for byte (the sandbox path appears as `{ROOT}`; `errors.log` is reduced to the fixed message of each line). No `expected/` folder means nothing may change.
- Optional: `env.txt` (`NAME=value` lines), `touch.txt` (file times), `generate.txt` (files too large to commit, made at test time), `stdout.txt`, `deleted.txt`.

The expected files are written by `--bless` and then read against the specification line by line; review the diff of `expected/` before committing it. The small trees in `tests/fixtures/lint/<case>/` hold their own `tests/harness-rules.json`: a rule whose id ends in `.bad` must fail and one ending in `.ok` must pass.

## Release

1. Bump `version` in `.claude-plugin/plugin.json` and add the entry to `CHANGELOG.md`.
2. Commit, then tag `vX.Y.Z` and push the tag.
