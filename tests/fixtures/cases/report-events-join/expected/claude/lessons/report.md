# Lessons record summary

- Period: 2026-10 ~ 2026-10 (last 1 month(s), this month included)
- Files read: runs/2026-10.jsonl
- Lines: role runs 28 · main-conversation turns 1 · harness changes 0 · skipped lines 0 (not JSON, or unknown kind)
- Record times: 2026-10-01T10:00:00+09:00 ~ 2026-10-14T12:00:00+09:00
- Current harness fingerprint: 006494ff (7 files)

## Project × role

The role is the `agent` name; the main conversation comes from turn lines. Token columns are `median / total`; the tools, turns and ms columns are medians. Unreadable values (`null`) are left out of the counts; a total too large for 64 bits is shown as `-`.

| Project | Role | Count | Model | effort | in | out | cache_read | cache_write | tools | turns | ms | Read failures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| alpha | main conversation | 1 | claude-sonnet-4-5-20250929 | high | 200 / 200 | 100 / 100 | 0 / 0 | 0 / 0 | 1 | 1 | 300 | 0 |
| alpha | coder | 10 | claude-sonnet-4-5-20250929 | high | 1600 / 16000 | 100 / 1000 | 0 / 0 | 0 / 0 | 1 | 1 | 2200 | 0 |
| alpha | designer | 2 | claude-sonnet-4-5-20250929 | high | 400 / 800 | 100 / 200 | 0 / 0 | 0 / 0 | 1 | 1 | 550 | 0 |
| alpha | reviewer | 6 | claude-sonnet-4-5-20250929 | high | 3000 / 18000 | 100 / 600 | 0 / 0 | 0 / 0 | 1 | 1 | 3100 | 0 |
| alpha | tester | 10 | claude-sonnet-4-5-20250929 | high | 2100 / 21000 | 100 / 1000 | 0 / 0 | 0 / 0 | 1 | 1 | 3200 | 0 |

## Role × harness version

Runs grouped by role and the harness fingerprint written on each run (all projects together), oldest version of a role first. Tokens = in + out + cache_read + cache_write of one run; time = ms. A run with an unread value is left out of that column's n. Spread is min–max when n < 4 and p25–p75 when n ≥ 4. The runs are different tasks, so this is observation, not a controlled test. The fingerprint covers the whole setup: a change may come from a file other than the role's own (see Harness changes).

| Role | Harness | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread |
|---|---|---|---|---|---|---|---|---|---|
| main conversation | aaaa1111 | 1 | 2026-10-03 | 1 | 300 | min–max 300–300 | 1 | 300 | min–max 300–300 |
| coder | aaaa1111 | 5 | 2026-10-01 – 2026-10-05 | 5 | 1200 | p25–p75 1100–1300 | 5 | 1200 | p25–p75 1100–1300 |
| coder | bbbb2222 | 5 | 2026-10-06 – 2026-10-10 | 5 | 2200 | p25–p75 2100–2300 | 5 | 3200 | p25–p75 3100–3300 |
| designer | bbbb2222 | 1 | 2026-10-05 | 1 | 500 | min–max 500–500 | 1 | 600 | min–max 600–600 |
| designer | aaaa1111 | 1 | 2026-10-05 | 1 | 500 | min–max 500–500 | 1 | 500 | min–max 500–500 |
| reviewer | aaaa1111 | 3 | 2026-10-01 – 2026-10-03 | 3 | 1100 | min–max 1000–1200 | 3 | 1100 | min–max 1000–1200 |
| reviewer | bbbb2222 | 3 | 2026-10-12 – 2026-10-14 | 3 | 5100 | min–max 5000–5200 | 3 | 5100 | min–max 5000–5200 |
| tester | aaaa1111 | 5 | 2026-10-01 – 2026-10-05 | 5 | 2000 | p25–p75 1500–2500 | 5 | 1200 | p25–p75 1100–1300 |
| tester | bbbb2222 | 5 | 2026-10-06 – 2026-10-10 | 5 | 2400 | p25–p75 1900–2900 | 5 | 5200 | p25–p75 5100–5300 |

### Version comparisons

For each role whose latest harness version differs from the previous one. A difference is printed as a finding only when both sides have n ≥ 5 and the spreads do not overlap; otherwise it is labelled noise / inconclusive and no difference is given.

- coder: aaaa1111 → bbbb2222 | runs 5 → 5 | tokens median 1200 (n=5) → 2200 (n=5): finding, median difference +1000 | time (ms) median 1200 (n=5) → 3200 (n=5): finding, median difference +2000 | applied by 2026-10-06 2026-10-06-1.md#2
- designer: bbbb2222 → aaaa1111 | runs 1 → 1 | tokens median 500 (n=1) → 500 (n=1): noise / inconclusive (n < 5; spreads overlap) | time (ms) median 600 (n=1) → 500 (n=1): noise / inconclusive (n < 5)
- reviewer: aaaa1111 → bbbb2222 | runs 3 → 3 | tokens median 1100 (n=3) → 5100 (n=3): noise / inconclusive (n < 5) | time (ms) median 1100 (n=3) → 5100 (n=3): noise / inconclusive (n < 5) | applied by 2026-10-06 2026-10-06-1.md#2
- tester: aaaa1111 → bbbb2222 | runs 5 → 5 | tokens median 2000 (n=5) → 2400 (n=5): noise / inconclusive (spreads overlap) | time (ms) median 1200 (n=5) → 5200 (n=5): finding, median difference +4000 | applied by 2026-10-06 2026-10-06-1.md#2

