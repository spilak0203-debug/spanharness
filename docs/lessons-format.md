# Lessons format

This is the normative specification of the lessons data: the files in the lessons folder, the `record` command that writes them, the harness fingerprint, and the `report` command that summarizes them. `scripts/spanharness.py` and `scripts/spanharness.ps1` are two implementations of this text. For the same inputs they must write byte-identical files. Where this text and an implementation disagree, the implementation is wrong.

Words in capitals (MUST, MUST NOT, MAY) are used in the usual sense.

## 0. Terms

- **Whitespace** is exactly these code points: U+0009 to U+000D, U+0020, U+0085, U+00A0, U+1680, U+2000 to U+200A, U+2028, U+2029, U+202F, U+205F, U+3000. **Trim** removes whitespace from both ends. A string is **blank** when trimming leaves nothing.
- **text(object, key)** is the value of `key` when it is a JSON string that is not blank, else null. The value is returned as it is (not trimmed). A missing key, a non-object `object`, and any other JSON type give null.
- **number(value)** is the value as a signed 64-bit integer, else null. A JSON number is converted by truncating toward zero (`7.9` gives 7, `-7.9` gives -7); a result outside -9223372036854775808 to 9223372036854775807 gives null. Booleans, strings, null, NaN and infinities give null. Numbers that are written with a fraction or an exponent and are larger than 2^53 in magnitude are not specified.
- **sum(values)** is the exact sum, or null when it is outside the signed 64-bit range.
- **Ordinal order** compares strings by their UTF-16 code unit sequence. (For text in the Basic Multilingual Plane this is the same as comparing code points. Python: `key=lambda s: s.encode("utf-16-be")`.) Every sort in this specification is ordinal and stable, and every comparison of strings is ordinal unless it says "ignoring case".
- **Lower-casing** (`lower`) uses the simple one-to-one Unicode case mapping, independent of culture. Model ids and roles are ASCII in practice.
- **Timestamp** is `YYYY-MM-DDTHH:MM:SS`, optionally followed by a fraction `.` and one or more digits, optionally followed by `Z` or `+HH:MM` or `-HH:MM`. All digits are ASCII `0`-`9`. The month is 01-12, the day exists in that month, the hour is 00-23, minutes and seconds are 00-59, and an offset is within +-14:00. At most the first 7 fraction digits are used. A timestamp without an offset is read as UTC. Any other text is not a timestamp. Two timestamps are compared as instants.
- **Local time** is the machine's time zone, or the offset of `--now` when that flag is given (section 2).
- **Date** of a record is the first 10 characters of its `t` when they have the form `DDDD-DD-DD` (ASCII digits only, no calendar check), else none.

## 1. Folder layout

The lessons folder is `<claude dir>/lessons/`, where `<claude dir>` is `$CLAUDE_CONFIG_DIR` when that is set and not blank, else `~/.claude`. `--lessons-dir` overrides the whole path.

| File | Written by | Contents |
|---|---|---|
| `runs/YYYY-MM.jsonl` | `record` | One line = one record. A new file each month (local time). Append-only. |
| `events.md` | orchestrator | Only when there is a signal, one line: `- date \| project \| signal \| work type · size \| role \| one-line fact`. Self-reported by the orchestrator about its own work, so its counts are a lower bound. `role` is the role's short name (`coder`, not `spanharness:coder`; `main` for the orchestrator's own work). The report joins each line to the runs by date (YYYY-MM-DD) + project + role (`main` = the main conversation). Signals: `fix-request` · `review-block` (role = the role whose work was blocked) · `review-wrong` (a reviewer finding that turned out not to be a problem) · `repeated-failure` · `redone`. A fact starting `user:` means the user raised it. Write the work type `experiment` for experiment work (trying methods against a baseline): a `repeated-failure` or `redone` with that work type is an expected iteration, not a harness failure, so the report leaves those two out of the signal rates and shows them as a separate count; `fix-request`, `review-block` and `review-wrong` are harness signals and are counted whatever the work type. |
| `harness-log.md` | advisor (when applying) · user | One line: `- date \| proposal file#number \| changed files \| expected effect \| check (validate · lint · test results) \| new harness fingerprint`. The report shows which proposal made a harness version. |
| `proposals/YYYY-MM-DD-N.md` | advisor | Numbered proposals. Applied items are marked `applied YYYY-MM-DD`. |
| `ab/tasks/` | advisor | The standing A/B task set: `index.md` (set version, selection rules, retired tasks) and one file per task. Frozen while a proposal is tested; changed only by an approved proposal item. |
| `ab/YYYY-MM-DD/` | advisor (plan) · orchestrator (results) | A/B plan (names the task set version and the grader) and blinded comparison results. |
| `backup/YYYY-MM-DD/` | advisor | Copies of files outside the plugin clone, from before they were edited. |
| `report.md` | `report` | The summary (section 5). Rewritten on every run. |
| `state/` | `record` | `harness.json` (last fingerprint, per-file hashes, plugin version) · `turn-<session>.json` and `agent-<agent_id>.json` (read positions) · `lock` (lock file, always empty). |
| `errors.log` | `record` | Why a record failed, one line per failure (section 3.6). Starts over once it passes 256 KB. |

No file in this folder holds conversation text. The plugin does not write a README into this folder.

Do not read `runs/` directly: run `report` and read `report.md`. The report groups runs by role × harness version (n, median and spread of tokens and time), compares each role's latest version with the previous one (a difference is a finding only with n ≥ 5 on both sides and non-overlapping spreads; otherwise it says noise / inconclusive), and counts the `events.md` signals per version. It also groups runs by role × model, with the signal counts and an approximate cost, because the main conversation's model changes per session and the harness fingerprint alone mixes models. The cost is for orientation, not a bill.

## 2. Command line

Both implementations take the same arguments.

```
record                          hook JSON on stdin; always exits 0
report [OUT.md] [--months N]    default OUT: <lessons>/report.md; N in 1..120, default 2
lint [--root DIR]               apply tests/harness-rules.json to DIR (default: the plugin root)
common: --claude-dir D  --lessons-dir D  --plugin-root D  --project-dir D  --now ISO8601
```

- `--claude-dir D` replaces `<claude dir>` (default: `$CLAUDE_CONFIG_DIR`, else `~/.claude`; `~` is `$HOME`, or `%USERPROFILE%` on Windows).
- `--lessons-dir D` replaces `<claude dir>/lessons`.
- `--plugin-root D` replaces the plugin root, which by default is the parent of the folder that holds the script (the script is `<plugin root>/scripts/spanharness.*`). It is where agents, output styles, skills, `.claude-plugin/plugin.json` and `scripts/prices.json` are read from.
- `--project-dir D` is the project folder. When it is absent, `$CLAUDE_PROJECT_DIR` is used (when set and not blank), then for `record` the `cwd` of the hook input, and for `report` and `lint` the current working directory of the process.
- `--now T` replaces the clock. `T` is `YYYY-MM-DDTHH:MM:SS` followed by `Z` or `+HH:MM` or `-HH:MM`; the offset is required. The value is used as local time with that offset: nothing is converted. It affects the `t` field, the month of the file, the time in `errors.log`, the 30-day clean-up of read positions, and the period of the report.
- All flags are accepted by all commands; a flag that a command does not use is ignored. A flag needs a value; the value is the next argument.
- Exit codes. `record`: always 0 (see 3.1). `report`: 0 written; 1 the file could not be written, or any other failure; 2 bad arguments (a usage line is printed to stderr, nothing is written). `lint`: 0 all rules pass; 1 at least one rule failed (one line per failed rule on stdout, starting with the rule id); 2 bad arguments.
- `report` prints the absolute path of the written file and a line break to stdout.
- The lint rules are data in `tests/harness-rules.json` and are specified there, not here.

## 3. `record`

`record` is the hook command for `SubagentStop` and `Stop`. The hook is one synchronous handler, so `record` delays the end of the conversation turn: it MUST be fast and it MUST always exit 0, with nothing on stdout, whatever happens. Failures go to `errors.log` only.

### 3.1 Guards, in this order

1. **Opt-out.** When the environment variable `SPANHARNESS_RECORD` is exactly `0`, exit 0 at once, without reading stdin and without touching any file.
2. **Host guard (PowerShell implementation only).** When the host is not Windows, exit 0 at once, without reading stdin. (On Windows the launcher script exits for `record` and the PowerShell implementation records; on other systems the Python implementation records.)
3. **Terminal.** When stdin is a terminal (not a pipe or a file), print one usage line to stderr and exit 0. There is no timeout on reading stdin.
4. Bad arguments (an unknown flag, a flag without a value, a positional argument, a `--now` that is not valid) are checked after the terminal guard, in both implementations. One line is written to stderr (the wording is free), nothing else happens, and the exit code is 0. Every unexpected failure also ends in exit 0 and writes `record failed` plus detail to `errors.log` (3.6).

### 3.2 Steps

