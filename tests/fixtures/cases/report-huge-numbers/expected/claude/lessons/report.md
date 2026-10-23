# Lessons record summary

- Period: 2026-10 ~ 2026-10 (last 1 month(s), this month included)
- Files read: runs/2026-10.jsonl
- Lines: role runs 11 · main-conversation turns 0 · harness changes 0 · skipped lines 0 (not JSON, or unknown kind)
- Record times: 2026-10-02T10:00:00+09:00 ~ 2026-10-07T10:00:00+09:00
- Current harness fingerprint: 006494ff (7 files)

## Project × role

The role is the `agent` name; the main conversation comes from turn lines. Token columns are `median / total`; the tools, turns and ms columns are medians. Unreadable values (`null`) are left out of the counts; a total too large for 64 bits is shown as `-`.

| Project | Role | Count | Model | effort | in | out | cache_read | cache_write | tools | turns | ms | Read failures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| alpha | coder | 3 | claude-sonnet-4-5-20250929 | high | 300 / 3000000000000000400 | 30 / 3000000000000000040 | 3000 / 3000000000000004000 | 150 / 3000000000000000200 | 5 | 4 | 2000 | 0 |
| beta | coder | 2 | claude-sonnet-4-5-20250929 | high | 5000000000000000000 / - | 20 / 40 | 2000 / 4000 | 100 / 200 | 6 | 4 | 2000 | 0 |
| delta | coder | 2 | claude-sonnet-4-5-20250929 | high | 5 / 5 | 12.5 / 25 | 5 / 5 | 52.5 / 105 | 5 | 4.5 | 1002.5 | 0 |
| gamma | coder | 4 | claude-haiku-5-5, claude-opus-5-5, claude-sonnet-5-5 | high | 4000000000000000000 / - | 20 / 3000000000000000040 | 2000 / 3000000000000004000 | 100 / 3000000000000000200 | 4.5 | 3.5 | 1500 | 0 |

## Role × harness version

Runs grouped by role and the harness fingerprint written on each run (all projects together), oldest version of a role first. Tokens = in + out + cache_read + cache_write of one run; time = ms. A run with an unread value is left out of that column's n. Spread is min–max when n < 4 and p25–p75 when n ≥ 4. The runs are different tasks, so this is observation, not a controlled test. The fingerprint covers the whole setup: a change may come from a file other than the role's own (see Harness changes).

| Role | Harness | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread |
|---|---|---|---|---|---|---|---|---|---|
| coder | a1b2c3d4 | 11 | 2026-10-02 – 2026-10-07 | 8 | 2500000000000500530 | p25–p75 2900–5000000000000001590 | 11 | 2000 | p25–p75 1000–2500 |

### Version comparisons

For each role whose latest harness version differs from the previous one. A difference is printed as a finding only when both sides have n ≥ 5 and the spreads do not overlap; otherwise it is labelled noise / inconclusive and no difference is given.

none: no role has two harness versions in this period.

## Role × model

Runs grouped by role and the model written on each run (all projects and harness versions together): the main conversation's model changes per session, so the harness fingerprint alone mixes models. Model ids that differ only in case are one row (shown in lower case). Columns as in the harness table: tokens = in + out + cache_read + cache_write of one run, time = ms; a run with an unread value is left out of that column's n; spread is min–max when n < 4 and p25–p75 when n ≥ 4. A run without a model is listed as `(model unknown)`. The runs are different tasks, so this is observation, not a controlled test.

The signal columns count the `events.md` events of that role × model (see Outcome signals for the signals). An event is joined to the runs of the same date + project + role (case does not matter; `main` is the main conversation) and counted under the model of those runs, whatever the harness version. When the runs it matches that day used more than one model, the model is not guessed: the event is counted in no row and shows in the `Ambiguous model` line under the table. An event with no run to match is not here either (it is counted under Outcome signals). `other signals` sums signal words with no column of its own. `repeated-failure` and `redone` with work type `experiment` are expected iterations and are left out; the other signals with that work type are counted. Events are self-reported, so the counts are a lower bound. `Cost n` is the number of runs the cost adds up (a run with any unread token value is left out), and the cost uses the prices and rules of the cost table below; `-` for a model with no known price or a token total that does not fit in 64 bits.

| Role | Model | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread | fix-request | review-block | review-wrong | repeated-failure | redone | other signals | Cost n | Approx. cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| coder | claude-haiku-5-5 | 1 | 2026-10-04 | 0 | - | - | 1 | 2000 | min–max 2000–2000 | - | - | - | - | - | - | 1 | $2205000000000.00 |
| coder | claude-opus-5-5 | 1 | 2026-10-05 | 1 | 1000000 | min–max 1000000–1000000 | 1 | 100 | min–max 100–100 | - | - | - | - | - | - | 1 | $4.00 |
| coder | claude-sonnet-4-5-20250929 | 7 | 2026-10-02 – 2026-10-07 | 5 | 3480 | p25–p75 1160–5000000000000001060 | 7 | 2000 | p25–p75 1000–2500 | - | - | - | - | - | - | 6 | - |
| coder | claude-sonnet-5-5 | 2 | 2026-10-02 – 2026-10-03 | 2 | 5000000000000002120 | min–max 5000000000000001060–5000000000000003180 | 2 | 2000 | min–max 1000–3000 | - | - | - | - | - | - | 2 | - |

- Signal columns show `-`: events.md not found: no outcome signals.

### Approximate cost per model

Approximate: tokens × list price (USD per million tokens as of 2026-10-21), summed per model over all projects and roles; the cost column of the role × model table above splits the same sum by role. Cache writes are priced at the 5-minute rate because the 1-hour split is not recorded. Haiku 5.5 is priced at the rate for prompts up to 100K tokens, so its cost is a lower bound. A model id is matched by family and version (`claude-opus-5-5`, with or without a date or `[1m]` after it); an id with no known price shows `-`, never a guess, and so does a model with no run to count or a token total that does not fit in 64 bits. A run with any unread token value is left out of the cost and counted under `Left out`.

| Model | Priced as | List price per M tokens (in / out / cache write / cache read) | Runs | Left out | Approx. cost (USD) |
|---|---|---|---|---|---|
| claude-haiku-5-5 | Haiku 5.5 | 0.1 / 0.5 / 0.125 / 0.01 | 1 | 0 | $2205000000000.00 |
| claude-opus-5-5 | Opus 5.5 | 4 / 20 / 5 / 0.2 | 1 | 0 | $4.00 |
| claude-sonnet-4-5-20250929 | - | - | 7 | 1 | - |
| claude-sonnet-5-5 | Sonnet 5.5 | 2 / 10 / 2.5 / 0.1 | 2 | 0 | - |

## Outcome signals (events.md)

events.md not found: no outcome signals.

## Read failures

- Lines with unread keys: 0 / 11 (role-run and turn lines whose `missing` is not empty)
- Unread keys: none

## Harness changes

none
