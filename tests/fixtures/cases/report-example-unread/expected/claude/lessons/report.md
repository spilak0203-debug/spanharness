# Lessons record summary

- Period: 2026-10 ~ 2026-10 (last 1 month(s), this month included)
- Files read: runs/2026-10.jsonl
- Lines: role runs 6 · main-conversation turns 2 · harness changes 1 · skipped lines 0 (not JSON, or unknown kind)
- Record times: 2026-10-01T10:00:00+09:00 ~ 2026-10-09T10:00:00+09:00
- Current harness fingerprint: 006494ff (7 files)

## Project × role

The role is the `agent` name; the main conversation comes from turn lines. Token columns are `median / total`; the tools, turns and ms columns are medians. Unreadable values (`null`) are left out of the counts; a total too large for 64 bits is shown as `-`.

| Project | Role | Count | Model | effort | in | out | cache_read | cache_write | tools | turns | ms | Read failures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| alpha | main conversation | 2 | claude-sonnet-4-5-20250929 | high | 1 / 2 | 1 / 2 | 1 / 2 | 1 / 2 | 1 | 1 | 1 | 0 |
| alpha | coder | 6 | claude-sonnet-4-5-20250929 | high | 1 / 5 | 1 / 6 | 1 / 6 | 1 / 6 | 1 | 1 | 1 | 2 |

## Role × harness version

Runs grouped by role and the harness fingerprint written on each run (all projects together), oldest version of a role first. Tokens = in + out + cache_read + cache_write of one run; time = ms. A run with an unread value is left out of that column's n. Spread is min–max when n < 4 and p25–p75 when n ≥ 4. The runs are different tasks, so this is observation, not a controlled test. The fingerprint covers the whole setup: a change may come from a file other than the role's own (see Harness changes).

| Role | Harness | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread |
|---|---|---|---|---|---|---|---|---|---|
| main conversation | a1b2c3d4 | 2 | 2026-10-07 – 2026-10-08 | 2 | 4 | min–max 4–4 | 2 | 1 | min–max 1–1 |
| coder | a1b2c3d4 | 6 | 2026-10-01 – 2026-10-09 | 5 | 4 | p25–p75 4–4 | 5 | 1 | p25–p75 1–1 |

### Version comparisons

For each role whose latest harness version differs from the previous one. A difference is printed as a finding only when both sides have n ≥ 5 and the spreads do not overlap; otherwise it is labelled noise / inconclusive and no difference is given.

none: no role has two harness versions in this period.

## Role × model

Runs grouped by role and the model written on each run (all projects and harness versions together): the main conversation's model changes per session, so the harness fingerprint alone mixes models. Model ids that differ only in case are one row (shown in lower case). Columns as in the harness table: tokens = in + out + cache_read + cache_write of one run, time = ms; a run with an unread value is left out of that column's n; spread is min–max when n < 4 and p25–p75 when n ≥ 4. A run without a model is listed as `(model unknown)`. The runs are different tasks, so this is observation, not a controlled test.

The signal columns count the `events.md` events of that role × model (see Outcome signals for the signals). An event is joined to the runs of the same date + project + role (case does not matter; `main` is the main conversation) and counted under the model of those runs, whatever the harness version. When the runs it matches that day used more than one model, the model is not guessed: the event is counted in no row and shows in the `Ambiguous model` line under the table. An event with no run to match is not here either (it is counted under Outcome signals). `other signals` sums signal words with no column of its own. `repeated-failure` and `redone` with work type `experiment` are expected iterations and are left out; the other signals with that work type are counted. Events are self-reported, so the counts are a lower bound. `Cost n` is the number of runs the cost adds up (a run with any unread token value is left out), and the cost uses the prices and rules of the cost table below; `-` for a model with no known price or a token total that does not fit in 64 bits.

| Role | Model | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread | fix-request | review-block | review-wrong | repeated-failure | redone | other signals | Cost n | Approx. cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| main conversation | claude-sonnet-4-5-20250929 | 2 | 2026-10-07 – 2026-10-08 | 2 | 4 | min–max 4–4 | 2 | 1 | min–max 1–1 | - | - | - | - | - | - | 2 | - |
| coder | claude-sonnet-4-5-20250929 | 6 | 2026-10-01 – 2026-10-09 | 5 | 4 | p25–p75 4–4 | 5 | 1 | p25–p75 1–1 | - | - | - | - | - | - | 5 | - |

- Signal columns show `-`: events.md not found: no outcome signals.

### Approximate cost per model

Approximate: tokens × list price (USD per million tokens as of 2026-10-21), summed per model over all projects and roles; the cost column of the role × model table above splits the same sum by role. Cache writes are priced at the 5-minute rate because the 1-hour split is not recorded. Haiku 5.5 is priced at the rate for prompts up to 100K tokens, so its cost is a lower bound. A model id is matched by family and version (`claude-opus-5-5`, with or without a date or `[1m]` after it); an id with no known price shows `-`, never a guess, and so does a model with no run to count or a token total that does not fit in 64 bits. A run with any unread token value is left out of the cost and counted under `Left out`.

| Model | Priced as | List price per M tokens (in / out / cache write / cache read) | Runs | Left out | Approx. cost (USD) |
|---|---|---|---|---|---|
| claude-sonnet-4-5-20250929 | - | - | 8 | 1 | - |

## Outcome signals (events.md)

events.md not found: no outcome signals.

## Read failures

- Lines with unread keys: 2 / 8 (role-run and turn lines whose `missing` is not empty)
- Unread keys: in 1 · model 1 · ms 1

## Harness changes

- 2026-10-03T09:00:00+09:00 | a1b2c3d4 → e5f6a7b8 | changed agents/coder.md | added output-styles/x.md | plugin 0.1.1