1. Read all of stdin as bytes. Remove a leading UTF-8 byte order mark. Decode as UTF-8 (invalid bytes become U+FFFD).
2. Parse the JSON. When it is not a JSON object (bad JSON, another JSON type, nesting deeper than 100 levels, or empty input), write `hook input is not a JSON object ({N} bytes)` to `errors.log`, where `N` is the number of bytes read after the byte order mark, and exit. The error text of the parser MUST NOT be written, because it would quote the input.
3. Read these keys of the input, all with `text()`: `hook_event_name`, `session_id`, `cwd`, `agent_id`, `agent_type`; and `effort`, which is an object (`{"level": "low"}`), from which the string `level` is taken with `text()`. If `effort` is not an object, or has no usable `level`, the recorded effort is null. No other key is read (in particular `last_assistant_message` is never read).
4. Decide the kind. **agent**: `hook_event_name` is `SubagentStop` and `agent_type` is not null. **turn**: `hook_event_name` is `Stop` and `agent_id` is null. Anything else (another event, a `SubagentStop` without an `agent_type`, a `Stop` that carries an `agent_id`) exits 0 here, having written nothing.
5. The transcript is `agent_transcript_path` (kind agent) or `transcript_path` (kind turn); it may be null. The **state file** is `state/agent-<name>.json` with `<name>` = safe-name(`agent_id`) for kind agent, and `state/turn-<name>.json` with `<name>` = safe-name(`session_id`) for kind turn; it is none when that id is null. The state file therefore follows an agent run, so a role called again with the same `agent_id` counts only what that call added.
   - **safe-name(s)**: replace every character that is one of `"` `<` `>` `|` `:` `*` `?` `\` `/` or has a code below U+0020 with `-`; trim spaces and dots from both ends; keep at most the first 60 UTF-16 code units and trim spaces and dots from the end again; when nothing is left the name is `skill`.
6. **Wait for a complete last line** (skipped when the transcript path is null or empty): if the file exists, is not empty and its last byte is not `0x0A`, poll every 50 ms until its last byte is `0x0A` or 1000 ms have passed since the start; otherwise do not wait at all. Claude Code writes the transcript behind the hook's back, and a partial last line is left for the next record anyway (3.3), so the wait only shortens that delay. This is the only deliberate delay of `record`; the hook is synchronous, so it must stay short.
7. **Fingerprint** (section 4), outside the lock. When it fails, write `harness fingerprint failed — {reason}` to `errors.log`, continue with no fingerprint (`harness` is null in the record, no `harness` line is written, `state/harness.json` is not touched).
8. **Role files** (kind agent only): read `role_model` and `role_effort` as described in 4.4.
9. Read the saved offset: the state file's `offset` (number()) when the file exists, parses as an object, and its `path` equals the transcript path ignoring case; else none. With no state file the offset is none. (No lock is held.)
10. Summarize the transcript (3.3): for kind agent `summarize(transcript, offset ?? 0)`; for kind turn `summarize_turn(transcript, offset)`. This is the only slow step, and it is made without the lock.
11. When an offset was saved and the summary says `unchanged`, exit 0: nothing happened since the last record (the Stop that fires at the same moment as a SubagentStop already counted it). (Test-only: 3.9.)
12. **Take the lock** (3.7). When it cannot be taken within 10 s, write `could not take the lock; record skipped` and exit. With the lock held, read the saved offset again (as in step 9). When it is not the one used in step 9 (another record of the same state file has finished in the meantime), release the lock and go back to step 9. This happens at most 3 times; the 4th time the lock is taken before step 9 and held until step 18, so a record is never starved.
13. Take the time `now` (local time; read from the clock here, after the lock, not when the process started; `--now` replaces the clock) and the stamp `t` = `now` as `yyyy-MM-ddTHH:mm:ss` followed by the offset as `+HH:MM` / `-HH:MM` (`+00:00` for UTC, never `Z`). The month file is `runs/` + `now` as `yyyy-MM` + `.jsonl`.
14. Build the record (3.4). Compute `missing`.
15. Decide whether a `harness` line comes first: when a fingerprint exists and (no saved harness state exists, or its `harness` differs from the fingerprint, or its `plugin_version`, read with `text()`, differs from the current plugin version — a missing value, a value that is not a string, and a blank string all count as null). The saved state is `state/harness.json`; it counts as missing when it cannot be read, is not a JSON object, has no string `harness`, or has no object `files`.
16. **Append** the `harness` line (if any) and then the record line to the month file in one write: UTF-8 without byte order mark, each line ending with a single `\n`. Create the folders. If the write fails with an I/O error, retry up to 5 times, 100 ms apart; after that the failure is reported (3.6) and nothing below happens, so the next call counts the same stretch again.
17. Bookkeeping; each part is independent and a failure in one is written to `errors.log` and does not stop the others:
    - when a `harness` line was written: write `state/harness.json` (3.5);
    - when there is a state file: write it (3.5) with `path` = the transcript path and `offset` = the summary's `offset`;
    - delete the state files older than 30 days (3.5).
18. Release the lock (if it is held). Exit 0.

The steps before 6 touch no file when the event is not handled, and the work after the wait is bounded: a handful of small files for the fingerprint and the new part of one transcript. The time it takes is proportional to the size of that new part; the lock is held for the commit only (steps 12 to 18), which is a few small files. Nothing is sent over the network and no child process is started.

### 3.3 Transcript summary

The transcript is a JSONL file. The summary reads the file from a byte offset.

`summarize(path, offset)`:

- Open the file for reading, allowing others to write. The path must be a regular file: a folder, a named pipe or a device cannot be read in this sense, which is decided from the file's metadata when it is opened, and opening MUST NOT wait for a writer. When it cannot be opened or read (at the start or partway through), nothing is counted: the result has `offset` = the offset given, every count is null, and `unchanged` is false.
- The length of the file is taken once, when it is opened. No byte after that length is read, even if the file grows meanwhile; the next record continues there.
- If `offset` is negative or larger than the file length, the offset becomes 0 (the file started over). Start reading at the offset. `unchanged` is true when the file length equals the offset.
- Split the bytes into lines at the byte `0x0A`. A line is decoded as UTF-8 (after the whole line has been collected, so a multi-byte character is never cut), a UTF-8 byte order mark is removed from the line that starts at byte 0 of the file (and from no other line: a byte order mark inside the file makes that line broken), and the line is trimmed. A line that is blank is skipped. Every other line is parsed as a JSON object (nesting deeper than 200 levels is a parse failure); a line that is not a JSON object is **broken** and counted in `broken` (the count is for diagnostics only and is not written anywhere).
- After each complete line (one that ends with `0x0A`), `offset` moves to the byte after that `0x0A`, whether the line was usable or not.
- The last line, when the file does not end with `0x0A`, is still being written. It counts only when it is a JSON object (or blank): then `offset` moves to the end of the file. If it is not, it is left for the next time: `offset` stays where it was and the line is not counted as broken.
- For every JSON object line:
  - `type` = text(line, "type"). When `type` is `user` or `assistant` and `timestamp` is a JSON string that is a timestamp (section 0), the instant joins the minimum and the maximum seen (lines of any other type, such as `system`, are written after the turn and MUST NOT count).
  - When `type` is `user` and the line is a **prompt** (below), `last_prompt` = the byte position where this line starts (the offset as it is before this line is finished).
  - When `type` is `assistant` and `message` is an object: `id` = text(message, "id"), or a unique placeholder (`line-1`, `line-2`, …, taken from one counter shared with the tool placeholders) when there is none. The `id` joins the set of answers. `model` = text(message, "model"): when it is not null and not `<synthetic>`, it replaces the last model seen. When `message.usage` is an object, then for the id the four values `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` are read with number(); a value that is not null replaces the one kept for that id, a null keeps the earlier one. (A message is written once per content block with the same usage; the last value wins.) When `message.content` is an array, every element that is an object with `type` equal to `tool_use` adds its `id` (text(), or a unique placeholder `tool-N` from the same counter) to the set of tool calls.
- A **prompt** is a `user` line that is typed by the person. It is not a prompt when `isMeta` is the JSON value `true`, or `isCompactSummary` is `true`, or text(`origin`, "kind") is not null and not `human`. Otherwise `message.content` decides: a string is a prompt when it is not blank; an array is a prompt when it has an object element whose text(element, "type") is not `tool_result` (an element without a `type` counts); anything else is not a prompt.
- The result:
  - `in`, `out`, `cache_read`, `cache_write`: for each, null when no answer kept a value for that key; else the sum over all ids (an id with no value counts 0), or null when the sum does not fit 64 bits;
  - `turns` = the number of ids in the set of answers, or null when it is empty; `tools` = the number of tool call ids, or null when the set of answers is empty (0 when there were answers but no tool call);
  - `ms` = the maximum minus the minimum instant, in whole milliseconds rounded down, or null when no instant was seen (0 for a single instant);
  - `model` = the last model, or null.

`summarize_turn(path, offset)` reads one turn of the main conversation: with an offset, it is `summarize(path, offset)`. Without one (the hook was switched on in the middle of a session, or the state was cleaned away and the session came back) it is `summarize(path, p)`, where `p` is the `last_prompt` that `summarize(path, 0)` finds (the start of the last prompt line of the file), or 0 when it finds none. What lies before `p` does not change the result, so it is not read: an implementation finds `p` by reading blocks from the end of the file, line by line backwards, until a line is a prompt (a line counts as in `summarize`: a complete line, or a last line that is a JSON object), and does not parse the part before it. A session at its first turn has its prompt at the top, so it is counted whole either way.

### 3.4 Record lines

A line is one JSON object, written as in rule 5 of section 6, with the keys in exactly the order below. Every key is always present; a value that is not known is `null`.

**`agent`** (one role run) — 20 keys:

| # | Key | Type | Value |
|---|---|---|---|
| 1 | `t` | string | the stamp (3.2 step 13) |
| 2 | `kind` | string | `agent` |
| 3 | `project` | string or null | project name (below) |
| 4 | `cwd` | string or null | text(input, "cwd") |
| 5 | `session` | string or null | text(input, "session_id") |
| 6 | `agent` | string | `agent_type`, exactly as the hook gave it (for example `spanharness:coder`) |
| 7 | `agent_id` | string or null | text(input, "agent_id") |
| 8 | `model` | string or null | the summary's model (full id, as in the transcript) |
| 9 | `role_model` | string or null | from the role file (4.4) |
| 10 | `effort` | string or null | the hook's `effort.level` |
| 11 | `role_effort` | string or null | from the role file (4.4) |
| 12 | `in` | integer or null | summary |
| 13 | `out` | integer or null | summary |
| 14 | `cache_read` | integer or null | summary |
| 15 | `cache_write` | integer or null | summary |
| 16 | `tools` | integer or null | summary |
| 17 | `turns` | integer or null | summary |
| 18 | `ms` | integer or null | summary |
| 19 | `harness` | string or null | the fingerprint, 8 hex characters |
| 20 | `missing` | array of strings | below |

**`turn`** (one main-conversation turn) — 16 keys, the same as `agent` without `agent`, `agent_id`, `role_model` and `role_effort`, in this order: `t`, `kind` (`turn`), `project`, `cwd`, `session`, `model`, `effort`, `in`, `out`, `cache_read`, `cache_write`, `tools`, `turns`, `ms`, `harness`, `missing`.

**`harness`** (the fingerprint changed) — 8 keys:

| # | Key | Type | Value |
|---|---|---|---|
| 1 | `t` | string | the same stamp as the record that follows |
| 2 | `kind` | string | `harness` |
| 3 | `harness` | string | the new fingerprint |
| 4 | `prev` | string or null | the saved fingerprint, null when there was no saved state |
| 5 | `changed` | array of strings | keys in both prints with a different hash, ordinal order |
| 6 | `added` | array of strings | keys only in the new print, ordinal order (every key when there was no saved state) |
| 7 | `removed` | array of strings | keys only in the saved print, ordinal order |
| 8 | `plugin_version` | string or null | `version` of `<plugin root>/.claude-plugin/plugin.json` (text()), null when the file is missing, unreadable, or has none |

When only the plugin version differs (the fingerprint is the same), the three arrays are empty.

**Project name.** `project` = the folder name of the nearest repository at or above `cwd`: null when `cwd` is null. Otherwise remove trailing `/` and `\` from `cwd` and walk upward from there: at each folder, if its last path component is not empty and `<folder>/.git` exists (as a folder or as a file; a worktree has a file), that component is the project. Parents are taken with the host's path rules, and the walk ends when no parent is left or the folder is empty. When nothing matched, the project is the last component of the trimmed `cwd` (the text after its last `/` or `\`, whichever comes later, on every host), or null when that is empty.

**`missing`.** The keys of the record whose value is null, in key order, except `effort`, `role_model` and `role_effort` (a role file may have no model or effort of its own, and the hook has no effort for a model that has none). `missing` itself is not listed. Besides the token keys it can therefore list `project`, `cwd`, `session`, `agent_id`, `model` and `harness`. The report counts a line whose `missing` is not empty as a read failure.

**Privacy.** The record holds numbers, ids, the project folder name and `cwd`. It never holds a prompt, an answer, or any text from the transcript other than the model id.

### 3.5 State files

All are in `state/`. Each is a JSON object written as in rule 5 of section 6 with no trailing line break, through a temporary file (`<name>.tmp`, then replace the target; when that fails it is retried 3 times, 150 ms apart: 4 tries in all).

- `turn-<name>.json` and `agent-<name>.json`: `{"path": <transcript path>, "offset": <integer>}`, in this key order.
- `harness.json`: `{"harness": <fingerprint>, "files": {<key>: <hash>, …}, "plugin_version": <string or null>}`, in this key order, `files` in ordinal key order.
- `lock`: an empty file that is only locked (3.7). It is never deleted.
- **Clean-up**: every file in `state/` whose name starts with `turn-` or `agent-` and ends with `.json`, and whose last-write time is more than 30 days (30 × 24 h) before the current time (`--now` when given), is deleted.

### 3.6 `errors.log`

`errors.log` is in the lessons folder. A failure appends one line: `{yyyy-MM-dd HH:mm:ss} {what}` or `{yyyy-MM-dd HH:mm:ss} {what} — {detail}` (an em dash U+2014 with a space on each side; the time is local; the line ends with a single `\n`; UTF-8). `detail` is one line (line breaks replaced by spaces) with free wording, for example the exception type and the system's reason; implementations are not required to agree on it. It MUST NOT contain a path, a file name or an id: the names of the state files and folders come from the hook input (`session_id`, `agent_id`, `cwd`), and the messages of the runtime for a failed file operation quote them. For a failed file operation it is the exception type and the reason without the file name (Python: `OSError: <strerror>`; PowerShell: the .NET type name and a fixed wording such as `access denied`). Before appending, when the file exists and is larger than 262144 bytes it is deleted, so it starts over. Writing the log MUST NOT fail loudly: if the log cannot be written, nothing is done. The log never holds text from the hook input or the transcript.

The `what` texts are fixed:

| When | `what` |
|---|---|
| step 2 | `hook input is not a JSON object ({N} bytes)` |
| step 7 | `harness fingerprint failed` (detail: `cannot read {key}` with the key of the unreadable file, section 4.1) |
| step 12 | `could not take the lock; record skipped` |
| step 16 | `could not write the record` |
| step 17 | `could not save the harness state`, `could not save the read position`, `could not remove old read positions` |
| anything else | `record failed` |

The conformance tests compare the part of each line before ` — ` without the time.

### 3.7 Locking

The lock is an exclusive lock on `state/lock` (the folder is created when needed). It is held from the commit (step 12) to the end (step 18), and only then: the summary of the transcript, which is the slow part, is made without it, so that records that arrive together (six agents stopping at once) do not wait for each other's transcripts and none runs into the 10-second limit.

What the lock protects is the saved position. Two records of the same state file (two Stops of one session, or one agent id stopped twice) may both sum up the same stretch of the transcript, but only one of them may write it. So the second record, having the lock, compares the saved position with the one its summary started from (step 12); when another record has moved it, the second discards its summary and sums up again from the new position, which is normally "unchanged" (step 11). The harness fingerprint is decided and the files are appended and replaced with the lock held, so the `harness` line is written once.

The lock is taken by retrying every 50 ms for at most 10 s. Python uses `fcntl.flock` (and `msvcrt.locking` when it runs on Windows in tests); PowerShell opens the file with `FileShare.None`. A lock left by a process that was killed is released by the operating system.

### 3.8 Example

Hook input (one line in reality; here wrapped), with `--now 2026-10-21T10:02:00+09:00`:

```json
{"hook_event_name":"SubagentStop","session_id":"sess1","cwd":"/work/repo-a/src","agent_id":"ag1","agent_type":"spanharness:coder","effort":{"level":"high"},"transcript_path":"/t/main.jsonl","agent_transcript_path":"/t/agent-ag1.jsonl","last_assistant_message":"not recorded"}
```

`/work/repo-a/.git` is a folder. The role file `<plugin root>/agents/coder.md` has `model: sonnet` and `effort: high`. The agent transcript `/t/agent-ag1.jsonl` has these lines (the 4th is not JSON):

```
{"type":"user","timestamp":"2026-10-21T10:00:00.000Z","message":{"role":"user","content":"hello"}}
{"type":"assistant","timestamp":"2026-10-21T10:00:05.000Z","message":{"id":"m1","model":"claude-sonnet-4-5-20250929","content":[{"type":"tool_use","id":"t1"}],"usage":{"input_tokens":10,"output_tokens":5,"cache_read_input_tokens":100,"cache_creation_input_tokens":20}}}
{"type":"assistant","timestamp":"2026-10-21T10:00:06.000Z","message":{"id":"m1","model":"claude-sonnet-4-5-20250929","content":[{"type":"tool_use","id":"t2"}],"usage":{"input_tokens":10,"output_tokens":5,"cache_read_input_tokens":100,"cache_creation_input_tokens":20}}}
{not json
{"type":"assistant","timestamp":"2026-10-21T10:01:30.500Z","message":{"id":"m2","model":"claude-sonnet-4-5-20250929","content":[],"usage":{"input_tokens":7,"output_tokens":3,"cache_read_input_tokens":50,"cache_creation_input_tokens":0}}}
```

`m1` is counted once (usage 10/5/100/20), `m2` adds 7/3/50/0: in 17, out 8, cache_read 150, cache_write 20; two answers; two tool calls; from 10:00:00.000 to 10:01:30.500 is 90500 ms. With no saved state, the plugin at version `0.1.0` and the fingerprint of the example in 4.6 (`006494ff`), the month file `runs/2026-10.jsonl` receives two lines:

```
{"t":"2026-10-21T10:02:00+09:00","kind":"harness","harness":"006494ff","prev":null,"changed":[],"added":["CLAUDE.md","output-style","plugin/agents/coder.md","plugin/agents/tester.md","plugin/output-styles/orchestrator.md","plugin/skills/new-project/SKILL.md","skills/ponytail/SKILL.md"],"removed":[],"plugin_version":"0.1.0"}
{"t":"2026-10-21T10:02:00+09:00","kind":"agent","project":"repo-a","cwd":"/work/repo-a/src","session":"sess1","agent":"spanharness:coder","agent_id":"ag1","model":"claude-sonnet-4-5-20250929","role_model":"sonnet","effort":"high","role_effort":"high","in":17,"out":8,"cache_read":150,"cache_write":20,"tools":2,"turns":2,"ms":90500,"harness":"006494ff","missing":[]}
```

and `state/agent-ag1.json` is `{"path":"/t/agent-ag1.jsonl","offset":<length of the transcript in bytes>}`. A second call with the same input and an unchanged transcript writes nothing (step 11).

### 3.9 Test-only gate

The environment variable `SPANHARNESS_TEST_GATE` exists for the tests of steps 12 and 13 and is never set by the plugin. When it is set and not blank, it names a folder, and in every try of steps 9 to 12 that passes step 11 (also a try that is then redone; not a try that ends as unchanged), before the lock is taken for the first three tries (the 4th holds it already), `record` creates the empty file `reached-N` in that folder (`N` is the number of the try, 1 to 4) and then waits until the file `go-N` exists in that folder, polling every 10 ms, for 60 s at most. An error on the way (the folder is missing) is ignored. A test changes the transcript and the saved read position while `record` waits, which is how a redo and the 4th try are reached without relying on timing. Without the variable nothing happens.

## 4. The harness fingerprint

The fingerprint says which version of "the harness" (the text that shapes how the roles and the main conversation behave) a run was made under. It is the first 8 lowercase hex characters of a SHA-256, over a set of files.

### 4.1 Files

`files` maps a key to the **file hash**: the lowercase hex SHA-256 of the file's bytes after (1) removing a leading UTF-8 byte order mark and (2) replacing every `0x0D 0x0A` pair with `0x0A`. A file that exists and cannot be read makes the whole fingerprint fail (`cannot read {key}`): a print with a file missing would look like that file was removed. A missing file or folder adds nothing and is not a failure.

| Key | Source | Why |
|---|---|---|
| `plugin/agents/<file>` | every file directly in `<plugin root>/agents/` whose name ends with `.md` (ASCII case-insensitive) | the roles |
| `plugin/output-styles/<file>` | the same for `<plugin root>/output-styles/` | the orchestrator text |
| `plugin/skills/<dir>/SKILL.md` | for every folder `<dir>` directly in `<plugin root>/skills/`, its `SKILL.md` if it exists | skills shape main-conversation work |
| `skills/<name>/SKILL.md` | for each `<name>` in the `skills:` lists of the plugin agent files above (4.3): `<claude dir>/skills/<name>/SKILL.md` if it exists | a preloaded skill is part of the role's prompt |
| `output-style` | the file hash of the **active output style** value, taken as UTF-8 text (4.2) | which style is active matters even when its text is in `plugin/` |
| `output-styles/<file>` | when the active output style is a user or project style file (4.2): that file, `<file>` being its name | a custom style's text |
| `CLAUDE.md` | `<claude dir>/CLAUDE.md` only | applies to every role; a project `CLAUDE.md` is left out, because it would split versions per project |

- A skill name is skipped when it is `.` or `..` or contains any of the characters listed for safe-name in 3.2 step 5. Each distinct name (exact string) is looked up once.
- Agents in `~/.claude/agents` or in the project that are not part of the plugin are not part of the fingerprint.
- `<file>` and `<dir>` are the names as they are on disk.

### 4.2 The active output style

The value is the first of these that has a top-level key `outputStyle` holding a string that is not blank (the string is used as it is, untrimmed): `<project>/.claude/settings.local.json`, `<project>/.claude/settings.json`, `<claude dir>/settings.json`; else the word `default`. `<project>` is the project folder (section 2); when there is none, the two project files are skipped. A file that is missing, cannot be parsed as a JSON object, or has no usable `outputStyle` is skipped (it is not a failure).

A **style file** matches the value when, in this order of folders, `<project>/.claude/output-styles/` then `<claude dir>/output-styles/`, and within a folder in ordinal order of file names, a file whose name ends with `.md` (ASCII case-insensitive) has either a frontmatter `name` (4.3) equal to the value, or a file name without `.md` equal to the value, comparing ignoring case. The first matching file gives the key `output-styles/<file>`. (The plugin's own style, whose value is `spanharness:orchestrator`, has no such file and is covered by `plugin/output-styles/…`.)

### 4.3 Frontmatter

Agent files, skill files and style files may start with a frontmatter block. Only the following is read.

- The text is split into lines at `\n` only (not `splitlines()`), and one trailing `\r` is removed from every line before anything else is checked, so a file with `\r\n` line ends reads the same as one with `\n`.
- The block starts when the first line, with trailing spaces, tabs and `\r` removed, is `---`. It ends at the first later line that is `---` or `...` (trailing spaces, tabs and `\r` removed). Without both, the file has no frontmatter and every `get` and `get_list` gives nothing.
- Inside the block, a **key line** matches `^([A-Za-z0-9_][A-Za-z0-9_.-]*)[ \t]*:([ \t]|$)`. Following lines belong to that key while they are empty, start with a space or a tab, are `-`, or start with `- `. Any other line ends the key (and is ignored). The first key line for a key name wins.
- `get(key)`: take the text after the first `:` of the key line and trim it; append every non-blank continuation line, trimmed, each after one space; trim. If the result starts with `"`, the value is the text up to the next unescaped `"`, with `\n`, `\t`, `\r`, `\0` and `\uXXXX` decoded and `\` + any other character meaning that character. If it starts with `'`, the value is the text up to the closing `'`, with `''` meaning `'`. Otherwise the value is the text before the first ` #` (a space and a hash), trimmed. A missing key gives null (not the empty string). Block scalars (`|`, `>`) are not supported.
- `get_list(key)`: items come from the key line and the continuation lines. From the key line: the text after the first `:` trimmed; when it begins with `#` it is empty, otherwise it is cut at the first ` #`; when it is not empty, remove one pair of surrounding `[` `]` if it starts with `[` and ends with `]`, split at `,`, and take each part through `get`'s value rules (quotes removed, comment cut, trimmed). From the continuation lines: every line whose trim is `-` or starts with `- ` gives an item with the text after the dash through the same value rules. Empty items are dropped. A missing key gives an empty list.

### 4.4 Role model and effort

For kind agent, `agent_type` selects one role file. A name is usable only when it is not `.` or `..` and contains none of the characters listed for safe-name (3.2 step 5); otherwise there is no role file.

- `spanharness:<name>`: `<plugin root>/agents/<name>.md`.
- Any other `<name>` (the whole `agent_type`): `<project>/.claude/agents/<name>.md`, then `<claude dir>/agents/<name>.md`; if neither exists and `<plugin root>/agents/<name>.md` exists, that file.

`role_model` = `get("model")` and `role_effort` = `get("effort")` of the file; both null when there is no file, no frontmatter, or no such key. The role file is matched by its file name, not by its `name` key.

### 4.5 Computation

1. Collect the keys and hashes (4.1).
2. Sort the keys in ordinal order.
3. Build the text of the lines `{key}\t{file hash}` joined with `\n`, with no line break at the end.
4. The fingerprint is the first 8 lowercase hex characters of the SHA-256 of that text (UTF-8).

**Compare(before, after)** gives `changed` (keys in both with different hashes), `added` (keys only in `after`), `removed` (keys only in `before`), each in ordinal order; a missing `before` counts as empty.

### 4.6 Example

A plugin root and a claude dir with these files (the `skills:` list of `coder.md` names `ponytail`; no `outputStyle` is set anywhere; the file `CLAUDE.md` has CRLF line ends):

| Key | File content (`\n` and `\r\n` as written) | File hash |
|---|---|---|
| `CLAUDE.md` | `- rule\r\n` | `8633657562154c9df489e6620a516ad95081412e73730819376a112647687cb4` |
| `output-style` | `default` | `37a8eec1ce19687d132fe29051dca629d164e2c4958ba141d5f4133a33f0688f` |
| `plugin/agents/coder.md` | `---\nname: coder\nmodel: sonnet\neffort: high\nskills:\n  - ponytail\n---\nA\n` | `ce57f2797ecef612cffcf986d40350144d3da63c3fb029cea8c201112159c693` |
| `plugin/agents/tester.md` | `---\nname: tester\n---\nB\n` | `3fc8998e3411814040cf6e1ea75b2abd9b25f74cb4db9f8e1008a1d1978cf4cb` |
| `plugin/output-styles/orchestrator.md` | `S\n` | `7aa397df66304bab4fe275afe0507a01844e7fda848b4e194a9402d010721839` |
| `plugin/skills/new-project/SKILL.md` | `N\n` | `28312e346b76a3f91e8283519baab5f103d79547dedff5fb7ccc0dc3c5119bbe` |
| `skills/ponytail/SKILL.md` | `P\n` | `852a478ece1b66d04d107ae488dd476a5a43b317f62729e25152e4bfba096cac` |

The keys are already in ordinal order (`CLAUDE.md` first because `C` < `o`). The text hashed is the seven lines `key<TAB>hash` joined with `\n`. Its SHA-256 starts with `006494ff`, which is the fingerprint.

## 5. `report`

`report` reads the runs of the last months, `events.md` and `harness-log.md`, and writes `report.md`. The same files in must give the same bytes out: rows and lists are sorted, and no clock time is written (the clock decides only the period).

### 5.1 Arguments and output

- Arguments: at most one positional `OUT.md`; `--months N`, where `N` is made of ASCII digits only (no sign, no space) and is 1 to 120 (default 2); and the common flags of section 2. A second positional, an unknown flag starting with `--`, a flag without its value, a bad `N`, an `OUT.md` that is not a valid path (for example it contains a NUL character) all give exit 2.
- The output path is `OUT.md` (relative to the current working directory) or `<lessons>/report.md`, made absolute. Missing folders are created. The text is written as UTF-8 without byte order mark and with `\n` line ends, through `<path>.tmp` and a replace (retrying 3 times 150 ms apart). Any failure to write gives exit 1 and a one-line reason on stderr. A report with nothing to count is still written.
- The period: `to` = the month of the local `now` as `yyyy-MM`; `from` = the month `months - 1` months before it (so `--months 1` is this month only). Example: now 2027-01-05 with 2 months is `2026-12 ~ 2027-01`.
- The prices come from `<plugin root>/scripts/prices.json` (5.9). If that file cannot be read or parsed, the report is still written with no known prices (every price and cost shows `-`), the date in the cost section is the word `unknown`, and one warning line goes to stderr; the exit code stays 0.

### 5.2 Reading the runs

- The files read are the files directly in `<lessons>/runs/` whose names are `YYYY-MM.jsonl` (the extension compared ASCII case-insensitively, the month 01-12, ASCII digits) with `from` ≤ `YYYY-MM` ≤ `to`, in ordinal order of the names. The files read are listed in the report even when a file in them turns out to be unreadable.
- A file is UTF-8 (a leading byte order mark is skipped, and invalid bytes become U+FFFD); lines end at `\n`, `\r\n` or a lone `\r`. A file that cannot be opened or read is listed under "Files that could not be opened" and the lines read before the failure still count. Blank lines are ignored.
- Each non-blank line is parsed as a JSON object (nesting deeper than 100 levels is a parse failure). `kind` = text(line, "kind"). A line that is not an object, or whose kind is not `agent`, `turn` or `harness`, is a **skipped line**.
- `t` = text(line, "t"). When `t` is a timestamp (section 0), it takes part in the **record times**: the earliest and the latest instant (on equal instants the first one read stays), shown with their original text. This holds for all three kinds.
- A `harness` line adds a **change**: `when` = `t` (or none), `prev` = text(line, "prev"), `hash` = text(line, "harness"), `changed`, `added` and `removed` = the elements of the array under that key that are strings and not blank (an absent or non-array value is an empty list; order kept), and `version` = text(line, "plugin_version"). It is not a run.
- An `agent` or `turn` line is a **run**, numbered `seq` from 0 in reading order. For kind `agent`: `main` = false, `role` = text(line, "agent") or `(role name unknown)`. For kind `turn`: `main` = true, `role` = `main conversation`. `project` = text(line, "project") or `(project unknown)`.
  - **Role normalization.** For kind `agent`, when the role begins with `spanharness:` (ignoring case) and something follows it, the prefix is removed (`spanharness:coder` is `coder`). Records keep the raw value; this applies only here and to the roles of `events.md` (5.3).
  - `harness` = text(line, "harness") or `(unknown)`. `model` = text(line, "model") trimmed and lower-cased, or null. `date` = the Date of `t` (section 0), or none. `counts` = number() of `in`, `out`, `cache_read`, `cache_write` (each may be null). `tokens` = sum(counts) when all four are not null, else null. `ms` = number(`ms`).
  - The line adds to the **project × role row** of (kind, project, role): `count` + 1; the lower-cased trimmed `model` (when not null) to the set of models; text(line, "effort") (when not null, as it is) to the set of efforts; each of `in`, `out`, `cache_read`, `cache_write`, `tools`, `turns`, `ms` whose number() is not null to the list of values of that column; when the array under `missing` has at least one string that is not blank, `unread` + 1 for the row and for the total, and + 1 for each such string in the per-key counts.
- Totals: `agents` and `turns` count the runs of each kind; `skipped` the skipped lines.

### 5.3 Reading `events.md`

`<lessons>/events.md` is read once. Problems: when the file does not exist (or is not a file) the problem text is `events.md not found: no outcome signals.`; when it cannot be read, `events.md could not be read.` In both cases there are no events.

Split the text at `\n`; trim each line; ignore lines that do not start with `- `. Cut the rest after `- ` at ` | ` (a space, a vertical bar, a space) into at most 6 parts, so the 6th part keeps any further ` | `, and trim each part. A line is **bad** (counted in `bad`) when it has fewer than 5 parts, or part 1 is not `DDDD-DD-DD` (ASCII digits), or part 2, 3 or 5 is empty. For the others: the **month** is the first 7 characters of part 1; when it is before `from` or after `to` the line is ignored (not counted anywhere). The **signal** is part 3 lower-cased. The **work type** is part 4 cut at the first `·` (U+00B7), trimmed. When the work type equals `experiment` ignoring case and the signal is `repeated-failure` or `redone`, the line is an **expected iteration**: it adds 1 to `expected` and is not an event. Otherwise it is an **event**: `date` = part 1, `project` = part 2, `signal`, `role` = part 5 with the prefix `spanharness:` (ignoring case) removed when something follows it, and `main` = the role equals (ignoring case) one of `main`, `main conversation`, `orchestrator`. The 6th part (the fact) is not used.

### 5.4 Shared definitions

- **Day key** of a run or an event: its date, the lower-cased project, and for a role run (not main) `a` with the lower-cased role, for a main run `t` with no role. An event is **joined** to the runs (the runs with a date) that have the same day key; a run with no date can never be joined.
- **Number formats.** Counts are plain decimal integers with no thousands separators. `fmt1(x)` is `x` rounded half away from zero to 1 decimal, with a trailing `.0` dropped (`4.5`, `2500`, `0`; a result of zero is `0`, never `-0`). `fmt2(x)` is the same with 2 decimals and trailing zeros dropped (`0.57`, `0.2`, `1`). Money is `$` followed by the value rounded half away from zero to exactly 2 decimals (`$27.00`), except a value above 0 and below 0.01 (before rounding), which is `<$0.01`. All of this is computed with exact arithmetic (integers, fractions, or decimals), never through binary floating point. (Equivalent: take the shortest round-trip decimal string of the value and round that half up; the two agree for every value that occurs here.)
- **median(values)**: sort ascending; for an odd count the middle value; for an even count the mean of the two middle values. It is shown with `fmt1` (so an even count gives `.5` or a whole number).
- **quantile(values, q)** with q = 1/4, 1/2 or 3/4: sort ascending; `at = (n - 1) × q`; `low = floor(at)`; `high = min(low + 1, n - 1)`; the result is `sorted[low] + (sorted[high] - sorted[low]) × (at - low)` (exact). The median above is quantile 1/2.
- **spread(values)**: with fewer than 4 values the label `min–max` with the smallest and the largest value; with 4 or more the label `p25–p75` with quantile 1/4 and quantile 3/4. The text is `{label} {fmt1(low)}–{fmt1(high)}`, for example `p25–p75 2030–3770` or `min–max 500–500`. The dash in the label and between the numbers is the en dash U+2013.
- **stat(values)** gives three cells: when the list is empty `0`, `-`, `-`; else the count, `fmt1(median)`, and the spread text.
- **span(first, last)**: `-` when `first` is none; `first` when `first` = `last`; else `{first} – {last}` (space, en dash, space).
- **Cell escaping.** In a table cell, `|` becomes `\|`, and each `\r` and each `\n` becomes a space. This applies to every cell of every table (not to the bullet lines).
- **Row order**: each table names its order. Where it says "main first", the rows of the main conversation come before all others.

### 5.5 The sections, in order

Every `{…}` below is a value; everything else is literal. `\n` is a line break. A table is a header line, a separator line, and one line per row, each row `| ` + cells joined with ` | ` + ` |`.

#### Header

```
# Lessons record summary

- Period: {from} ~ {to} (last {months} month(s), this month included)
- Files read: {runs/NAME, … joined with ", " | none}
- Files that could not be opened: {NAME, … joined with ", "}
- Lines: role runs {agents} · main-conversation turns {turns} · harness changes {number of changes} · skipped lines {skipped} (not JSON, or unknown kind)
- Record times: {earliest t text} ~ {latest t text}
- Current harness fingerprint: {hash} ({n} files)
```

The `Files that could not be opened` line is written only when at least one file failed, and `Record times` only when at least one `t` was a timestamp. The names there have no `runs/` prefix. The current fingerprint is computed now from the files on disk (section 4, with the project folder resolved as in section 2, and the hook-input `cwd` not available); when it fails the line is `- Current harness fingerprint: unknown (cannot read {key})`.

Example. Input: `runs/2026-10.jsonl` has 3 `agent` lines, 1 `turn` line, 1 `harness` line, one line `{"t":"2026-10-07T10:00:00+09:00","kind":"mystery"}` and one broken line; the earliest `t` is `2026-10-02T10:00:00+09:00` and the latest `2026-10-08T10:00:00+09:00`; now is 2026-10-21; months 1. Output:

```
# Lessons record summary

- Period: 2026-10 ~ 2026-10 (last 1 month(s), this month included)
- Files read: runs/2026-10.jsonl
- Lines: role runs 3 · main-conversation turns 1 · harness changes 1 · skipped lines 2 (not JSON, or unknown kind)
- Record times: 2026-10-02T10:00:00+09:00 ~ 2026-10-08T10:00:00+09:00
- Current harness fingerprint: 006494ff (7 files)
```

#### Project × role

Heading `\n## Project × role\n\n`. With no run: `No role runs or turns recorded.\n`. Otherwise this paragraph, a blank line, and the table:

```
The role is the `agent` name; the main conversation comes from turn lines. Token columns are `median / total`; the tools, turns and ms columns are medians. Unreadable values (`null`) are left out of the counts; a total too large for 64 bits is shown as `-`.
```

Columns (13): `Project | Role | Count | Model | effort | in | out | cache_read | cache_write | tools | turns | ms | Read failures`; separator `|---|---|---|---|---|---|---|---|---|---|---|---|---|`.

One row per (kind, project, role), ordered by project, then main first, then role. Cells: project; role; count; models of the row in ordinal order joined with `, ` or `-`; efforts in ordinal order joined with `, ` or `-`; for `in`, `out`, `cache_read`, `cache_write`: `-` when the list is empty, else `{fmt1(median)} / {sum}` where `sum` is `-` when it does not fit 64 bits; for `tools`, `turns`, `ms`: `-` when empty, else `fmt1(median)`; the unread count.

Example. Input runs (`in out cache_read cache_write tools turns ms`): alpha/coder ×4 in 2026-10 and 2026-09 with models `claude-opus-4-1-20250805` (×2: in 200 and 400) and `claude-sonnet-4-5-20250929` (×2: in 100 and 300), effort `high`, out 20 40 10 30, cache_read 2000 4000 1000 3000, cache_write 100 200 50 150, tools 6 10 4 8, turns 4 6 3 5, ms 2000 4000 1000 3000; one alpha `turn` (model `claude-opus-4-1-20250805`, effort `medium`, 50 5 500 25 1 1 250); a beta `reviewer` with `model` and `in` null and `missing` = `["model","in"]` (out 7, cache_read 700, cache_write 70, tools 2, turns 1, ms 500); a `doc-writer` in project `we|rd`. Output:

```
| Project | Role | Count | Model | effort | in | out | cache_read | cache_write | tools | turns | ms | Read failures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| alpha | main conversation | 1 | claude-opus-4-1-20250805 | medium | 50 / 50 | 5 / 5 | 500 / 500 | 25 / 25 | 1 | 1 | 250 | 0 |
| alpha | coder | 4 | claude-opus-4-1-20250805, claude-sonnet-4-5-20250929 | high | 250 / 1000 | 25 / 100 | 2500 / 10000 | 125 / 500 | 7 | 4.5 | 2500 | 0 |
| beta | reviewer | 1 | - | - | - | 7 / 7 | 700 / 700 | 70 / 70 | 2 | 1 | 500 | 1 |
| we\|rd | doc-writer | 1 | claude-sonnet-4-5-20250929 | - | 10 / 10 | 1 / 1 | 100 / 100 | 10 / 10 | 0 | 1 | 100 | 0 |
```

(The doc-writer line has in 10, out 1, cache_read 100, cache_write 10, tools 0, turns 1, ms 100, model `claude-sonnet-4-5-20250929`, no effort.)

#### Role × harness version

Heading `\n## Role × harness version\n\n`. With no run: `No role runs or turns recorded.\n` and no further text in this section (no comparisons). Otherwise this paragraph, a blank line, and the table:

```
Runs grouped by role and the harness fingerprint written on each run (all projects together), oldest version of a role first. Tokens = in + out + cache_read + cache_write of one run; time = ms. A run with an unread value is left out of that column's n. Spread is min–max when n < 4 and p25–p75 when n ≥ 4. The runs are different tasks, so this is observation, not a controlled test. The fingerprint covers the whole setup: a change may come from a file other than the role's own (see Harness changes).
```

Columns (10): `Role | Harness | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread`; separator `|---|---|---|---|---|---|---|---|---|---|`.

A **version** is the runs with the same (kind, role, harness), all projects together. Its first and last sequence numbers are those of its runs. Rows: main first, then by role, then by first sequence number (oldest version first). Cells: role; harness; the number of runs; span(earliest date, latest date) over the runs that have a date (ordinal comparison); stat of `tokens` over the runs where it is not null; stat of `ms` over the runs where it is not null.

Example. Input: `coder` runs under `aaaa1111` on 2026-10-01..05 with tokens 1000 1100 1200 1300 1400 and ms 1000 1100 1200 1300 1400; under `bbbb2222` on 2026-10-06..10 with tokens 2000..2400 and ms 3000..3400; one `reviewer` run under `aaaa1111` on 2026-10-01 with tokens 900 and ms 400. Output:

```
| Role | Harness | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread |
|---|---|---|---|---|---|---|---|---|---|
| coder | aaaa1111 | 5 | 2026-10-01 – 2026-10-05 | 5 | 1200 | p25–p75 1100–1300 | 5 | 1200 | p25–p75 1100–1300 |
| coder | bbbb2222 | 5 | 2026-10-06 – 2026-10-10 | 5 | 2200 | p25–p75 2100–2300 | 5 | 3200 | p25–p75 3100–3300 |
| reviewer | aaaa1111 | 1 | 2026-10-01 | 1 | 900 | min–max 900–900 | 1 | 400 | min–max 400–400 |
```

##### Version comparisons

Heading `\n### Version comparisons\n\n`, then this paragraph and a blank line:

```
For each role whose latest harness version differs from the previous one. A difference is printed as a finding only when both sides have n ≥ 5 and the spreads do not overlap; otherwise it is labelled noise / inconclusive and no difference is given.
```

Take the versions whose harness is not `(unknown)`, grouped by (kind, role) in the order of the table above. A group with fewer than 2 versions is skipped. In a group the **latest** is the version with the largest last sequence number, and the **previous** the one with the largest last sequence number among the others. For each group one line:

```
- {role}: {previous harness} → {latest harness} | runs {previous runs} → {latest runs} | tokens {compare(previous tokens, latest tokens)} | time (ms) {compare(previous times, latest times)}
```

followed by ` | applied by {log entry}` when the log (5.8) has an entry for the latest harness. When no group was written: `none: no role has two harness versions in this period.\n`.

`compare(previous, latest)` where both are the lists of values of the versions:

- when either list is empty: `not measured (no readable value on the previous side)` if the previous list is empty, else `… on the latest side)`;
- else `head` = `median {fmt1(median of previous)} (n={count}) → {fmt1(median of latest)} (n={count}): `. Reasons: `n < 5` when either count is below 5; `spreads overlap` when the spreads (ranges `low`–`high` of `spread`) satisfy `low₁ ≤ high₂` and `low₂ ≤ high₁`. With reasons: `head` + `noise / inconclusive (` + the reasons joined with `; ` + `)`. Without: `head` + `finding, median difference ` + `+` if latest median > previous median, then `fmt1(latest median - previous median)`.

Example (same input as above, plus 5 `reviewer` runs under `bbbb2222` with tokens and ms 5000, 5050, 5100, 5150, 5200, read after all the other runs; the log has `- 2026-10-06 | 2026-10-06-1.md#2 | agents/coder.md | shorter | passed | bbbb2222`):

```
- coder: aaaa1111 → bbbb2222 | runs 5 → 5 | tokens median 1200 (n=5) → 2200 (n=5): finding, median difference +1000 | time (ms) median 1200 (n=5) → 3200 (n=5): finding, median difference +2000 | applied by 2026-10-06 2026-10-06-1.md#2
- reviewer: aaaa1111 → bbbb2222 | runs 1 → 5 | tokens median 900 (n=1) → 5100 (n=5): noise / inconclusive (n < 5) | time (ms) median 400 (n=1) → 5100 (n=5): noise / inconclusive (n < 5) | applied by 2026-10-06 2026-10-06-1.md#2
```

#### Role × model

Heading `\n## Role × model\n\n`. With no run: `No role runs or turns recorded.\n` and nothing else (no cost section either). Otherwise two paragraphs, each followed by a blank line:

```
Runs grouped by role and the model written on each run (all projects and harness versions together): the main conversation's model changes per session, so the harness fingerprint alone mixes models. Model ids that differ only in case are one row (shown in lower case). Columns as in the harness table: tokens = in + out + cache_read + cache_write of one run, time = ms; a run with an unread value is left out of that column's n; spread is min–max when n < 4 and p25–p75 when n ≥ 4. A run without a model is listed as `(model unknown)`. The runs are different tasks, so this is observation, not a controlled test.
```

```
The signal columns count the `events.md` events of that role × model (see Outcome signals for the signals). An event is joined to the runs of the same date + project + role (case does not matter; `main` is the main conversation) and counted under the model of those runs, whatever the harness version. When the runs it matches that day used more than one model, the model is not guessed: the event is counted in no row and shows in the `Ambiguous model` line under the table. An event with no run to match is not here either (it is counted under Outcome signals). `other signals` sums signal words with no column of its own. `repeated-failure` and `redone` with work type `experiment` are expected iterations and are left out; the other signals with that work type are counted. Events are self-reported, so the counts are a lower bound. `Cost n` is the number of runs the cost adds up (a run with any unread token value is left out), and the cost uses the prices and rules of the cost table below; `-` for a model with no known price or a token total that does not fit in 64 bits.
```

Columns (18): `Role | Model | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread | fix-request | review-block | review-wrong | repeated-failure | redone | other signals | Cost n | Approx. cost (USD)`; separator `|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|`.

Rows: one per (kind, role, model) over all runs, where the model is the run's `model` or `(model unknown)`; ordered main first, then role, then model. Cells: role; model; runs; span of the dates; stat of `tokens`; stat of `ms`; the five signal counts; `other signals`; `Cost n` = the number of runs in the row whose four counts are all not null; the cost (below).

**Signal counts.** For every event (5.3), find the runs with its day key. No runs: the event is not counted here. Otherwise take the distinct (kind, role, model-or-`(model unknown)`) of those runs (the role exact, not lower-cased): if there is exactly one, the event counts for that row under its signal; if more than one, the event is **ambiguous** and counts under its signal in the ambiguity total. A row's `other signals` is the sum over its signals that are none of the five columns. When `events.md` has a problem (5.3), every signal cell, and `other signals`, is `-`.

**Cost of a set of runs** (a row, or a model's runs): take the runs whose four counts are all not null. Let `sum_in`, `sum_out`, `sum_cache_read`, `sum_cache_write` be the sums of each count over them (each by sum(): null when it does not fit 64 bits). The cost is `-` when the model has no price (5.9), or no run is left, or any of the four sums is null. Otherwise `money = (sum_in × price.input + sum_out × price.output + sum_cache_read × price.cache_read + sum_cache_write × price.cache_write_5m) / 1000000` (exact decimal arithmetic), shown as in 5.4.

After the table, a blank line, then:

- no problem with `events.md`: `- Ambiguous model: {total} event(s) matched runs of more than one model that day, so they are in no row above` followed by ` ({signal} {count} · {signal} {count})` when the total is above 0 (signals in ordinal order), then `\n`;
- with a problem: ``- Signal columns show `-`: {problem text}`` and `\n`.

Example. Input (all in 2026-10, alpha, `high`; `in` is the only non-zero count; all four counts are read unless noted): coder/`claude-opus-5-5` on 10-02, 10-04, 10-05 (spelt `Claude-Opus-5-5`) and 10-06 (project beta), 1000000 each; coder/`claude-sonnet-5-5` on 10-03, 10-04 and 10-09 (the last with `in` null), 1000000 each; a `turn` with `claude-opus-5-5` on 10-07; a reviewer with `claude-mystery-9-9` on 10-08; `events.md`:

```
- 2026-10-02 | alpha | fix-request | refactor · small | coder | user: wanted a rename
- 2026-10-02 | Alpha | Review-Block | feature · large | CODER | reviewer blocked
- 2026-10-02 | alpha | surprise | feature · small | coder | a signal word with no column of its own
- 2026-10-03 | alpha | fix-request | docs · small | coder | user: asked for a fix
- 2026-10-04 | alpha | fix-request | docs · small | coder | two models that day
- 2026-10-04 | alpha | redone | docs · small | coder | two models that day
- 2026-10-05 | alpha | review-wrong | experiment · small | coder | the finding was not a problem
- 2026-10-06 | beta | fix-request | docs · small | coder | another project, the same model row
- 2026-10-07 | alpha | fix-request | chat · small | main | user: asked again
- 2026-10-08 | alpha | repeated-failure | docs · small | reviewer | a model with no known price
```

Output (`ms` is 100 for every run):

```
| Role | Model | Runs | First – last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread | fix-request | review-block | review-wrong | repeated-failure | redone | other signals | Cost n | Approx. cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| main conversation | claude-opus-5-5 | 1 | 2026-10-07 | 1 | 1000000 | min–max 1000000–1000000 | 1 | 100 | min–max 100–100 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | $4.00 |
| coder | claude-opus-5-5 | 4 | 2026-10-02 – 2026-10-06 | 4 | 1000000 | p25–p75 1000000–1000000 | 4 | 100 | p25–p75 100–100 | 2 | 1 | 1 | 0 | 0 | 1 | 4 | $16.00 |
| coder | claude-sonnet-5-5 | 3 | 2026-10-03 – 2026-10-09 | 2 | 1000000 | min–max 1000000–1000000 | 3 | 100 | min–max 100–100 | 1 | 0 | 0 | 0 | 0 | 0 | 2 | $4.00 |
| reviewer | claude-mystery-9-9 | 1 | 2026-10-08 | 1 | 1000000 | min–max 1000000–1000000 | 1 | 100 | min–max 100–100 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | - |

- Ambiguous model: 2 event(s) matched runs of more than one model that day, so they are in no row above (fix-request 1 · redone 1)
```

(The 10-04 events are ambiguous because opus and sonnet coder runs both happened that day; the 10-05 `review-wrong` has work type `experiment` and still counts, because only `repeated-failure` and `redone` are expected iterations.)

##### Approximate cost per model

Heading `\n### Approximate cost per model\n\n`, then this paragraph (`{as_of}` is the `as_of` of `prices.json`, or `unknown`) and a blank line:

```
Approximate: tokens × list price (USD per million tokens as of {as_of}), summed per model over all projects and roles; the cost column of the role × model table above splits the same sum by role. Cache writes are priced at the 5-minute rate because the 1-hour split is not recorded. Haiku 5.5 is priced at the rate for prompts up to 100K tokens, so its cost is a lower bound. A model id is matched by family and version (`claude-opus-5-5`, with or without a date or `[1m]` after it); an id with no known price shows `-`, never a guess, and so does a model with no run to count or a token total that does not fit in 64 bits. A run with any unread token value is left out of the cost and counted under `Left out`.
```

Columns (6): `Model | Priced as | List price per M tokens (in / out / cache write / cache read) | Runs | Left out | Approx. cost (USD)`; separator `|---|---|---|---|---|---|`.

One row per model (the lower-cased model, or `(model unknown)`), in ordinal order of the model. Cells: the model; the price entry's `name` or `-`; `-` when there is no price, else the four prices `input / output / cache_write_5m / cache_read` each written with up to 3 decimals and no trailing zeros (`4 / 20 / 5 / 0.2`, `0.1 / 0.5 / 0.125 / 0.01`) joined with ` / `; the number of runs; the runs left out (the runs whose four counts are not all read); the cost of the model's runs.

Example (the input above plus a `claude-haiku-5-5` run with 10000000 in, 1000000 out, 100000000 cache_read and 4000000 cache_write):

```
| Model | Priced as | List price per M tokens (in / out / cache write / cache read) | Runs | Left out | Approx. cost (USD) |
|---|---|---|---|---|---|
| claude-haiku-5-5 | Haiku 5.5 | 0.1 / 0.5 / 0.125 / 0.01 | 1 | 0 | $3.00 |
| claude-mystery-9-9 | - | - | 1 | 0 | - |
| claude-opus-5-5 | Opus 5.5 | 4 / 20 / 5 / 0.2 | 5 | 0 | $20.00 |
| claude-sonnet-5-5 | Sonnet 5.5 | 2 / 10 / 2.5 / 0.1 | 3 | 1 | $4.00 |
```

(Haiku: (10000000 × 0.1 + 1000000 × 0.5 + 100000000 × 0.01 + 4000000 × 0.125) / 1000000 = 1 + 0.5 + 1 + 0.5 = 3.00.)

#### Outcome signals (events.md)

Heading `\n## Outcome signals (events.md)\n\n`. When `events.md` has a problem, the section is only the problem text and `\n`. Otherwise:

For every event find the runs with its day key. None: counted in `no_run`. Otherwise the distinct versions (5.5 Role × harness version) of those runs: more than one: counted in `changed_day`; exactly one: counted in `joined` and in that version's signal counts under the event's signal.

Then this paragraph and a blank line:

```
events.md is written by the orchestrator about its own work, so these counts are a lower bound, not everything that went wrong. Each event is joined by date + project + role (case does not matter; `main` is the main conversation) to the harness version of that role's runs that day. Per run = events of that signal / runs of that role under that version. A `repeated-failure` or `redone` event whose work type is `experiment` is an expected iteration, not a harness failure: it is left out of the counts and rates here and shown on a line of its own. The other signals (`fix-request` · `review-block` · `review-wrong`) with work type `experiment` are harness signals and are counted as usual.
```

When `joined` > 0, a table and a blank line. Columns (6): `Role | Harness | Runs | Signal | Events | Per run`; separator `|---|---|---|---|---|---|`. One row per (version, signal) for the versions that have signals, versions in the order of the Role × harness version table, signals in ordinal order. Cells: role; harness; the number of runs of the version; the signal; the count; `fmt2(count / runs)`.

Then three bullets:

```
- Events in the period: {number of events} · joined to a harness version {joined} · no run of that role in that project that day {no_run} · harness changed that day, so not attributed {changed_day}
- Expected experiment iterations (`repeated-failure` · `redone` with work type `experiment`; not in the counts above): {expected}
- Lines starting with `- ` that are not in the format (`- YYYY-MM-DD | project | signal | work type · size | role | fact`): {bad}
```

Example. Input: the runs of the Role × model example (all with harness `a1b2c3d4`; 7 coder runs, 1 main run, 1 reviewer run), and `events.md` as there plus these three lines:

```
- 2026-10-03 | alpha | redone | experiment · small | coder | an expected iteration
- 2026-10-12 | alpha | fix-request | docs · small | coder | no coder run that day
- not a date | alpha | fix-request | docs · small | coder | not in the format
```

Output:

```
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
```

#### Read failures

```

## Read failures

- Lines with unread keys: {unread} / {agents + turns} (role-run and turn lines whose `missing` is not empty)
- Unread keys: {key} {count} · {key} {count}
```

The keys are in ordinal order, or the word `none` when there are none. (`unread` is the total of 5.2.) Example: two of 8 lines have `missing` `["model","in"]` and `["ms"]`:

```
- Lines with unread keys: 2 / 8 (role-run and turn lines whose `missing` is not empty)
- Unread keys: in 1 · model 1 · ms 1
```

#### Harness changes

Heading `\n## Harness changes\n\n`. With no change: `none\n`. Otherwise one line per change in reading order:

```
- {when | (time unknown)} | {prev | (first)} → {hash | ?} | changed {a, b} | added {a, b} | removed {a, b} | plugin {version}
```

The parts `changed`, `added`, `removed` appear only when their list is not empty (the files joined with `, `); `plugin {version}` only when the line has a `plugin_version`. Parts are joined with ` | `. The last line of the report ends with `\n`. Example: `- 2026-10-03T09:12:00+09:00 | a1b2c3d4 → e5f6a7b8 | changed agents/coder.md | added output-styles/x.md | plugin 0.1.1`.

### 5.6 Section order

Header; Project × role; Role × harness version (with Version comparisons); Role × model (with Approximate cost per model); Outcome signals (events.md); Read failures; Harness changes.

### 5.7 Exit and output

`report` writes the text of 5.5 and exits per section 2.

### 5.8 `harness-log.md`

Read `<lessons>/harness-log.md` (UTF-8, a leading byte order mark skipped), split at `\n`, trim each line; keep the lines that start with `- `; cut the rest at ` | ` (no limit on the number of parts); a line with 6 or more parts gives an entry keyed by its **last** part, trimmed; the value is part 1 trimmed + a space + part 2 trimmed (`2026-10-06 2026-10-06-1.md#2`). The first line for a key wins (a later line with the same fingerprint, a change to the plugin files that left the fingerprint as it was, did not make that version). A file that does not exist or cannot be read gives no entries.

### 5.9 Prices

`scripts/prices.json` is a JSON object with `as_of` (a `YYYY-MM-DD` string), `unit` (informational), and `models`, an object of entries keyed by `family-major-minor`, for example `opus-5-5`. An entry has `name` (string), `input`, `output`, `cache_read` and `cache_write_5m` (USD per million tokens, JSON numbers read as exact decimals, not as binary floats), and optionally `note`, which is for the maintainer and is not used. Prices are list prices; cache writes are at the 5-minute rate.

**Matching a model id to an entry.** Trim the id and lower-case it. It must match the regular expression

```
^claude-(fable|opus|sonnet|haiku)-([0-9]+)-([0-9]{1,2})(?=$|[-\[@\s])
```

(`$` is the end of the string; `\s` is whitespace as in section 0; ASCII digits only). The key is `{family}-{major}-{minor}` from the three groups, as written (no leading zeros are removed). The entry is `models[key]`; when the id does not match, or there is no such entry, the model has no price. Examples: `claude-opus-5-5[1m]` → `opus-5-5`; `claude-sonnet-5-5-20261001` → `sonnet-5-5`; `claude-haiku-4-5-20251001` → `haiku-4-5`; `claude-opus-4-1-20250805` → key `opus-4-1`, no entry, no price; `claude-opus-4-20250514` → no match; `claude-mystery-9-9` → no match. A price is never guessed from a nearby version.

## 6. Implementation rules

1. **Runtime.** The Python implementation uses Python 3.8 or newer and only the standard library. The PowerShell implementation runs on Windows PowerShell 5.1 and on PowerShell 7, uses only what ships with them, and `scripts/spanharness.ps1` is pure ASCII: characters such as `·`, `–`, `→`, `×`, `≥` and `—` are built from code points (for example `[char]0x00B7`). A lint rule enforces this. Node is not used.
2. **Text I/O is UTF-8.** Read stdin as bytes (`[Console]::OpenStandardInput()` in PowerShell, `sys.stdin.buffer` in Python). Every text file read (settings files, agent, skill and style files, `plugin.json`, `prices.json`, state files, `events.md`, `harness-log.md`, `runs/` files, transcript lines, lint targets) is read as bytes, a leading UTF-8 byte order mark is removed, and the rest is decoded as UTF-8 with invalid bytes replaced by U+FFFD (Python `errors="replace"`; .NET `new UTF8Encoding($false)` without throwing). A transcript is read in lines, and the byte order mark is removed from the first line of the file only (3.3). Never rely on a platform default encoding or on a reader that removes or keeps the byte order mark on its own. A JSON string can hold a lone surrogate (an escape such as `\ud83d` without its partner; Claude Code writes these when it cuts a string in the middle of a pair). That is valid input: the line is kept, and the string is compared and counted as it is. When such a string is written to a file it becomes U+FFFD (one for each lone surrogate), in both implementations (Python: an error handler of the encoder; .NET: the replacement of `UTF8Encoding`). Write files as UTF-8 without a byte order mark and with `\n` line ends, never through a text mode that changes line ends. Hash bytes as in 4.1.
3. **JSON nesting.** A nesting level is one object or array: `{}` and `[]` are depth 1, `[[1]]` and `{"a":[]}` are depth 2; scalars add nothing. Where this document gives a nesting limit (100 for hook input and `runs/` lines, 200 for transcript lines), both implementations check the depth themselves with an explicit pass over the parsed value (or the text) and treat a deeper value as a parse failure; the parser's own recursion limit is set high enough never to trigger first.
4. **JSON input.** Python: `json.loads` with `parse_constant` rejecting `NaN`, `Infinity` and `-Infinity`. PowerShell: `System.Web.Script.Serialization.JavaScriptSerializer` with `MaxJsonLength = [int]::MaxValue` (and a recursion limit that allows the nesting limits in 3.2 and 5.2); `ConvertFrom-Json` MUST NOT be used, because transcripts exceed its 2 MB limit. A transcript line is not converted to dictionaries on PowerShell 7 either: only the few fields that 3.3 reads are taken from the parsed line (a line has hundreds of nodes, and one call per node is slow in PowerShell). The input must be JSON as RFC 8259 defines it, and nothing else: `NaN`, `Infinity`, single quotes, names without quotes, a leading `+`, `.5`, `5.`, leading zeros, a trailing comma, comments, a raw control character in a string, white space other than space, tab, line feed and carriage return, and text after the first value are all parse failures. A duplicate key keeps the last value. Integers read from JSON are exact (no float for integers). The serializer of Windows PowerShell 5.1 accepts all of the above, turns a string such as `\/Date(5)\/` into a date and a lone surrogate escape into U+FFFD, so the PowerShell implementation checks the text before it gives it to the serializer (with regular expressions only: it reduces the text to its tokens and the tokens to a single value, one nesting level for each pass; this also enforces the nesting limit) and reads a text that holds a string of that form or any surrogate escape (`\uD800` to `\uDFFF`) with its own reader, so that such a string stays as it is. PowerShell 7 (System.Text.Json) and Python are strict already.
5. **JSON output.** Output is what Python's `json.dumps(obj, ensure_ascii=False, separators=(",", ":"))` produces, with the keys in the order of this specification. Strings escape `"` as `\"`, `\` as `\\`, and the control characters U+0008, U+000A, U+000C, U+000D, U+0009 as `\b`, `\n`, `\f`, `\r`, `\t`; every other character below U+0020 is `\u00xx` with 4 lowercase hex digits; all other characters, including `/`, `<`, `>`, `&`, `'`, U+007F, U+2028 and non-ASCII text, are written as they are. Integers are plain decimal; `null`, `true`, `false` are lowercase. PowerShell uses a small hand-written writer and MUST NOT use `ConvertTo-Json`, which escapes `<`, `>`, `&` and `'` and formats numbers by culture.
6. **Culture.** Every number and date is formatted and parsed with the invariant culture. In PowerShell, set `[System.Threading.Thread]::CurrentThread.CurrentCulture` to the invariant culture at start-up. Never use a culture-sensitive comparison, sort, `ToUpper` or `ToLower`.
7. **Sorting** is ordinal (section 0) everywhere. PowerShell: never `Sort-Object` with its default comparer; use `[System.StringComparer]::Ordinal`. Case-insensitive comparisons are done on `lower()` / `ToLowerInvariant()` of both sides.
8. **Rounding** is as in 5.4: half away from zero, on exact values. Money is computed in decimal (`decimal.Decimal` in Python with enough precision, `[decimal]` or `[System.Numerics.BigInteger]` in PowerShell), not in binary floating point. Tokens are 64-bit integers; sums and the range checks of section 0 are done exactly. The conformance fixtures include rounding ties (`0.15`, `2.5`, `0.125`, `0.285`).
9. **Time.** `t` is local time `yyyy-MM-ddTHH:mm:sszzz` (Python: `datetime.now().astimezone().isoformat(timespec="seconds")`). The month file and the report period use the local date. `--now` replaces the clock (section 2).
10. **Locking** as in 3.7.
11. **`record` always exits 0**, prints nothing on stdout, and writes failures to `errors.log` (3.6). When stdin is a terminal it prints usage to stderr and exits 0.
12. **Opt-out.** `SPANHARNESS_RECORD=0` makes `record` exit 0 at once (3.1). It can be set in the `env` of `settings.json`.
13. **Both implementations are checked against the same fixtures** (`tests/fixtures/cases/<case>/`): the output files are compared byte for byte, except `errors.log` (3.6) and the `lock` file. A change to this specification MUST come with a fixture.

## 7. Changes from the previous recorder

For the maintainer. These are the places where this specification differs from the recorder that wrote the existing data. Old `runs/*.jsonl` lines stay readable by `report`.

1. Commands: `--record` is `record`, `--lessons-report` is `report`; `--home DIR` is replaced by `--claude-dir`, `--lessons-dir` and `--plugin-root`; `lint` is new. The lessons folder honours `$CLAUDE_CONFIG_DIR`. `--preview` is gone.
2. The hook is one synchronous handler, so `record` must be fast. The 10-second stdin thread is replaced by a terminal check (no timeout). `SPANHARNESS_RECORD=0` is a new opt-out. The stability wait (size unchanged for 500 ms, at most 3 s) is replaced by a wait for a complete last line (at most 1 s, usually none), because the hook is no longer asynchronous.
3. The previous recorder's status file in `state/` (line counters and registration data) is no longer written, and no `README.md` is written to the lessons folder; this document replaces it. Hook registration in `settings.json` is gone (the plugin's `hooks/hooks.json` does it).
4. Fingerprint inputs changed (section 4): the keys are `plugin/agents/…`, `plugin/output-styles/…`, `plugin/skills/…/SKILL.md`, `skills/<name>/SKILL.md` (for the plugin agents' preloads), `output-style`, a custom style file, and `CLAUDE.md`. Agents in `~/.claude/agents` are no longer part of it. The first record after the switch therefore writes a `harness` line that lists every key as added. `output-style` is now always present; a custom style file adds its key besides it (before, a style file replaced the `output-style` key). The active style is resolved through project local settings, project settings and user settings (before: user settings only). The file hash drops a byte order mark and is taken over bytes (before: over decoded text; the same for valid UTF-8).
5. The `harness` line has a new last key `plugin_version`, and `state/harness.json` stores it. A change of the plugin version alone now writes a `harness` line (with empty `changed`, `added` and `removed`).
6. `agent_type` is recorded as the hook gives it (`spanharness:<name>`). `role_model` and `role_effort` are read from the plugin's agent file for `spanharness:<name>` and otherwise from the project and user agent folders, matched by file name (before: matched by the `name` key among the enabled roles). `effort` is the `level` string of the hook's `effort` object, as before.
7. Report: a leading `spanharness:` is removed from record roles and from `events.md` roles before grouping and joining. The main-conversation names are `main`, `main conversation` and `orchestrator` (a non-English alias for the main conversation is dropped).
8. Prices are read from `scripts/prices.json` instead of being compiled in; the date in the cost text comes from its `as_of`. The cost text itself is unchanged, so the Haiku 5.5 sentence in it must be edited together with that entry if its price rule changes.
9. JSON is written without escaping `<`, `>`, `&` and `'` (the previous serializer wrote them as `<` and so on). Both forms parse to the same values.
10. Numbers in the report are formatted from exact values. The previous recorder went through binary floating point with 15 significant digits, so medians and spreads above 10^15 could lose digits; below that the output is identical. Negative token counts are not valid input and their formatting is not specified.
11. The lock is a lock on `state/lock` instead of a named mutex. A failed record write is retried 5 times as before.
12. `errors.log` lines are English with fixed `what` texts (3.6), end with `\n` on every system, and report the size of a bad input in bytes (before: characters). The 256 KB rotation is unchanged.
13. The 30-day clean-up of read positions uses the `--now` clock when it is given.
14. Timestamps: the grammar of section 0 is strict, a timestamp without an offset is read as UTC (before: local time), and other forms the previous parser accepted are ignored. Transcripts and records use the ISO form with an offset, so real data is not affected.
15. Frontmatter reading is limited to what is used (4.3): block scalars are not supported.
16. `harness-log.md` lines and proposals are no longer tied to one language, and the marker of an applied proposal item is `applied YYYY-MM-DD` (before: a word in another language). The report reads `harness-log.md` as before.
17. Lines of `runs/*.jsonl` are split only at `\n`, `\r\n` and a lone `\r`; a file name ending in `.JSONL` is accepted as `.jsonl`.
18. All messages of `report` (usage, errors) are English; the report prints the output path on stdout as before.
19. A read error partway through a transcript now counts nothing and keeps the given offset (before: the counts and the offset reached before the error were kept), so both implementations agree on a rare case.
20. All text files are read the same way (byte order mark removed, invalid UTF-8 replaced), and frontmatter lines drop a trailing `\r` (6.2, 4.3), as before; this is now written down.
21. The transcript summary is made outside the lock; the lock covers the commit only, and a record whose saved position was moved meanwhile sums up again (3.2 steps 9 to 12, 3.7). Before, one lock covered the whole record, so records of long transcripts made the others wait for 10 s and give up.
22. A transcript that is not a regular file is unreadable, and no byte after the length seen at the start is read (3.3).
23. The byte order mark of a transcript is removed from the first line of the file only; before, the Python implementation removed it from every line. A saved `plugin_version` that is not a non-blank string counts as null (3.2 step 15). Lone surrogate escapes are valid input and are written as U+FFFD (6.2). The PowerShell implementation on 5.1 accepts only strict JSON (6.4), writes no path to `errors.log` (3.6), and checks the command line after the terminal guard and reports a bad one on stderr, as the Python implementation does (3.1).
