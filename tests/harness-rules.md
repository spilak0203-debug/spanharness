# harness-rules.json: rule semantics

`tests/harness-rules.json` is a data-driven list of lint rules over the plugin's content files. `scripts/spanharness.py lint` and `scripts/spanharness.ps1 lint` must apply it identically. Same rules, same ids, same pass/fail. Failure message wording is free.

## File format

```
{ "version": 1,
  "groups": { "core": "...", "later": "..." },
  "rules": [ { "id": "...", "kind": "...", "group": "later", ... }, ... ] }
```

- The file is UTF-8 without BOM and pure ASCII (non-ASCII characters are `\uXXXX` escapes), so any reader can load it.
- `id`: unique, stable, `[a-z0-9.-]+`. Never reuse or rename an id; tests and negative fixtures refer to it.
- `group`: optional, default `core`. A rule runs only when its group is enabled. The runner enables `core` by default and takes extra groups from its caller (e.g. `--group later`). A group name that is not in `groups` is an error. Skipped rules are only counted.
- Output: one line per failure that starts with `FAIL <id>`, then the file path and a reason. Exit 0 when nothing failed, 1 otherwise.

## Common rules

- Paths are relative to the plugin root, with `/` separators, case-sensitive. The candidate set is every regular file under the root except `.git/`.
- Text rules read the file as UTF-8 (a BOM is dropped; invalid UTF-8 is a failure of that rule for that file), then turn CRLF and lone CR into LF. All literals below are compared on that normalized text, so rules never contain `\r`.
- Glob (`paths`, `exclude`): `*` is any run of characters except `/`; a whole segment `**` is any number of directories (`dir/**` = every file below dir; `a/**/b.md` also matches `a/b.md`). No `?`, no classes.
- Target resolution for every kind except `files`: targets = files matching `paths` minus files matching `exclude`. The rule is applied to each target on its own, and fails if any target fails.
- Missing files: a `paths` entry without `*` that does not exist is a failure of the rule. A pattern with `*` may match nothing, but if the whole target set is empty the rule fails ("no files match"). So a rule never passes by checking nothing.
- Per kind, existence is decided as follows: only the `files` kind exists to test existence. Every other kind fails when a literal path is missing. To cover files that don't exist yet, put the rule in group `later` (see the end). Exception: `mustNotContain` rules use wildcard scopes (`scripts/**/*.py`, `hooks/**`), so they pick up scripts and hooks as soon as they exist and need no group.

## Kinds

Optional on every text kind below (`contains`, `containsOnce`, `mustNotContain`): `section` is a heading line such as `## Workflow`. The rule then looks only at that section: the heading line itself and the lines up to, not including, the next line that starts with `## ` (or the end of the file). The heading must occur exactly once as a whole line, else the rule fails.

| kind | fields | passes when |
|---|---|---|
| `files` | `paths` (literal list) or `dir` + `only` | `paths`: every path is an existing regular file. `dir`+`only`: the regular files directly in `dir` are exactly the names in `only`; no extra, none missing. Entries starting with `.` are ignored, and subdirectories don't count. |
| `frontmatter` | at least one of `keys`, `equals`, `absent`, `nonEmpty` | see below |
| `sectionsInOrder` | `sections` (full heading lines), `exact` (bool, default false) | the file's level-2 headings are the lines starting with `## `. Without `exact`, the listed headings each equal a heading line of the file and appear in that order (other headings may sit between). With `exact`, the file's headings are exactly the list. |
| `contains` | `text` or `texts` (all of them) | each literal occurs at least once |
| `containsOnce` | `text` or `texts` | each literal occurs exactly once (non-overlapping, scanning left to right) |
| `endsWithLine` | `line` | the normalized text ends with `"\n" + line + "\n"` and has no further trailing newline, so `line` is the whole last line and there are no trailing blank lines |
| `mustNotContain` | `text` or `regex`, optional `ignoreCase` | the literal does not occur / the regex does not match anywhere |
| `asciiOnly` | none | every raw byte is 0x09, 0x0A, 0x0D or 0x20-0x7E (so no BOM, no non-ASCII) |
| `json` | `path` and one of `equals`, `anyContains` | see below |

