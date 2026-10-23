# Lessons record summary

- Period: 2026-09 ~ 2026-10 (last 2 month(s), this month included)
- Files read: runs/2026-09.jsonl, runs/2026-10.jsonl
- Lines: role runs 5 · main-conversation turns 2 · harness changes 4 · skipped lines 7 (not JSON, or unknown kind)
- Record times: 2026-09-30T23:59:59-05:00 ~ 2026-10-10T10:00:00Z
- Current harness fingerprint: 006494ff (7 files)

## Project × role

The role is the `agent` name; the main conversation comes from turn lines. Token columns are `median / total`; the tools, turns and ms columns are medians. Unreadable values (`null`) are left out of the counts; a total too large for 64 bits is shown as `-`.

| Project | Role | Count | Model | effort | in | out | cache_read | cache_write | tools | turns | ms | Read failures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (project unknown) | main conversation | 1 | - | - | - | - | - | - | - | - | - | 0 |
| (project unknown) | (role name unknown) | 1 | - | - | 1 / 1 | - | - | 4 / 4 | - | -3 | 2 | 1 |
| alpha | main conversation | 1 | claude-opus-4-1-20250805 | medium | 60 / 60 | 6 / 6 | 600 / 600 | 30 / 30 | 0 | 1 | - | 1 |
| alpha | coder | 3 | claude-sonnet-4-5-20250929 | high | 100 / 401 | 10 / 41 | 1000 / 4001 | 50 / 201 | 4 | 3 | 1000 | 0 |
| we\|rd | doc-writer | 1 | - | - | 10 / 10 | 1 / 1 | 100 / 100 | 10 / 10 | 0 | 1 | 100 | 1 |

## Role × harness version

Runs grouped by role and the harness fingerprint written on each run (all projects together), oldest version of a role first. Tokens = in + out + cache_read + cache_write of one run; time = ms. A run with an unread value is left out of that column's n. Spread is min–max when n < 4 and p25–p75 when n ≥ 4. The runs are different tasks, so this is observation, not a controlled test. The fingerprint covers the whole setup: a change may come from a file other than the role's own (see Harness changes).

| Role | Harness | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread |
|---|---|---|---|---|---|---|---|---|---|
| main conversation | bbbb2222 | 1 | 2026-10-06 | 1 | 696 | min–max 696–696 | 0 | - | - |
| main conversation | (unknown) | 1 | 2026-10-10 | 0 | - | - | 0 | - | - |
| (role name unknown) | (unknown) | 1 | 2026-10-09 | 0 | - | - | 1 | 2 | min–max 2–2 |
| coder | aaaa1111 | 2 | 2026-09-30 – 2026-10-02 | 2 | 582 | min–max 4–1160 | 2 | 500.5 | min–max 1–1000 |
| coder | bbbb2222 | 1 | 2026-10-04 | 1 | 3480 | min–max 3480–3480 | 1 | 3000 | min–max 3000–3000 |
| doc-writer | aaaa1111 | 1 | 2026-10-08 | 1 | 121 | min–max 121–121 | 1 | 100 | min–max 100–100 |

### Version comparisons

For each role whose latest harness version differs from the previous one. A difference is printed as a finding only when both sides have n ≥ 5 and the spreads do not overlap; otherwise it is labelled noise / inconclusive and no difference is given.

- coder: aaaa1111 → bbbb2222 | runs 2 → 1 | tokens median 582 (n=2) → 3480 (n=1): noise / inconclusive (n < 5) | time (ms) median 500.5 (n=2) → 3000 (n=1): noise / inconclusive (n < 5) | applied by 2026-10-03 2026-10-03-1.md#1

## Role × model

Runs grouped by role and the model written on each run (all projects and harness versions together): the main conversation's model changes per session, so the harness fingerprint alone mixes models. Model ids that differ only in case are one row (shown in lower case). Columns as in the harness table: tokens = in + out + cache_read + cache_write of one run, time = ms; a run with an unread value is left out of that column's n; spread is min–max when n < 4 and p25–p75 when n ≥ 4. A run without a model is listed as `(model unknown)`. The runs are different tasks, so this is observation, not a controlled test.

The signal columns count the `events.md` events of that role × model (see Outcome signals for the signals). An event is joined to the runs of the same date + project + role (case does not matter; `main` is the main conversation) and counted under the model of those runs, whatever the harness version. When the runs it matches that day used more than one model, the model is not guessed: the event is counted in no row and shows in the `Ambiguous model` line under the table. An event with no run to match is not here either (it is counted under Outcome signals). `other signals` sums signal words with no column of its own. `repeated-failure` and `redone` with work type `experiment` are expected iterations and are left out; the other signals with that work type are counted. Events are self-reported, so the counts are a lower bound. `Cost n` is the number of runs the cost adds up (a run with any unread token value is left out), and the cost uses the prices and rules of the cost table below; `-` for a model with no known price or a token total that does not fit in 64 bits.