## Role × model

Runs grouped by role and the model written on each run (all projects and harness versions together): the main conversation's model changes per session, so the harness fingerprint alone mixes models. Model ids that differ only in case are one row (shown in lower case). Columns as in the harness table: tokens = in + out + cache_read + cache_write of one run, time = ms; a run with an unread value is left out of that column's n; spread is min–max when n < 4 and p25–p75 when n ≥ 4. A run without a model is listed as `(model unknown)`. The runs are different tasks, so this is observation, not a controlled test.

The signal columns count the `events.md` events of that role × model (see Outcome signals for the signals). An event is joined to the runs of the same date + project + role (case does not matter; `main` is the main conversation) and counted under the model of those runs, whatever the harness version. When the runs it matches that day used more than one model, the model is not guessed: the event is counted in no row and shows in the `Ambiguous model` line under the table. An event with no run to match is not here either (it is counted under Outcome signals). `other signals` sums signal words with no column of its own. `repeated-failure` and `redone` with work type `experiment` are expected iterations and are left out; the other signals with that work type are counted. Events are self-reported, so the counts are a lower bound. `Cost n` is the number of runs the cost adds up (a run with any unread token value is left out), and the cost uses the prices and rules of the cost table below; `-` for a model with no known price or a token total that does not fit in 64 bits.

| Role | Model | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread | fix-request | review-block | review-wrong | repeated-failure | redone | other signals | Cost n | Approx. cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| main conversation | claude-sonnet-4-5-20250929 | 1 | 2026-10-03 | 1 | 300 | min–max 300–300 | 1 | 300 | min–max 300–300 | 2 | 0 | 1 | 0 | 0 | 0 | 1 | - |
| coder | claude-sonnet-4-5-20250929 | 10 | 2026-10-01 – 2026-10-10 | 10 | 1700 | p25–p75 1225–2175 | 10 | 2200 | p25–p75 1225–3175 | 3 | 1 | 0 | 0 | 1 | 0 | 10 | - |
| designer | claude-sonnet-4-5-20250929 | 2 | 2026-10-05 | 2 | 500 | min–max 500–500 | 2 | 550 | min–max 500–600 | 0 | 0 | 0 | 0 | 1 | 0 | 2 | - |
| reviewer | claude-sonnet-4-5-20250929 | 6 | 2026-10-01 – 2026-10-14 | 6 | 3100 | p25–p75 1125–5075 | 6 | 3100 | p25–p75 1125–5075 | 0 | 0 | 1 | 0 | 0 | 0 | 6 | - |
| tester | claude-sonnet-4-5-20250929 | 10 | 2026-10-01 – 2026-10-10 | 10 | 2200 | p25–p75 1600–2800 | 10 | 3200 | p25–p75 1225–5175 | 0 | 0 | 0 | 0 | 0 | 0 | 10 | - |

- Ambiguous model: 0 event(s) matched runs of more than one model that day, so they are in no row above

### Approximate cost per model

Approximate: tokens × list price (USD per million tokens as of 2026-10-21), summed per model over all projects and roles; the cost column of the role × model table above splits the same sum by role. Cache writes are priced at the 5-minute rate because the 1-hour split is not recorded. Haiku 5.5 is priced at the rate for prompts up to 100K tokens, so its cost is a lower bound. A model id is matched by family and version (`claude-opus-5-5`, with or without a date or `[1m]` after it); an id with no known price shows `-`, never a guess, and so does a model with no run to count or a token total that does not fit in 64 bits. A run with any unread token value is left out of the cost and counted under `Left out`.

| Model | Priced as | List price per M tokens (in / out / cache write / cache read) | Runs | Left out | Approx. cost (USD) |
|---|---|---|---|---|---|
| claude-sonnet-4-5-20250929 | - | - | 29 | 0 | - |

## Outcome signals (events.md)

events.md is written by the orchestrator about its own work, so these counts are a lower bound, not everything that went wrong. Each event is joined by date + project + role (case does not matter; `main` is the main conversation) to the harness version of that role's runs that day. Per run = events of that signal / runs of that role under that version. A `repeated-failure` or `redone` event whose work type is `experiment` is an expected iteration, not a harness failure: it is left out of the counts and rates here and shown on a line of its own. The other signals (`fix-request` · `review-block` · `review-wrong`) with work type `experiment` are harness signals and are counted as usual.

| Role | Harness | Runs | Signal | Events | Per run |
|---|---|---|---|---|---|
| main conversation | aaaa1111 | 1 | fix-request | 2 | 2 |
| main conversation | aaaa1111 | 1 | review-wrong | 1 | 1 |
| coder | aaaa1111 | 5 | fix-request | 2 | 0.4 |
| coder | aaaa1111 | 5 | review-block | 1 | 0.2 |
| coder | bbbb2222 | 5 | fix-request | 1 | 0.2 |
| coder | bbbb2222 | 5 | redone | 1 | 0.2 |
| reviewer | bbbb2222 | 3 | review-wrong | 1 | 0.33 |

- Events in the period: 12 · joined to a harness version 9 · no run of that role in that project that day 2 · harness changed that day, so not attributed 1
- Expected experiment iterations (`repeated-failure` · `redone` with work type `experiment`; not in the counts above): 0
- Lines starting with `- ` that are not in the format (`- YYYY-MM-DD | project | signal | work type · size | role | fact`): 1

## Read failures

- Lines with unread keys: 0 / 29 (role-run and turn lines whose `missing` is not empty)
- Unread keys: none

## Harness changes

none