Literals are matched as ordinal substrings, case-sensitive. They may contain `\n`; a leading and trailing `\n` makes a literal match whole lines. `ignoreCase` makes the match ASCII case-insensitive (only used with ASCII patterns).

### frontmatter

- The file must start with a line `---`; the frontmatter ends at the next line that is exactly `---`. Between them: blank lines are skipped; `key: value` (key `[A-Za-z0-9_-]+`, the colon, one optional space and the rest of the line); and, after a `key:` with an empty value, list items `  - item` (one or more spaces, `- `, the item). Anything else, or a duplicate key, is a parse failure of the rule. No comments, no nesting, no multi-line values, no full YAML.
- A scalar value is the rest of the line trimmed; if it begins and ends with `"` those two characters are removed (nothing inside is unescaped). A list value is the list of its trimmed items (quotes removed the same way). A key with an empty value and no items is the empty string.
- `keys`: the top-level keys, in file order, equal this list exactly (checks order and rules out extra keys).
- `equals`: object `key: value`. The key must exist and its value must equal: a JSON string compares to a scalar, a JSON array of strings to a list.
- `absent`: none of these keys exist.
- `nonEmpty`: each key exists and is not the empty string or an empty list.

### json

The file is strict JSON (BOM dropped). `path` is dot-separated segments: an object key, a decimal array index, or `*` (every element of an array / every value of an object). A segment that doesn't fit the node yields nothing. The path resolves to a list of values (possibly empty).
- `equals` (the path must not contain `*`): exactly one value is found and it equals the given JSON value, with the same type (string vs number vs bool).
- `anyContains`: at least one resolved value is a string that contains the given literal.

### Regex

`regex` is searched (not anchored) in the normalized text or the section. The flavour is the common subset of Python `re` and .NET `System.Text.RegularExpressions`: literal characters and escaped metacharacters, `.` (never matches `\n`), character classes with ranges and `\uXXXX` (4 hex digits, BMP only), groups `( )` and `(?: )`, alternation `|`, `* + ? {m,n}`, and negative lookahead `(?!...)`. Do not use `^`, `$`, `\b`, `\d`, `\w`, `\s`, named groups, lookbehind, or inline flags. No regex options except IgnoreCase (via `ignoreCase`); .NET must use CultureInvariant. A match anywhere fails the rule.

## Groups

Every rule is in `core`. A rules file may define more groups: `lint` runs only `core` unless `--group NAME` asks for more, and a group name that is not defined is an error (exit 2). Use a group for rules about files that are planned but not there yet. Because a literal path that is missing fails every non-`files` kind, such a rule that is run too early shows up as a loud failure, never as a silent pass.

## Rule inventory

157 rules: contains 87, mustNotContain 28, frontmatter 13 (11 roles, orchestrator, skill), containsOnce 13, json 6, sectionsInOrder 4, files 3, endsWithLine 2, asciiOnly 1. All 157 are in `core`.

Id prefixes: `files.*` · `agent.<role>.*` (one role) · `agents.*` (all or several roles) · `orch.*` (orchestrator) · `skill.*` · `plugin.*` / `marketplace.*` · `hooks.*` · `scripts.*` · `forbid.*` (must-not-contain over `agents`, `output-styles`, `skills`, `README.md`, `docs`, `hooks`, `scripts`: Hangul, `Korean`, `in English`, `user's language`, `/home/[a-z]`, `C:\\Users\\[A-Za-z]`, `/Users/[A-Za-z]`, `/tmp/claude`, `Co-Authored-By`, `@gmail.com`).

Every one of the 11 agents has `## Input`, so `agents.sections.required` (Input, Workflow, Do not, Return in order) applies to all.
