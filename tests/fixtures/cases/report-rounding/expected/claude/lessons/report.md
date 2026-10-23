# Lessons record summary

- Period: 2025-11 ~ 2026-10 (last 12 month(s), this month included)
- Files read: runs/2026-03.jsonl, runs/2026-04.jsonl, runs/2026-05.jsonl, runs/2026-06.jsonl, runs/2026-07.jsonl, runs/2026-08.jsonl, runs/2026-09.jsonl, runs/2026-10.jsonl
- Lines: role runs 286 · main-conversation turns 0 · harness changes 0 · skipped lines 0 (not JSON, or unknown kind)
- Record times: 2026-03-01T10:00:00+09:00 ~ 2026-10-20T10:00:00+09:00
- Current harness fingerprint: 006494ff (7 files)

## Project × role

The role is the `agent` name; the main conversation comes from turn lines. Token columns are `median / total`; the tools, turns and ms columns are medians. Unreadable values (`null`) are left out of the counts; a total too large for 64 bits is shown as `-`.

| Project | Role | Count | Model | effort | in | out | cache_read | cache_write | tools | turns | ms | Read failures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| alpha | r-cache | 1 | claude-sonnet-5-5 | high | 0 / 0 | 0 / 0 | 0 / 0 | 58000 / 58000 | 1 | 1 | 1 | 0 |
| alpha | r-fable | 1 | claude-fable-5-1 | high | 2500 / 2500 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 1 | 0 |
| alpha | r-haiku | 1 | claude-haiku-5-5 | high | 50000 / 50000 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 1 | 0 |
| alpha | r-haiku45 | 1 | claude-haiku-4-5-20251001 | high | 12500 / 12500 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 1 | 0 |
| alpha | r-opus | 1 | claude-opus-5-5 | high | 3750 / 3750 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 1 | 0 |
| alpha | r-sonnet | 1 | claude-sonnet-5-5 | high | 72500 / 72500 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 1 | 0 |
| alpha | r-zero | 1 | claude-opus-5-5 | high | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 1 | 0 |
| alpha | t16 | 16 | claude-sonnet-5-5 | high | 1 / 16 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 1 | 0 |
| alpha | t20 | 20 | claude-sonnet-5-5 | high | 1 / 20 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 1 | 0 |
| alpha | t200 | 200 | claude-sonnet-5-5 | high | 1 / 200 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 1 | 0 |
| alpha | t3 | 3 | claude-sonnet-5-5 | high | 1 / 3 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 1 | 0 |
| alpha | t8 | 8 | claude-sonnet-5-5 | high | 1 / 8 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 1 | 0 |
| beta | dec | 12 | claude-opus-5-5 | high | 58.5 / 702 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 552.5 | 0 |
| beta | q4 | 4 | claude-opus-5-5 | high | 2.5 / 10 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 25 | 0 |
| beta | q6 | 6 | claude-opus-5-5 | high | 2.5 / 15 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 17.5 | 0 |
| beta | same | 10 | claude-opus-5-5 | high | 152 / 1520 | 0 / 0 | 0 / 0 | 0 / 0 | 1 | 1 | 1 | 0 |

## Role × harness version

Runs grouped by role and the harness fingerprint written on each run (all projects together), oldest version of a role first. Tokens = in + out + cache_read + cache_write of one run; time = ms. A run with an unread value is left out of that column's n. Spread is min–max when n < 4 and p25–p75 when n ≥ 4. The runs are different tasks, so this is observation, not a controlled test. The fingerprint covers the whole setup: a change may come from a file other than the role's own (see Harness changes).

