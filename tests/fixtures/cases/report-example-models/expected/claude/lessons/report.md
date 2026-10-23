# Lessons record summary

- Period: 2026-10 ~ 2026-10 (last 1 month(s), this month included)
- Files read: runs/2026-10.jsonl
- Lines: role runs 8 · main-conversation turns 1 · harness changes 0 · skipped lines 0 (not JSON, or unknown kind)
- Record times: 2026-10-02T10:00:00+09:00 ~ 2026-10-09T10:00:00+09:00
- Current harness fingerprint: 006494ff (7 files)

## Project × role

The role is the `agent` name; the main conversation comes from turn lines. Token columns are `median / total`; the tools, turns and ms columns are medians. Unreadable values (`null`) are left out of the counts; a total too large for 64 bits is shown as `-`.

| Project | Role | Count | Model | effort | in | out | cache_read | cache_write | tools | turns | ms | Read failures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| alpha | main conversation | 1 | claude-opus-5-5 | high | 1000000 / 1000000 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 100 | 0 |
| alpha | coder | 6 | claude-opus-5-5, claude-sonnet-5-5 | high | 1000000 / 5000000 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 100 | 1 |
| alpha | reviewer | 1 | claude-mystery-9-9 | high | 1000000 / 1000000 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 100 | 0 |
| beta | coder | 1 | claude-opus-5-5 | high | 1000000 / 1000000 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 100 | 0 |

## Role × harness version

Runs grouped by role and the harness fingerprint written on each run (all projects together), oldest version of a role first. Tokens = in + out + cache_read + cache_write of one run; time = ms. A run with an unread value is left out of that column's n. Spread is min–max when n < 4 and p25–p75 when n ≥ 4. The runs are different tasks, so this is observation, not a controlled test. The fingerprint covers the whole setup: a change may come from a file other than the role's own (see Harness changes).

| Role | Harness | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread |
|---|---|---|---|---|---|---|---|---|---|
| main conversation | a1b2c3d4 | 1 | 2026-10-07 | 1 | 1000000 | min–max 1000000–1000000 | 1 | 100 | min–max 100–100 |
| coder | a1b2c3d4 | 7 | 2026-10-02 – 2026-10-09 | 6 | 1000000 | p25–p75 1000000–1000000 | 7 | 100 | p25–p75 100–100 |
| reviewer | a1b2c3d4 | 1 | 2026-10-08 | 1 | 1000000 | min–max 1000000–1000000 | 1 | 100 | min–max 100–100 |

### Version comparisons

For each role whose latest harness version differs from the previous one. A difference is printed as a finding only when both sides have n ≥ 5 and the spreads do not overlap; otherwise it is labelled noise / inconclusive and no difference is given.

none: no role has two harness versions in this period.

## Role × model

Runs grouped by role and the model written on each run (all projects and harness versions together): the main conversation's model changes per session, so the harness fingerprint alone mixes models. Model ids that differ only in case are one row (shown in lower case). Columns as in the harness table: tokens = in + out + cache_read + cache_write of one run, time = ms; a run with an unread value is left out of that column's n; spread is min–max when n < 4 and p25–p75 when n ≥ 4. A run without a model is listed as `(model unknown)`. The runs are different tasks, so this is observation, not a controlled test.

The signal columns count the `events.md` events of that role × model (see Outcome signals for the signals). An event is joined to the runs of the same date + project + role (case does not matter; `main` is the main conversation) and counted under the model of those runs, whatever the harness version. When the runs it matches that day used more than one model, the model is not guessed: the event is counted in no row and shows in the `Ambiguous model` line under the table. An event with no run to match is not here either (it is counted under Outcome signals). `other signals` sums signal words with no column of its own. `repeated-failure` and `redone` with work type `experiment` are expected iterations and are left out; the other signals with that work type are counted. Events are self-reported, so the counts are a lower bound. `Cost n` is the number of runs the cost adds up (a run with any unread token value is left out), and the cost uses the prices and rules of the cost table below; `-` for a model with no known price or a token total that does not fit in 64 bits.