| Role | Model | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread | fix-request | review-block | review-wrong | repeated-failure | redone | other signals | Cost n | Approx. cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| main conversation | (model unknown) | 1 | 2026-10-10 | 0 | - | - | 0 | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - |
| main conversation | claude-opus-4-1-20250805 | 1 | 2026-10-06 | 1 | 696 | min–max 696–696 | 0 | - | - | 1 | 0 | 0 | 0 | 0 | 0 | 1 | - |
| (role name unknown) | (model unknown) | 1 | 2026-10-09 | 0 | - | - | 1 | 2 | min–max 2–2 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | - |
| coder | claude-sonnet-4-5-20250929 | 3 | 2026-09-30 – 2026-10-04 | 3 | 1160 | min–max 4–3480 | 3 | 1000 | min–max 1–3000 | 3 | 1 | 0 | 0 | 0 | 1 | 3 | - |
| doc-writer | (model unknown) | 1 | 2026-10-08 | 1 | 121 | min–max 121–121 | 1 | 100 | min–max 100–100 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | - |

- Ambiguous model: 0 event(s) matched runs of more than one model that day, so they are in no row above

### Approximate cost per model

Approximate: tokens × list price (USD per million tokens as of 2026-10-21), summed per model over all projects and roles; the cost column of the role × model table above splits the same sum by role. Cache writes are priced at the 5-minute rate because the 1-hour split is not recorded. Haiku 5.5 is priced at the rate for prompts up to 100K tokens, so its cost is a lower bound. A model id is matched by family and version (`claude-opus-5-5`, with or without a date or `[1m]` after it); an id with no known price shows `-`, never a guess, and so does a model with no run to count or a token total that does not fit in 64 bits. A run with any unread token value is left out of the cost and counted under `Left out`.

| Model | Priced as | List price per M tokens (in / out / cache write / cache read) | Runs | Left out | Approx. cost (USD) |
|---|---|---|---|---|---|
| (model unknown) | - | - | 3 | 2 | - |
| claude-opus-4-1-20250805 | - | - | 1 | 0 | - |
| claude-sonnet-4-5-20250929 | - | - | 3 | 0 | - |

## Outcome signals (events.md)

events.md is written by the orchestrator about its own work, so these counts are a lower bound, not everything that went wrong. Each event is joined by date + project + role (case does not matter; `main` is the main conversation) to the harness version of that role's runs that day. Per run = events of that signal / runs of that role under that version. A `repeated-failure` or `redone` event whose work type is `experiment` is an expected iteration, not a harness failure: it is left out of the counts and rates here and shown on a line of its own. The other signals (`fix-request` · `review-block` · `review-wrong`) with work type `experiment` are harness signals and are counted as usual.

| Role | Harness | Runs | Signal | Events | Per run |
|---|---|---|---|---|---|
| main conversation | bbbb2222 | 1 | fix-request | 1 | 1 |
| (role name unknown) | (unknown) | 1 | fix-request | 1 | 1 |
| coder | aaaa1111 | 2 | fix-request | 3 | 1.5 |
| coder | aaaa1111 | 2 | surprise | 1 | 0.5 |
| coder | bbbb2222 | 1 | review-block | 1 | 1 |
| doc-writer | aaaa1111 | 1 | redone | 1 | 1 |

- Events in the period: 8 · joined to a harness version 8 · no run of that role in that project that day 0 · harness changed that day, so not attributed 0
- Expected experiment iterations (`repeated-failure` · `redone` with work type `experiment`; not in the counts above): 0
- Lines starting with `- ` that are not in the format (`- YYYY-MM-DD | project | signal | work type · size | role | fact`): 3

## Read failures

- Lines with unread keys: 3 / 7 (role-run and turn lines whose `missing` is not empty)
- Unread keys: in 2 · model 1 · ms 1

## Harness changes

- 2026-10-03T09:12:00+09:00 | (first) → aaaa1111 | added a, b | plugin 0.1.0
- 2026-10-05T09:00:00+09:00 | aaaa1111 → bbbb2222 | changed plugin/agents/coder.md, z | added output-styles/x.md | removed gone.md | plugin 0.1.1
- (time unknown) | (first) → ? | plugin 0.2.0
- not a time | bbbb2222 → cccc3333