| Role | Harness | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread |
|---|---|---|---|---|---|---|---|---|---|
| dec | aaaa1111 | 6 | 2026-10-01 – 2026-10-06 | 6 | 104.5 | p25–p75 103.3–105.8 | 6 | 1002.5 | p25–p75 1001.3–1003.8 |
| dec | bbbb2222 | 6 | 2026-10-10 – 2026-10-15 | 6 | 12.5 | p25–p75 11.3–13.8 | 6 | 102.5 | p25–p75 101.3–103.8 |
| q4 | h000aaaa | 4 | 2026-10-01 – 2026-10-04 | 4 | 2.5 | p25–p75 1.8–3.3 | 4 | 25 | p25–p75 17.5–32.8 |
| q6 | h000aaaa | 6 | 2026-10-01 – 2026-10-06 | 6 | 2.5 | p25–p75 1.3–3.8 | 6 | 17.5 | p25–p75 8.8–26.3 |
| r-cache | h000aaaa | 1 | 2026-10-07 | 1 | 58000 | min–max 58000–58000 | 1 | 1 | min–max 1–1 |
| r-fable | h000aaaa | 1 | 2026-10-05 | 1 | 2500 | min–max 2500–2500 | 1 | 1 | min–max 1–1 |
| r-haiku | h000aaaa | 1 | 2026-10-03 | 1 | 50000 | min–max 50000–50000 | 1 | 1 | min–max 1–1 |
| r-haiku45 | h000aaaa | 1 | 2026-10-04 | 1 | 12500 | min–max 12500–12500 | 1 | 1 | min–max 1–1 |
| r-opus | h000aaaa | 1 | 2026-10-02 | 1 | 3750 | min–max 3750–3750 | 1 | 1 | min–max 1–1 |
| r-sonnet | h000aaaa | 1 | 2026-10-01 | 1 | 72500 | min–max 72500–72500 | 1 | 1 | min–max 1–1 |
| r-zero | h000aaaa | 1 | 2026-10-06 | 1 | 0 | min–max 0–0 | 1 | 1 | min–max 1–1 |
| same | aaaa1111 | 5 | 2026-10-01 – 2026-10-05 | 5 | 102 | p25–p75 101–103 | 5 | 1 | p25–p75 1–1 |
| same | bbbb2222 | 5 | 2026-10-06 – 2026-10-10 | 5 | 202 | p25–p75 201–203 | 5 | 1 | p25–p75 1–1 |
| t16 | h000aaaa | 16 | 2026-10-01 – 2026-10-16 | 16 | 1 | p25–p75 1–1 | 16 | 1 | p25–p75 1–1 |
| t20 | h000aaaa | 20 | 2026-10-01 – 2026-10-20 | 20 | 1 | p25–p75 1–1 | 20 | 1 | p25–p75 1–1 |
| t200 | h000aaaa | 200 | 2026-03-01 – 2026-10-04 | 200 | 1 | p25–p75 1–1 | 200 | 1 | p25–p75 1–1 |
| t3 | h000aaaa | 3 | 2026-10-01 – 2026-10-03 | 3 | 1 | min–max 1–1 | 3 | 1 | min–max 1–1 |
| t8 | h000aaaa | 8 | 2026-10-01 – 2026-10-08 | 8 | 1 | p25–p75 1–1 | 8 | 1 | p25–p75 1–1 |

### Version comparisons

For each role whose latest harness version differs from the previous one. A difference is printed as a finding only when both sides have n ≥ 5 and the spreads do not overlap; otherwise it is labelled noise / inconclusive and no difference is given.

- dec: aaaa1111 → bbbb2222 | runs 6 → 6 | tokens median 104.5 (n=6) → 12.5 (n=6): finding, median difference -92 | time (ms) median 1002.5 (n=6) → 102.5 (n=6): finding, median difference -900
- same: aaaa1111 → bbbb2222 | runs 5 → 5 | tokens median 102 (n=5) → 202 (n=5): finding, median difference +100 | time (ms) median 1 (n=5) → 1 (n=5): noise / inconclusive (spreads overlap)

## Role × model

Runs grouped by role and the model written on each run (all projects and harness versions together): the main conversation's model changes per session, so the harness fingerprint alone mixes models. Model ids that differ only in case are one row (shown in lower case). Columns as in the harness table: tokens = in + out + cache_read + cache_write of one run, time = ms; a run with an unread value is left out of that column's n; spread is min–max when n < 4 and p25–p75 when n ≥ 4. A run without a model is listed as `(model unknown)`. The runs are different tasks, so this is observation, not a controlled test.