| Role | Model | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread | fix-request | review-block | review-wrong | repeated-failure | redone | other signals | Cost n | Approx. cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| main conversation | claude-opus-5-5 | 1 | 2026-10-07 | 1 | 1000000 | min–max 1000000–1000000 | 1 | 100 | min–max 100–100 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | $4.00 |
| coder | claude-opus-5-5 | 4 | 2026-10-02 – 2026-10-06 | 4 | 1000000 | p25–p75 1000000–1000000 | 4 | 100 | p25–p75 100–100 | 2 | 1 | 1 | 0 | 0 | 1 | 4 | $16.00 |
| coder | claude-sonnet-5-5 | 3 | 2026-10-03 – 2026-10-09 | 2 | 1000000 | min–max 1000000–1000000 | 3 | 100 | min–max 100–100 | 1 | 0 | 0 | 0 | 0 | 0 | 2 | $4.00 |
| reviewer | claude-mystery-9-9 | 1 | 2026-10-08 | 1 | 1000000 | min–max 1000000–1000000 | 1 | 100 | min–max 100–100 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | - |

- Ambiguous model: 2 event(s) matched runs of more than one model that day, so they are in no row above (fix-request 1 · redone 1)

### Approximate cost per model

Approximate: tokens × list price (USD per million tokens as of 2026-10-21), summed per model over all projects and roles; the cost column of the role × model table above splits the same sum by role. Cache writes are priced at the 5-minute rate because the 1-hour split is not recorded. Haiku 5.5 is priced at the rate for prompts up to 100K tokens, so its cost is a lower bound. A model id is matched by family and version (`claude-opus-5-5`, with or without a date or `[1m]` after it); an id with no known price shows `-`, never a guess, and so does a model with no run to count or a token total that does not fit in 64 bits. A run with any unread token value is left out of the cost and counted under `Left out`.

| Model | Priced as | List price per M tokens (in / out / cache write / cache read) | Runs | Left out | Approx. cost (USD) |
|---|---|---|---|---|---|
| claude-mystery-9-9 | - | - | 1 | 0 | - |
| claude-opus-5-5 | Opus 5.5 | 4 / 20 / 5 / 0.2 | 5 | 0 | $20.00 |
| claude-sonnet-5-5 | Sonnet 5.5 | 2 / 10 / 2.5 / 0.1 | 3 | 1 | $4.00 |

## Outcome signals (events.md)

events.md is written by the orchestrator about its own work, so these counts are a lower bound, not everything that went wrong. Each event is joined by date + project + role (case does not matter; `main` is the main conversation) to the harness version of that role's runs that day. Per run = events of that signal / runs of that role under that version. A `repeated-failure` or `redone` event whose work type is `experiment` is an expected iteration, not a harness failure: it is left out of the counts and rates here and shown on a line of its own. The other signals (`fix-request` · `review-block` · `review-wrong`) with work type `experiment` are harness signals and are counted as usual.

| Role | Harness | Runs | Signal | Events | Per run |
|---|---|---|---|---|---|
| main conversation | a1b2c3d4 | 1 | fix-request | 1 | 1 |
| coder | a1b2c3d4 | 7 | fix-request | 4 | 0.57 |
| coder | a1b2c3d4 | 7 | redone | 1 | 0.14 |
| coder | a1b2c3d4 | 7 | review-block | 1 | 0.14 |
| coder | a1b2c3d4 | 7 | review-wrong | 1 | 0.14 |
| coder | a1b2c3d4 | 7 | surprise | 1 | 0.14 |
| reviewer | a1b2c3d4 | 1 | repeated-failure | 1 | 1 |

- Events in the period: 11 · joined to a harness version 10 · no run of that role in that project that day 1 · harness changed that day, so not attributed 0
- Expected experiment iterations (`repeated-failure` · `redone` with work type `experiment`; not in the counts above): 1
- Lines starting with `- ` that are not in the format (`- YYYY-MM-DD | project | signal | work type · size | role | fact`): 1

## Read failures

- Lines with unread keys: 1 / 9 (role-run and turn lines whose `missing` is not empty)
- Unread keys: in 1

## Harness changes

none