The signal columns count the `events.md` events of that role × model (see Outcome signals for the signals). An event is joined to the runs of the same date + project + role (case does not matter; `main` is the main conversation) and counted under the model of those runs, whatever the harness version. When the runs it matches that day used more than one model, the model is not guessed: the event is counted in no row and shows in the `Ambiguous model` line under the table. An event with no run to match is not here either (it is counted under Outcome signals). `other signals` sums signal words with no column of its own. `repeated-failure` and `redone` with work type `experiment` are expected iterations and are left out; the other signals with that work type are counted. Events are self-reported, so the counts are a lower bound. `Cost n` is the number of runs the cost adds up (a run with any unread token value is left out), and the cost uses the prices and rules of the cost table below; `-` for a model with no known price or a token total that does not fit in 64 bits.

| Role | Model | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread | fix-request | review-block | review-wrong | repeated-failure | redone | other signals | Cost n | Approx. cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dec | claude-opus-5-5 | 12 | 2026-10-01 – 2026-10-15 | 12 | 58.5 | p25–p75 12.8–104.3 | 12 | 552.5 | p25–p75 102.8–1002.3 | 0 | 0 | 0 | 0 | 0 | 0 | 12 | <$0.01 |
| q4 | claude-opus-5-5 | 4 | 2026-10-01 – 2026-10-04 | 4 | 2.5 | p25–p75 1.8–3.3 | 4 | 25 | p25–p75 17.5–32.8 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | <$0.01 |
| q6 | claude-opus-5-5 | 6 | 2026-10-01 – 2026-10-06 | 6 | 2.5 | p25–p75 1.3–3.8 | 6 | 17.5 | p25–p75 8.8–26.3 | 0 | 0 | 0 | 0 | 0 | 0 | 6 | <$0.01 |
| r-cache | claude-sonnet-5-5 | 1 | 2026-10-07 | 1 | 58000 | min–max 58000–58000 | 1 | 1 | min–max 1–1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | $0.15 |
| r-fable | claude-fable-5-1 | 1 | 2026-10-05 | 1 | 2500 | min–max 2500–2500 | 1 | 1 | min–max 1–1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | $0.03 |
| r-haiku | claude-haiku-5-5 | 1 | 2026-10-03 | 1 | 50000 | min–max 50000–50000 | 1 | 1 | min–max 1–1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | <$0.01 |
| r-haiku45 | claude-haiku-4-5-20251001 | 1 | 2026-10-04 | 1 | 12500 | min–max 12500–12500 | 1 | 1 | min–max 1–1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | $0.01 |
| r-opus | claude-opus-5-5 | 1 | 2026-10-02 | 1 | 3750 | min–max 3750–3750 | 1 | 1 | min–max 1–1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | $0.02 |
| r-sonnet | claude-sonnet-5-5 | 1 | 2026-10-01 | 1 | 72500 | min–max 72500–72500 | 1 | 1 | min–max 1–1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | $0.15 |
| r-zero | claude-opus-5-5 | 1 | 2026-10-06 | 1 | 0 | min–max 0–0 | 1 | 1 | min–max 1–1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | $0.00 |
| same | claude-opus-5-5 | 10 | 2026-10-01 – 2026-10-10 | 10 | 152 | p25–p75 102.3–201.8 | 10 | 1 | p25–p75 1–1 | 0 | 0 | 0 | 0 | 0 | 0 | 10 | <$0.01 |
| t16 | claude-sonnet-5-5 | 16 | 2026-10-01 – 2026-10-16 | 16 | 1 | p25–p75 1–1 | 16 | 1 | p25–p75 1–1 | 1 | 0 | 0 | 0 | 0 | 0 | 16 | <$0.01 |
| t20 | claude-sonnet-5-5 | 20 | 2026-10-01 – 2026-10-20 | 20 | 1 | p25–p75 1–1 | 20 | 1 | p25–p75 1–1 | 0 | 0 | 0 | 0 | 3 | 0 | 20 | <$0.01 |
| t200 | claude-sonnet-5-5 | 200 | 2026-03-01 – 2026-10-04 | 200 | 1 | p25–p75 1–1 | 200 | 1 | p25–p75 1–1 | 57 | 0 | 0 | 0 | 0 | 0 | 200 | <$0.01 |
| t3 | claude-sonnet-5-5 | 3 | 2026-10-01 – 2026-10-03 | 3 | 1 | min–max 1–1 | 3 | 1 | min–max 1–1 | 2 | 0 | 0 | 0 | 0 | 0 | 3 | <$0.01 |
| t8 | claude-sonnet-5-5 | 8 | 2026-10-01 – 2026-10-08 | 8 | 1 | p25–p75 1–1 | 8 | 1 | p25–p75 1–1 | 1 | 5 | 0 | 0 | 0 | 0 | 8 | <$0.01 |

- Ambiguous model: 0 event(s) matched runs of more than one model that day, so they are in no row above

### Approximate cost per model

Approximate: tokens × list price (USD per million tokens as of 2026-10-21), summed per model over all projects and roles; the cost column of the role × model table above splits the same sum by role. Cache writes are priced at the 5-minute rate because the 1-hour split is not recorded. Haiku 5.5 is priced at the rate for prompts up to 100K tokens, so its cost is a lower bound. A model id is matched by family and version (`claude-opus-5-5`, with or without a date or `[1m]` after it); an id with no known price shows `-`, never a guess, and so does a model with no run to count or a token total that does not fit in 64 bits. A run with any unread token value is left out of the cost and counted under `Left out`.

| Model | Priced as | List price per M tokens (in / out / cache write / cache read) | Runs | Left out | Approx. cost (USD) |
|---|---|---|---|---|---|
| claude-fable-5-1 | Fable 5.1 | 10 / 50 / 12.5 / 0.25 | 1 | 0 | $0.03 |
| claude-haiku-4-5-20251001 | Haiku 4.5 | 1 / 5 / 1.25 / 0.1 | 1 | 0 | $0.01 |
| claude-haiku-5-5 | Haiku 5.5 | 0.1 / 0.5 / 0.125 / 0.01 | 1 | 0 | <$0.01 |
| claude-opus-5-5 | Opus 5.5 | 4 / 20 / 5 / 0.2 | 34 | 0 | $0.02 |
| claude-sonnet-5-5 | Sonnet 5.5 | 2 / 10 / 2.5 / 0.1 | 249 | 0 | $0.29 |

## Outcome signals (events.md)

events.md is written by the orchestrator about its own work, so these counts are a lower bound, not everything that went wrong. Each event is joined by date + project + role (case does not matter; `main` is the main conversation) to the harness version of that role's runs that day. Per run = events of that signal / runs of that role under that version. A `repeated-failure` or `redone` event whose work type is `experiment` is an expected iteration, not a harness failure: it is left out of the counts and rates here and shown on a line of its own. The other signals (`fix-request` · `review-block` · `review-wrong`) with work type `experiment` are harness signals and are counted as usual.

| Role | Harness | Runs | Signal | Events | Per run |
|---|---|---|---|---|---|
| t16 | h000aaaa | 16 | fix-request | 1 | 0.06 |
| t20 | h000aaaa | 20 | redone | 3 | 0.15 |
| t200 | h000aaaa | 200 | fix-request | 57 | 0.29 |
| t3 | h000aaaa | 3 | fix-request | 2 | 0.67 |
| t8 | h000aaaa | 8 | fix-request | 1 | 0.13 |
| t8 | h000aaaa | 8 | review-block | 5 | 0.63 |

- Events in the period: 69 · joined to a harness version 69 · no run of that role in that project that day 0 · harness changed that day, so not attributed 0
- Expected experiment iterations (`repeated-failure` · `redone` with work type `experiment`; not in the counts above): 0
- Lines starting with `- ` that are not in the format (`- YYYY-MM-DD | project | signal | work type · size | role | fact`): 0

## Read failures

- Lines with unread keys: 0 / 286 (role-run and turn lines whose `missing` is not empty)
- Unread keys: none

## Harness changes

none
