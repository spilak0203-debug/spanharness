#!/usr/bin/env python3
"""spanharness: record | report | lint.

Python 3.8+, standard library only. This file implements docs/lessons-format.md
(the specification wins over this code) and tests/harness-rules.md.

    spanharness.py record                         hook JSON on stdin, always exits 0
    spanharness.py report [OUT.md] [--months N]
    spanharness.py lint [--root DIR] [--group NAME]
    common: --claude-dir D --lessons-dir D --plugin-root D --project-dir D --now ISO8601
"""
import codecs
import hashlib
import json
import os
import re
from stat import S_ISREG
import sys
import time

USAGE = ("usage: spanharness.py record | report [OUT.md] [--months N] | lint [--root DIR] [--group NAME]"
         " [--claude-dir D] [--lessons-dir D] [--plugin-root D] [--project-dir D] [--now ISO8601]")

# --------------------------------------------------------------------------
# 0. Terms: whitespace, text(), number(), ordinal order, lower-casing, timestamps
# --------------------------------------------------------------------------

WS = "".join(chr(c) for c in (list(range(0x09, 0x0E)) + [0x20, 0x85, 0xA0, 0x1680] + list(range(0x2000, 0x200B))
                              + [0x2028, 0x2029, 0x202F, 0x205F, 0x3000]))
INT_MIN, INT_MAX = -(2 ** 63), 2 ** 63 - 1
BOM = b"\xef\xbb\xbf"
EN = "–"   # en dash
DOT = "·"  # middle dot
ARROW = "→"
TIMES = "×"
EM = "—"   # em dash


def trim(s):
    return s.strip(WS)


def okey(s):
    """Ordinal order: compare by UTF-16 code units."""
    return s.encode("utf-16-be", "surrogatepass")


def lower(s):
    """Simple one-to-one lower-casing, character by character (no final-sigma context)."""
    if s.isascii():
        return s.lower()
    out = []
    for c in s:
        low = c.lower()
        out.append(low if len(low) == 1 else c)
    return "".join(out)


_ASCII_UP = {c: c + 32 for c in range(65, 91)}


def ascii_lower(s):
    return s.translate(_ASCII_UP)


def text(obj, key):
    """The value of key when it is a string that is not blank, else None."""
    if isinstance(obj, dict):
        v = obj.get(key)
        if isinstance(v, str) and trim(v):
            return v
    return None


def number(v):
    """Signed 64-bit integer (JSON numbers truncated toward zero), else None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        n = v
    elif isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return None
        n = int(v)
    else:
        return None
    return n if INT_MIN <= n <= INT_MAX else None


def total(values):
    """Exact sum, None when outside the signed 64-bit range."""
    s = sum(values)
    return s if INT_MIN <= s <= INT_MAX else None


def _no_constant(name):
    raise ValueError("constant " + name)


def _depth(v):
    best = 0
    stack = [(v, 1)]
    while stack:
        x, d = stack.pop()
        if isinstance(x, dict):
            best = max(best, d)
            stack.extend((c, d + 1) for c in x.values())
        elif isinstance(x, list):
            best = max(best, d)
            stack.extend((c, d + 1) for c in x)
    return best


def parse_json(s, max_depth=100, **kw):
    """json.loads that rejects NaN/Infinity and nesting deeper than max_depth. Raises ValueError."""
    try:
        v = json.loads(s, parse_constant=_no_constant, **kw)
    except RecursionError:
        raise ValueError("nesting too deep")
    if s.count("[") + s.count("{") > max_depth and _depth(v) > max_depth:
        raise ValueError("nesting too deep")
    return v


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _lone_surrogate(e):
    return b"\xef\xbf\xbd" * (e.end - e.start), e.end


codecs.register_error("spanharness-fffd", _lone_surrogate)


def enc(s):
    """Text to UTF-8; a lone surrogate (from an escape such as "\\ud83d" in JSON) is written as U+FFFD, as .NET does."""
    return s.encode("utf-8", "spanharness-fffd")


def decode(data):
    """Bytes to text: drop a leading UTF-8 BOM, invalid bytes become U+FFFD."""
    if data.startswith(BOM):
        data = data[3:]
    return data.decode("utf-8", "replace")


_DIM = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days(y, m, d):
    """Days since 1970-01-01 of a proleptic Gregorian date."""
    y -= m <= 2
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


_TS = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]+))?(Z|[+-][0-9]{2}:[0-9]{2})?\Z")
_NOW = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(Z|[+-][0-9]{2}:[0-9]{2})\Z")


def _fields(m):
    """Validated (y, mo, d, h, mi, s, offset minutes) of a timestamp match, or None."""
    y, mo, d, h, mi, s = (int(m.group(i)) for i in range(1, 7))
    if not (1 <= mo <= 12) or h > 23 or mi > 59 or s > 59:
        return None
    if not (1 <= d <= _DIM[mo - 1] + (1 if mo == 2 and _leap(y) else 0)):
        return None
    off = m.group(m.lastindex if m.re is _NOW else 8)
    minutes = 0
    if off and off != "Z":
        oh, om = int(off[1:3]), int(off[4:6])
        if om > 59 or oh * 60 + om > 14 * 60:
            return None
        minutes = (oh * 60 + om) * (-1 if off[0] == "-" else 1)
    return y, mo, d, h, mi, s, minutes


def parse_ts(s):
    """Instant of a timestamp (section 0) in 100 ns ticks since the epoch, or None."""
    m = _TS.match(s)
    if not m:
        return None
    f = _fields(m)
    if f is None:
        return None
    y, mo, d, h, mi, sec, off = f
    frac = int((m.group(7) or "")[:7].ljust(7, "0"))
    return ((_days(y, mo, d) * 86400 + h * 3600 + mi * 60 + sec - off * 60) * 10000000) + frac


class Clock(object):
    """A local time: fields plus the offset (minutes) in force."""

    def __init__(self, y, mo, d, h, mi, s, off):
        self.f = (y, mo, d, h, mi, s)
        self.off = off

    def epoch(self):
        y, mo, d, h, mi, s = self.f
        return _days(y, mo, d) * 86400 + h * 3600 + mi * 60 + s - self.off * 60

    def stamp(self):
        sign = "+" if self.off >= 0 else "-"
        a = abs(self.off)
        return "%04d-%02d-%02dT%02d:%02d:%02d%s%02d:%02d" % (self.f + (sign, a // 60, a % 60))

    def month(self):
        return "%04d-%02d" % self.f[:2]

    def log_time(self):
        return "%04d-%02d-%02d %02d:%02d:%02d" % self.f


def parse_now(s):
    m = _NOW.match(s)
    f = _fields(m) if m else None
    if f is None:
        raise ValueError("bad --now value")
    return Clock(*f)


def system_clock():
    import datetime
    dt = datetime.datetime.now().astimezone()
    off = dt.utcoffset()
    minutes = int(off.total_seconds() // 60) if off is not None else 0
    return Clock(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, minutes)


# --------------------------------------------------------------------------
# command line and folders (section 2)
# --------------------------------------------------------------------------

class UsageError(Exception):
    pass


FLAGS = ("--claude-dir", "--lessons-dir", "--plugin-root", "--project-dir", "--now", "--months", "--root", "--group")


def parse_args(argv):
    opts, pos, groups = {}, [], []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            if a not in FLAGS:
                raise UsageError("unknown flag " + a)
            if i + 1 >= len(argv):
                raise UsageError(a + " needs a value")
            if a == "--group":
                groups.append(argv[i + 1])
            else:
                opts[a] = argv[i + 1]
            i += 2
        else:
            pos.append(a)
            i += 1
    return opts, pos, groups


def env_text(name):
    v = os.environ.get(name)
    return v if v is not None and trim(v) else None


def home_dir():
    v = os.environ.get("USERPROFILE" if os.name == "nt" else "HOME")
    return v if v else os.path.expanduser("~")


class Ctx(object):
    def __init__(self, opts, default_project=None):
        self.claude_dir = opts.get("--claude-dir") or env_text("CLAUDE_CONFIG_DIR") or os.path.join(home_dir(), ".claude")
        self.lessons = opts.get("--lessons-dir") or os.path.join(self.claude_dir, "lessons")
        self.plugin_root = opts.get("--plugin-root") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if "--project-dir" in opts:
            self.project_dir = opts["--project-dir"]
        else:
            self.project_dir = env_text("CLAUDE_PROJECT_DIR") or default_project
        self.fixed_now = parse_now(opts["--now"]) if "--now" in opts else None
        self.now = self.fixed_now or system_clock()

    def read_clock(self):
        """The time now (`--now` when given): 3.2 step 13 reads it after the lock."""
        return self.fixed_now or system_clock()


def listdir(d):
    try:
        return os.listdir(d)
    except OSError:
        return []


def read_file(path):
    with open(path, "rb") as f:
        return f.read()


def load_object(path):
    """A JSON object from a file, or None when missing, unreadable or not an object."""
    try:
        v = parse_json(decode(read_file(path)), 1000)
    except (OSError, ValueError):
        return None
    return v if isinstance(v, dict) else None


# --------------------------------------------------------------------------
# 4. harness fingerprint
# --------------------------------------------------------------------------

_SAFE_BAD = re.compile('["<>|:*?\\\\/\x00-\x1f]')


def safe_name(s):
    s = _SAFE_BAD.sub("-", s).strip(" .")
    s = s.encode("utf-16-le", "surrogatepass")[:120].decode("utf-16-le", "surrogatepass").rstrip(" .")
    return s or "skill"


def usable_name(name):
    return name not in (".", "..") and not _SAFE_BAD.search(name)


_KEY_LINE = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_.-]*)[ \t]*:([ \t]|\Z)")


def parse_front(txt):
    """Frontmatter of 4.3 as {key: (text after the colon, [continuation lines])}."""
    if txt.startswith("﻿"):
        txt = txt[1:]
    lines = [ln[:-1] if ln.endswith("\r") else ln for ln in txt.split("\n")]
    if not lines or lines[0].rstrip(" \t\r") != "---":
        return {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].rstrip(" \t\r") in ("---", "..."):
            end = i
            break
    if end is None:
        return {}
    keys, cur = {}, None
    for line in lines[1:end]:
        m = _KEY_LINE.match(line)
        if m:
            name = m.group(1)
            if name in keys:
                cur = None
            else:
                cur = []
                keys[name] = (line[line.index(":") + 1:], cur)
        elif cur is not None and (line == "" or line[0] in " \t" or line == "-" or line.startswith("- ")):
            cur.append(line)
        else:
            cur = None
    return keys


def _quoted(s):
    out, i, n = [], 1, len(s)
    while i < n:
        c = s[i]
        if c == '"':
            break
        if c == "\\" and i + 1 < n:
            d = s[i + 1]
            simple = {"n": "\n", "t": "\t", "r": "\r", "0": "\0"}
            if d in simple:
                out.append(simple[d])
                i += 2
                continue
            if d == "u":
                h = s[i + 2:i + 6]
                if len(h) == 4 and all(x in "0123456789abcdefABCDEF" for x in h):
                    out.append(chr(int(h, 16)))
                    i += 6
                    continue
            out.append(d)
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _single(s):
    out, i, n = [], 1, len(s)
    while i < n:
        c = s[i]
        if c == "'":
            if i + 1 < n and s[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            break
        out.append(c)
        i += 1
    return "".join(out)


def front_value(s):
    s = trim(s)
    if s.startswith('"'):
        return _quoted(s)
    if s.startswith("'"):
        return _single(s)
    i = s.find(" #")
    return trim(s[:i] if i >= 0 else s)


def front_get(keys, key):
    e = keys.get(key)
    if e is None:
        return None
    s = trim(e[0])
    for c in e[1]:
        t = trim(c)
        if t:
            s += " " + t
    return front_value(trim(s))


def front_list(keys, key):
    e = keys.get(key)
    if e is None:
        return []
    items = []
    r = trim(e[0])
    if r.startswith("#"):
        r = ""
    else:
        i = r.find(" #")
        r = trim(r[:i] if i >= 0 else r)
    if r:
        if len(r) >= 2 and r.startswith("[") and r.endswith("]"):
            r = r[1:-1]
        items.extend(front_value(p) for p in r.split(","))
    for c in e[1]:
        t = trim(c)
        if t == "-" or t.startswith("- "):
            items.append(front_value(t[1:]))
    return [x for x in items if x != ""]


class FingerprintError(Exception):
    pass


def file_hash(data):
    if data.startswith(BOM):
        data = data[3:]
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _add(files, key, path):
    """Hash a file into files[key]; returns its bytes, or None when it does not exist."""
    if not os.path.isfile(path):
        return None
    try:
        data = read_file(path)
    except OSError:
        raise FingerprintError("cannot read " + key)
    files[key] = file_hash(data)
    return data


def active_style(claude_dir, project_dir):
    paths = []
    if project_dir:
        paths += [os.path.join(project_dir, ".claude", "settings.local.json"), os.path.join(project_dir, ".claude", "settings.json")]
    paths.append(os.path.join(claude_dir, "settings.json"))
    for p in paths:
        obj = load_object(p)
        if obj is not None:
            v = obj.get("outputStyle")
            if isinstance(v, str) and trim(v):
                return v
    return "default"


def style_file(claude_dir, project_dir, value):
    """The key `output-styles/<file>` and its path for a user or project style, or None."""
    dirs = []
    if project_dir:
        dirs.append(os.path.join(project_dir, ".claude", "output-styles"))
    dirs.append(os.path.join(claude_dir, "output-styles"))
    want = lower(value)
    for d in dirs:
        for name in sorted(listdir(d), key=okey):
            p = os.path.join(d, name)
            if not ascii_lower(name).endswith(".md") or not os.path.isfile(p):
                continue
            if lower(name[:-3]) == want:
                return name, p
            try:
                fname = front_get(parse_front(decode(read_file(p))), "name")
            except OSError:
                continue
            if fname is not None and lower(fname) == want:
                return name, p
    return None


def fingerprint(claude_dir, plugin_root, project_dir):
    """(8 hex characters, {key: file hash}). Raises FingerprintError."""
    files = {}
    skills = []
    d = os.path.join(plugin_root, "agents")
    for name in listdir(d):
        if ascii_lower(name).endswith(".md"):
            data = _add(files, "plugin/agents/" + name, os.path.join(d, name))
            if data is not None:
                skills.extend(front_list(parse_front(decode(data)), "skills"))
    d = os.path.join(plugin_root, "output-styles")
    for name in listdir(d):
        if ascii_lower(name).endswith(".md"):
            _add(files, "plugin/output-styles/" + name, os.path.join(d, name))
    d = os.path.join(plugin_root, "skills")
    for name in listdir(d):
        if os.path.isdir(os.path.join(d, name)):
            _add(files, "plugin/skills/" + name + "/SKILL.md", os.path.join(d, name, "SKILL.md"))
    seen = set()
    for name in skills:
        if name in seen or not usable_name(name):
            continue
        seen.add(name)
        _add(files, "skills/" + name + "/SKILL.md", os.path.join(claude_dir, "skills", name, "SKILL.md"))
    value = active_style(claude_dir, project_dir)
    files["output-style"] = file_hash(enc(value))
    found = style_file(claude_dir, project_dir, value)
    if found:
        _add(files, "output-styles/" + found[0], found[1])
    _add(files, "CLAUDE.md", os.path.join(claude_dir, "CLAUDE.md"))
    body = "\n".join(k + "\t" + files[k] for k in sorted(files, key=okey))
    return hashlib.sha256(enc(body)).hexdigest()[:8], files


def compare(before, after):
    """(changed, added, removed), each in ordinal order; a missing `before` counts as empty."""
    before = before or {}
    changed = sorted((k for k in after if k in before and before[k] != after[k]), key=okey)
    added = sorted((k for k in after if k not in before), key=okey)
    removed = sorted((k for k in before if k not in after), key=okey)
    return changed, added, removed


def plugin_version(plugin_root):
    return text(load_object(os.path.join(plugin_root, ".claude-plugin", "plugin.json")), "version")


def role_values(agent_type, claude_dir, plugin_root, project_dir):
    """(role_model, role_effort) from the role file of an agent_type (4.4)."""
    pre = "spanharness:"
    if agent_type.startswith(pre):
        name = agent_type[len(pre):]
        paths = [os.path.join(plugin_root, "agents", name + ".md")]
    else:
        name = agent_type
        paths = []
        if project_dir:
            paths.append(os.path.join(project_dir, ".claude", "agents", name + ".md"))
        paths += [os.path.join(claude_dir, "agents", name + ".md"), os.path.join(plugin_root, "agents", name + ".md")]
    if not usable_name(name):
        return None, None
    for p in paths:
        if os.path.isfile(p):
            try:
                keys = parse_front(decode(read_file(p)))
            except OSError:
                return None, None
            return front_get(keys, "model"), front_get(keys, "effort")
    return None, None


def project_name(cwd):
    if cwd is None:
        return None
    t = cwd.rstrip("/\\")
    folder = t
    while folder:
        comp = os.path.basename(folder)
        if comp and os.path.exists(os.path.join(folder, ".git")):
            return comp
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    last = t[max(t.rfind("/"), t.rfind("\\")) + 1:]
    return last or None


# --------------------------------------------------------------------------
# 3.3 transcript summary
# --------------------------------------------------------------------------

USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def is_prompt(obj):
    if obj.get("isMeta") is True or obj.get("isCompactSummary") is True:
        return False
    kind = text(obj.get("origin"), "kind")
    if kind is not None and kind != "human":
        return False
    msg = obj.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, str):
        return bool(trim(content))
    if isinstance(content, list):
        return any(isinstance(e, dict) and text(e, "type") != "tool_result" for e in content)
    return False


def open_regular(path):
    """The transcript opened for reading, only when it is a regular file (3.3): a directory, a pipe or a device
    is an OSError. The open does not wait for a writer on a pipe."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        if not S_ISREG(os.fstat(fd).st_mode):
            raise OSError("not a regular file")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def summarize(path, offset):
    """Counts of the transcript from a byte offset (3.3)."""
    res = {"in": None, "out": None, "cache_read": None, "cache_write": None, "tools": None, "turns": None,
           "ms": None, "model": None, "offset": offset, "unchanged": False, "last_prompt": None, "broken": 0}
    if path is None:
        return res
    try:
        f = open_regular(path)
    except (OSError, ValueError):
        return res
    try:
        with f:
            size = os.fstat(f.fileno()).st_size
            start = offset if 0 <= offset <= size else 0
            f.seek(start)
            return _read_lines(f, start, size, res)
    except OSError:
        res.update({"in": None, "out": None, "cache_read": None, "cache_write": None, "tools": None, "turns": None,
                    "ms": None, "model": None, "offset": offset, "unchanged": False, "last_prompt": None, "broken": 0})
        return res


def _read_lines(f, start, size, res):
    answers, tools = {}, set()
    counter = 0
    model = None
    tmin = tmax = None
    pos = cursor = start
    last_prompt = None
    broken = 0
    while cursor < size:
        # never past the length seen when the file was opened (a file that grows meanwhile is read to that length)
        raw = f.readline(size - cursor)
        if not raw:
            break
        line_start = cursor
        cursor += len(raw)
        complete = raw.endswith(b"\n")
        # a byte order mark is removed at the start of the file only (6.2)
        line = trim(decode(raw) if line_start == 0 else raw.decode("utf-8", "replace"))
        if not line:
            pos = cursor
            continue
        try:
            obj = parse_json(line, 200)
        except ValueError:
            obj = None
        if not isinstance(obj, dict):
            if complete:
                broken += 1
                pos = cursor
            continue
        pos = cursor
        typ = text(obj, "type")
        if typ == "user" or typ == "assistant":
            ts = obj.get("timestamp")
            if isinstance(ts, str):
                v = parse_ts(ts)
                if v is not None:
                    tmin = v if tmin is None or v < tmin else tmin
                    tmax = v if tmax is None or v > tmax else tmax
        if typ == "user":
            if is_prompt(obj):
                last_prompt = line_start
        elif typ == "assistant":
            msg = obj.get("message")
            if isinstance(msg, dict):
                mid = text(msg, "id")
                if mid is None:
                    counter += 1
                    mid = "line-%d" % counter
                kept = answers.setdefault(mid, [None, None, None, None])
                m = text(msg, "model")
                if m is not None and m != "<synthetic>":
                    model = m
                usage = msg.get("usage")
                if isinstance(usage, dict):
                    for i, k in enumerate(USAGE_KEYS):
                        n = number(usage.get(k))
                        if n is not None:
                            kept[i] = n
                content = msg.get("content")
                if isinstance(content, list):
                    for el in content:
                        if isinstance(el, dict) and el.get("type") == "tool_use":
                            tid = text(el, "id")
                            if tid is None:
                                counter += 1
                                tid = "tool-%d" % counter
                            tools.add(tid)
    res["offset"] = pos
    res["unchanged"] = size == start
    res["last_prompt"] = last_prompt
    res["broken"] = broken
    res["model"] = model
    for i, k in enumerate(("in", "out", "cache_read", "cache_write")):
        vals = [a[i] for a in answers.values() if a[i] is not None]
        res[k] = total(vals) if vals else None
    res["turns"] = len(answers) or None
    res["tools"] = len(tools) if answers else None
    res["ms"] = (tmax - tmin) // 10000 if tmin is not None else None
    return res


def _prompt_line(raw, line_start):
    """Is this line (its bytes, without the line feed) a prompt, as _read_lines decides it?"""
    line = trim(decode(raw) if line_start == 0 else raw.decode("utf-8", "replace"))
    # `type` can only read "user" when the text holds "user" or a \u escape; a cheap test, though most lines pass it
    if "user" not in line and "\\u" not in line:
        return False
    try:
        obj = parse_json(line, 200)
    except ValueError:
        return False
    return isinstance(obj, dict) and text(obj, "type") == "user" and is_prompt(obj)


def last_prompt_start(path, block=65536):
    """The byte position where the last prompt line starts, found by reading blocks from the end of the file; None
    when there is no prompt (or the file cannot be read). It is the `last_prompt` that summarize(path, 0) finds."""
    if path is None:
        return None
    try:
        f = open_regular(path)
    except (OSError, ValueError):
        return None
    try:
        with f:
            pos = os.fstat(f.fileno()).st_size
            tail = []           # the pieces of the line that ends at `hi`, last piece first
            while pos > 0:
                n = min(block, pos)
                pos -= n
                f.seek(pos)
                data = f.read(n)
                hi = len(data)
                while True:
                    i = data.rfind(b"\n", 0, hi)
                    if i < 0:
                        tail.append(data[:hi])
                        break
                    tail.append(data[i + 1:hi])
                    if _prompt_line(b"".join(reversed(tail)), pos + i + 1):
                        return pos + i + 1
                    tail = []
                    hi = i
            return 0 if tail and _prompt_line(b"".join(reversed(tail)), 0) else None
    except OSError:
        return None


def summarize_turn(path, offset):
    if offset is not None:
        return summarize(path, offset)
    # no saved position: the turn starts at the last prompt, whatever comes before it is not read (3.3)
    return summarize(path, last_prompt_start(path) or 0)


# --------------------------------------------------------------------------
# 3. record
# --------------------------------------------------------------------------

LOCK_TIMEOUT = 10.0
OPTIMISTIC_TRIES = 3
LOCK_STEP = 0.05
STATE_KEEP_DAYS = 30
ERRORS_MAX = 262144


def one_line(s):
    return s.replace("\r", " ").replace("\n", " ")


def detail_of(e):
    """Exception type and the system message; never text of the input."""
    if isinstance(e, OSError):
        return "%s: %s" % (type(e).__name__, e.strerror or "")
    return type(e).__name__


def log_error(lessons, now, what, detail=None):
    """Append one line to errors.log; never raises."""
    try:
        path = os.path.join(lessons, "errors.log")
        os.makedirs(lessons, exist_ok=True)
        try:
            if os.path.getsize(path) > ERRORS_MAX:
                os.remove(path)
        except OSError:
            pass
        line = now.log_time() + " " + what
        if detail:
            line += " " + EM + " " + one_line(detail)
        with open(path, "ab") as f:
            f.write(enc(line + "\n"))
    except Exception:
        pass


def _lock(fd):
    try:
        import fcntl
    except ImportError:
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def acquire_lock(path):
    """An open descriptor holding the exclusive lock, or None after LOCK_TIMEOUT."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o666)
    deadline = time.monotonic() + LOCK_TIMEOUT
    while True:
        try:
            _lock(fd)
            return fd
        except OSError:
            if time.monotonic() >= deadline:
                os.close(fd)
                return None
            time.sleep(LOCK_STEP)


def wait_test_gate(attempt):
    """Test-only (3.9): with SPANHARNESS_TEST_GATE naming a folder, say that try `attempt` has made its summary
    (`reached-N`) and wait for `go-N` (60 s at most)."""
    d = env_text("SPANHARNESS_TEST_GATE")
    if d is None:
        return
    try:
        open(os.path.join(d, "reached-%d" % attempt), "wb").close()
        go = os.path.join(d, "go-%d" % attempt)
        deadline = time.monotonic() + 60
        while not os.path.exists(go) and time.monotonic() < deadline:
            time.sleep(0.01)
    except OSError:
        pass


def wait_last_line(path, clock=time.monotonic, sleep=time.sleep):
    """If the file ends in a partial line, poll every 50 ms (at most 1000 ms) until its last byte is a line feed."""
    def complete():
        try:
            with open_regular(path) as f:
                size = os.fstat(f.fileno()).st_size
                if size == 0:
                    return True
                f.seek(size - 1)
                return f.read(1) == b"\n"
        except (OSError, ValueError):
            return True
    start = clock()
    while not complete():
        if clock() - start >= 1.0:
            return
        sleep(0.05)


def write_atomic(path, obj):
    """JSON object through <path>.tmp and a replace, retrying 3 times 150 ms apart."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    data = enc(dumps(obj))
    for attempt in range(4):
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
            return
        except OSError:
            if attempt == 3:
                raise
            time.sleep(0.15)


def append_lines(path, lines):
    data = enc("".join(ln + "\n" for ln in lines))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for attempt in range(6):
        try:
            with open(path, "ab") as f:
                f.write(data)
            return
        except OSError:
            if attempt == 5:
                raise
            time.sleep(0.1)


def saved_offset(state_file, transcript):
    if state_file is None or transcript is None:
        return None
    st = load_object(state_file)
    if st is None or not isinstance(st.get("path"), str) or lower(st["path"]) != lower(transcript):
        return None
    return number(st.get("offset"))


def clean_state(state_dir, now):
    limit = now.epoch() - STATE_KEEP_DAYS * 86400
    for name in listdir(state_dir):
        if (name.startswith("turn-") or name.startswith("agent-")) and name.endswith(".json"):
            p = os.path.join(state_dir, name)
            if os.path.getmtime(p) < limit:
                os.remove(p)


def cmd_record(argv):
    if os.environ.get("SPANHARNESS_RECORD") == "0":
        return 0
    stdin = sys.stdin
    if stdin is not None and stdin.isatty():
        sys.stderr.write(USAGE + "\n")
        return 0
    try:
        opts, pos, _ = parse_args(argv)
        if pos:
            raise UsageError("unexpected argument")
        ctx = Ctx(opts)
    except (UsageError, ValueError) as e:
        sys.stderr.write("spanharness record: %s\n" % e)
        return 0
    try:
        record(ctx, opts)
    except Exception as e:
        log_error(ctx.lessons, ctx.now, "record failed", detail_of(e))
    return 0


def record(ctx, opts):
    lessons, now = ctx.lessons, ctx.now
    raw = sys.stdin.buffer.read() if sys.stdin is not None else b""
    if raw.startswith(BOM):
        raw = raw[3:]
    try:
        hook = parse_json(raw.decode("utf-8", "replace"), 100)
    except ValueError:
        hook = None
    if not isinstance(hook, dict):
        log_error(lessons, now, "hook input is not a JSON object (%d bytes)" % len(raw))
        return
    event, session = text(hook, "hook_event_name"), text(hook, "session_id")
    cwd, agent_id, agent_type = text(hook, "cwd"), text(hook, "agent_id"), text(hook, "agent_type")
    effort = text(hook.get("effort"), "level")
    if event == "SubagentStop" and agent_type is not None:
        kind = "agent"
    elif event == "Stop" and agent_id is None:
        kind = "turn"
    else:
        return
    transcript = text(hook, "agent_transcript_path" if kind == "agent" else "transcript_path")
    ident = agent_id if kind == "agent" else session
    state_dir = os.path.join(lessons, "state")
    state_file = os.path.join(state_dir, ("agent-" if kind == "agent" else "turn-") + safe_name(ident) + ".json") if ident is not None else None
    if transcript is not None:
        wait_last_line(transcript)
    project_dir = ctx.project_dir or cwd
    fp, files = None, None
    try:
        fp, files = fingerprint(ctx.claude_dir, ctx.plugin_root, project_dir)
    except FingerprintError as e:
        log_error(lessons, now, "harness fingerprint failed", str(e))
    except Exception as e:
        log_error(lessons, now, "harness fingerprint failed", detail_of(e))
    role_model = role_effort = None
    if kind == "agent":
        role_model, role_effort = role_values(agent_type, ctx.claude_dir, ctx.plugin_root, project_dir)
    # The summary is made without the lock (it can take long); the lock covers only the commit below. A record
    # that finds the saved position moved by another record in the meantime sums up again from the new position.
    # The last try holds the lock from the start, so a record cannot starve.
    lock = None
    try:
        for attempt in range(OPTIMISTIC_TRIES + 1):
            if attempt == OPTIMISTIC_TRIES:
                lock = acquire_lock(os.path.join(state_dir, "lock"))
                if lock is None:
                    log_error(lessons, now, "could not take the lock; record skipped")
                    return
            offset = saved_offset(state_file, transcript)
            if kind == "agent":
                s = summarize(transcript, offset if offset is not None else 0)
            else:
                s = summarize_turn(transcript, offset)
            if offset is not None and s["unchanged"]:
                return
            wait_test_gate(attempt + 1)
            if lock is None:
                lock = acquire_lock(os.path.join(state_dir, "lock"))
                if lock is None:
                    log_error(lessons, now, "could not take the lock; record skipped")
                    return
                if saved_offset(state_file, transcript) != offset:
                    os.close(lock)
                    lock = None
                    continue
            _commit(ctx, kind, cwd, session, agent_id, agent_type, effort, transcript, state_file, s,
                    fp, files, role_model, role_effort)
            return
    finally:
        if lock is not None:
            os.close(lock)


def _commit(ctx, kind, cwd, session, agent_id, agent_type, effort, transcript, state_file, s,
            fp, files, role_model, role_effort):
    """Steps 13-17 of 3.2, with the lock held."""
    lessons = ctx.lessons
    state_dir = os.path.join(lessons, "state")
    now = ctx.read_clock()
    t = now.stamp()
    pv = plugin_version(ctx.plugin_root)
    rec = {"t": t, "kind": kind, "project": project_name(cwd), "cwd": cwd, "session": session}
    if kind == "agent":
        rec["agent"] = agent_type
        rec["agent_id"] = agent_id
    rec["model"] = s["model"]
    if kind == "agent":
        rec["role_model"] = role_model
    rec["effort"] = effort
    if kind == "agent":
        rec["role_effort"] = role_effort
    for k in ("in", "out", "cache_read", "cache_write", "tools", "turns", "ms"):
        rec[k] = s[k]
    rec["harness"] = fp
    skip = ("effort", "role_model", "role_effort")
    rec["missing"] = [k for k, v in rec.items() if v is None and k not in skip]
    lines = []
    write_harness = False
    if fp is not None:
        saved = load_object(os.path.join(state_dir, "harness.json"))
        valid = saved is not None and isinstance(saved.get("harness"), str) and isinstance(saved.get("files"), dict)
        if not valid or saved["harness"] != fp or text(saved, "plugin_version") != pv:
            write_harness = True
            changed, added, removed = compare(saved["files"] if valid else None, files)
            lines.append(dumps({"t": t, "kind": "harness", "harness": fp, "prev": saved["harness"] if valid else None,
                                "changed": changed, "added": added, "removed": removed, "plugin_version": pv}))
    lines.append(dumps(rec))
    try:
        append_lines(os.path.join(lessons, "runs", now.month() + ".jsonl"), lines)
    except OSError as e:
        log_error(lessons, now, "could not write the record", detail_of(e))
        return
    if write_harness:
        try:
            write_atomic(os.path.join(state_dir, "harness.json"),
                         {"harness": fp, "files": dict((k, files[k]) for k in sorted(files, key=okey)), "plugin_version": pv})
        except Exception as e:
            log_error(lessons, now, "could not save the harness state", detail_of(e))
    if state_file is not None:
        try:
            write_atomic(state_file, {"path": transcript, "offset": s["offset"]})
        except Exception as e:
            log_error(lessons, now, "could not save the read position", detail_of(e))
    try:
        clean_state(state_dir, now)
    except Exception as e:
        log_error(lessons, now, "could not remove old read positions", detail_of(e))


# --------------------------------------------------------------------------
# 5. report
# --------------------------------------------------------------------------

TXT_ROLE_TABLE = (
    "The role is the `agent` name; the main conversation comes from turn lines. Token columns are `median / total`; the tools, turns and ms columns are medians. Unreadable values (`null`) are left out of the counts; a total too large for 64 bits is shown as `-`."
)

TXT_VERSION_TABLE = (
    "Runs grouped by role and the harness fingerprint written on each run (all projects together), oldest version of a role first. Tokens = in + out + cache_read + cache_write of one run; time = ms. A run with an unread value is left out of that column's n. Spread is min–max when n < 4 and p25–p75 when n ≥ 4. The runs are different tasks, so this is observation, not a controlled test. The fingerprint covers the whole setup: a change may come from a file other than the role's own (see Harness changes)."
)

TXT_COMPARE = (
    "For each role whose latest harness version differs from the previous one. A difference is printed as a finding only when both sides have n ≥ 5 and the spreads do not overlap; otherwise it is labelled noise / inconclusive and no difference is given."
)

TXT_MODEL_1 = (
    "Runs grouped by role and the model written on each run (all projects and harness versions together): the main conversation's model changes per session, so the harness fingerprint alone mixes models. Model ids that differ only in case are one row (shown in lower case). Columns as in the harness table: tokens = in + out + cache_read + cache_write of one run, time = ms; a run with an unread value is left out of that column's n; spread is min–max when n < 4 and p25–p75 when n ≥ 4. A run without a model is listed as `(model unknown)`. The runs are different tasks, so this is observation, not a controlled test."
)

TXT_MODEL_2 = (
    "The signal columns count the `events.md` events of that role × model (see Outcome signals for the signals). An event is joined to the runs of the same date + project + role (case does not matter; `main` is the main conversation) and counted under the model of those runs, whatever the harness version. When the runs it matches that day used more than one model, the model is not guessed: the event is counted in no row and shows in the `Ambiguous model` line under the table. An event with no run to match is not here either (it is counted under Outcome signals). `other signals` sums signal words with no column of its own. `repeated-failure` and `redone` with work type `experiment` are expected iterations and are left out; the other signals with that work type are counted. Events are self-reported, so the counts are a lower bound. `Cost n` is the number of runs the cost adds up (a run with any unread token value is left out), and the cost uses the prices and rules of the cost table below; `-` for a model with no known price or a token total that does not fit in 64 bits."
)

TXT_COST = (
    "Approximate: tokens × list price (USD per million tokens as of {as_of}), summed per model over all projects and roles; the cost column of the role × model table above splits the same sum by role. Cache writes are priced at the 5-minute rate because the 1-hour split is not recorded. Haiku 5.5 is priced at the rate for prompts up to 100K tokens, so its cost is a lower bound. A model id is matched by family and version (`claude-opus-5-5`, with or without a date or `[1m]` after it); an id with no known price shows `-`, never a guess, and so does a model with no run to count or a token total that does not fit in 64 bits. A run with any unread token value is left out of the cost and counted under `Left out`."
)

TXT_EVENTS = (
    "events.md is written by the orchestrator about its own work, so these counts are a lower bound, not everything that went wrong. Each event is joined by date + project + role (case does not matter; `main` is the main conversation) to the harness version of that role's runs that day. Per run = events of that signal / runs of that role under that version. A `repeated-failure` or `redone` event whose work type is `experiment` is an expected iteration, not a harness failure: it is left out of the counts and rates here and shown on a line of its own. The other signals (`fix-request` · `review-block` · `review-wrong`) with work type `experiment` are harness signals and are counted as usual."
)

TXT_NO_RUNS = "No role runs or turns recorded.\n"
TXT_NONE_COMPARED = "none: no role has two harness versions in this period.\n"
SIGNALS = ("fix-request", "review-block", "review-wrong", "repeated-failure", "redone")
MAIN_ROLE = "main conversation"
MAIN_NAMES = ("main", "main conversation", "orchestrator")
UNKNOWN_MODEL = "(model unknown)"
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_PRICE_KEY = re.compile(r"claude-(fable|opus|sonnet|haiku)-([0-9]+)-([0-9]{1,2})(?=\Z|[-\[@" + re.escape(WS) + r"])")
Fraction = None
Decimal = None
math = None


def _imports():
    global Fraction, Decimal, math
    if Fraction is not None:
        return
    import math as _math
    from fractions import Fraction as _F
    from decimal import Decimal as _D
    Fraction, Decimal, math = _F, _D, _math


def fmt_dec(x, places, strip=True):
    """x rounded half away from zero to `places` decimals, exact."""
    x = Fraction(x)
    n = math.floor(abs(x) * 10 ** places + Fraction(1, 2))
    ip, fp = divmod(n, 10 ** places)
    s = str(ip)
    frac = str(fp).zfill(places) if places else ""
    if strip:
        frac = frac.rstrip("0")
    if frac:
        s += "." + frac
    if x < 0 and n != 0:
        s = "-" + s
    return s


def fmt1(x):
    return fmt_dec(x, 1)


def fmt2(x):
    return fmt_dec(x, 2)


def money(x):
    if x is None:
        return "-"
    if 0 < x < Fraction(1, 100):
        return "<$0.01"
    return "$" + fmt_dec(x, 2, False)


def quantile(vals, q):
    s = sorted(vals)
    n = len(s)
    at = (n - 1) * q
    low = math.floor(at)
    high = min(low + 1, n - 1)
    return s[low] + (s[high] - s[low]) * (at - low)


def median(vals):
    return quantile(vals, Fraction(1, 2))


def spread(vals):
    """(label, low, high)"""
    if len(vals) < 4:
        s = sorted(vals)
        return "min" + EN + "max", Fraction(s[0]), Fraction(s[-1])
    return "p25" + EN + "p75", quantile(vals, Fraction(1, 4)), quantile(vals, Fraction(3, 4))


def stat(vals):
    if not vals:
        return ["0", "-", "-"]
    label, lo, hi = spread(vals)
    return [str(len(vals)), fmt1(median(vals)), "%s %s%s%s" % (label, fmt1(lo), EN, fmt1(hi))]


def span(first, last):
    if first is None:
        return "-"
    return first if first == last else "%s %s %s" % (first, EN, last)


def esc(cell):
    return str(cell).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def table(header, rows):
    out = ["| " + " | ".join(esc(h) for h in header) + " |", "|" + "---|" * len(header)]
    out.extend("| " + " | ".join(esc(c) for c in r) + " |" for r in rows)
    return "\n".join(out) + "\n"


def strip_prefix(role):
    pre = "spanharness:"
    if len(role) > len(pre) and lower(role[:len(pre)]) == pre:
        return role[len(pre):]
    return role


class Price(object):
    def __init__(self, name, inp, out, cache_read, cache_write):
        self.name, self.inp, self.out, self.cache_read, self.cache_write = name, inp, out, cache_read, cache_write


def load_prices(plugin_root):
    """(as_of or None, {key: Price}) or None when prices.json cannot be read or parsed."""
    _imports()
    try:
        v = json.loads(decode(read_file(os.path.join(plugin_root, "scripts", "prices.json"))),
                       parse_float=Decimal, parse_constant=_no_constant)
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(v, dict):
        return None
    as_of = v.get("as_of") if isinstance(v.get("as_of"), str) else None
    models = {}
    if isinstance(v.get("models"), dict):
        for key, e in v["models"].items():
            if not isinstance(e, dict):
                continue
            nums = [e.get(k) for k in ("input", "output", "cache_write_5m", "cache_read")]
            if all(isinstance(x, (int, Decimal)) and not isinstance(x, bool) for x in nums):
                name = e.get("name") if isinstance(e.get("name"), str) else key
                models[key] = Price(name, Fraction(nums[0]), Fraction(nums[1]), Fraction(nums[3]), Fraction(nums[2]))
    return as_of, models


def price_of(model, prices):
    if model is None or prices is None:
        return None
    m = _PRICE_KEY.match(lower(trim(model)))
    return prices[1].get("%s-%s-%s" % m.groups()) if m else None


class Run(object):
    pass


class Data(object):
    def __init__(self):
        self.runs, self.changes = [], []
        self.agents = self.turns = self.skipped = 0
        self.t_min = self.t_max = None
        self.unread = 0
        self.unread_keys = {}
        self.rows = {}
        self.failed = []


def _strings(v):
    return [x for x in v if isinstance(x, str) and trim(x)] if isinstance(v, list) else []


def add_line(D, line):
    try:
        obj = parse_json(line, 100)
    except ValueError:
        obj = None
    kind = text(obj, "kind")
    if kind not in ("agent", "turn", "harness"):
        D.skipped += 1
        return
    t = text(obj, "t")
    if t is not None:
        ts = parse_ts(t)
        if ts is not None:
            if D.t_min is None or ts < D.t_min[0]:
                D.t_min = (ts, t)
            if D.t_max is None or ts > D.t_max[0]:
                D.t_max = (ts, t)
    if kind == "harness":
        D.changes.append({"when": t, "prev": text(obj, "prev"), "hash": text(obj, "harness"),
                          "changed": _strings(obj.get("changed")), "added": _strings(obj.get("added")),
                          "removed": _strings(obj.get("removed")), "version": text(obj, "plugin_version")})
        return
    r = Run()
    r.seq = len(D.runs)
    r.kind = kind
    r.main = kind == "turn"
    if r.main:
        D.turns += 1
        r.role = MAIN_ROLE
    else:
        D.agents += 1
        r.role = strip_prefix(text(obj, "agent") or "(role name unknown)")
    r.project = text(obj, "project") or "(project unknown)"
    r.harness = text(obj, "harness") or "(unknown)"
    model = text(obj, "model")
    r.model = lower(trim(model)) if model is not None else None
    r.date = t[:10] if t is not None and _DATE.match(t[:10]) and len(t) >= 10 else None
    r.counts = [number(obj.get(k)) for k in ("in", "out", "cache_read", "cache_write")]
    r.complete = all(c is not None for c in r.counts)
    r.tokens = total(r.counts) if r.complete else None
    r.ms = number(obj.get("ms"))
    D.runs.append(r)
    row = D.rows.setdefault((r.main, r.project, r.role), {"count": 0, "models": set(), "efforts": set(), "unread": 0,
                                                          "cols": dict((c, []) for c in ("in", "out", "cache_read", "cache_write", "tools", "turns", "ms"))})
    row["count"] += 1
    if r.model is not None:
        row["models"].add(r.model)
    eff = text(obj, "effort")
    if eff is not None:
        row["efforts"].add(eff)
    for c, vals in row["cols"].items():
        n = number(obj.get(c))
        if n is not None:
            vals.append(n)
    miss = _strings(obj.get("missing"))
    if miss:
        row["unread"] += 1
        D.unread += 1
        for k in miss:
            D.unread_keys[k] = D.unread_keys.get(k, 0) + 1


def read_runs(D, lessons, m_from, m_to):
    d = os.path.join(lessons, "runs")
    names = []
    for n in listdir(d):
        if (len(n) == 13 and re.match(r"[0-9]{4}-(0[1-9]|1[0-2])\Z", n[:7]) and n[7:].lower() == ".jsonl"
                and m_from <= n[:7] <= m_to and os.path.isfile(os.path.join(d, n))):
            names.append(n)
    names.sort(key=okey)
    D.files = names
    for n in names:
        chunks = []
        ok = True
        try:
            with open(os.path.join(d, n), "rb") as f:
                while True:
                    c = f.read(1 << 20)
                    if not c:
                        break
                    chunks.append(c)
        except OSError:
            ok = False
        if not ok:
            D.failed.append(n)
        for raw in re.split(r"\r\n|\n|\r", decode(b"".join(chunks))):
            line = trim(raw)
            if line:
                add_line(D, line)


def read_events(lessons, m_from, m_to):
    """(events, expected, bad, problem)"""
    path = os.path.join(lessons, "events.md")
    if not os.path.isfile(path):
        return [], 0, 0, "events.md not found: no outcome signals."
    try:
        data = read_file(path)
    except OSError:
        return [], 0, 0, "events.md could not be read."
    events, expected, bad = [], 0, 0
    for raw in decode(data).split("\n"):
        line = trim(raw)
        if not line.startswith("- "):
            continue
        parts = [trim(p) for p in line[2:].split(" | ", 5)]
        if len(parts) < 5 or not _DATE.match(parts[0]) or not parts[1] or not parts[2] or not parts[4]:
            bad += 1
            continue
        if parts[0][:7] < m_from or parts[0][:7] > m_to:
            continue
        signal = lower(parts[2])
        work = lower(trim(parts[3].split(DOT, 1)[0]))
        if work == "experiment" and signal in ("repeated-failure", "redone"):
            expected += 1
            continue
        role = strip_prefix(parts[4])
        events.append({"date": parts[0], "project": parts[1], "signal": signal, "role": role,
                       "main": lower(role) in MAIN_NAMES})
    return events, expected, bad, None


def read_log(lessons):
    entries = {}
    try:
        txt = decode(read_file(os.path.join(lessons, "harness-log.md")))
    except OSError:
        return entries
    for raw in txt.split("\n"):
        line = trim(raw)
        if not line.startswith("- "):
            continue
        parts = line[2:].split(" | ")
        if len(parts) >= 6:
            entries.setdefault(trim(parts[-1]), trim(parts[0]) + " " + trim(parts[1]))
    return entries


def day_key(date, project, main, role):
    return (date, lower(project), "t" if main else "a" + lower(role))


def cost_of(runs, price):
    """(runs counted, cost or None)"""
    ok = [r for r in runs if r.complete]
    if price is None or not ok:
        return len(ok), None
    sums = [total([r.counts[i] for r in ok]) for i in range(4)]
    if any(s is None for s in sums):
        return len(ok), None
    return len(ok), (sums[0] * price.inp + sums[1] * price.out + sums[2] * price.cache_read + sums[3] * price.cache_write) / 1000000


def month_minus(clock, n):
    idx = clock.f[0] * 12 + clock.f[1] - 1 - n
    return "%04d-%02d" % (idx // 12, idx % 12 + 1)


def build_report(ctx, months, prices):
    _imports()
    m_to = ctx.now.month()
    m_from = month_minus(ctx.now, months - 1)
    D = Data()
    read_runs(D, ctx.lessons, m_from, m_to)
    events, expected, bad, problem = read_events(ctx.lessons, m_from, m_to)
    log = read_log(ctx.lessons)
    out = []
    w = out.append
    # header
    w("# Lessons record summary\n")
    w("- Period: %s ~ %s (last %d month(s), this month included)" % (m_from, m_to, months))
    w("- Files read: " + (", ".join("runs/" + n for n in D.files) if D.files else "none"))
    if D.failed:
        w("- Files that could not be opened: " + ", ".join(D.failed))
    w("- Lines: role runs %d \u00b7 main-conversation turns %d \u00b7 harness changes %d \u00b7 skipped lines %d (not JSON, or unknown kind)"
      % (D.agents, D.turns, len(D.changes), D.skipped))
    if D.t_min is not None:
        w("- Record times: %s ~ %s" % (D.t_min[1], D.t_max[1]))
    try:
        fp, files = fingerprint(ctx.claude_dir, ctx.plugin_root, ctx.project_dir)
        w("- Current harness fingerprint: %s (%d files)" % (fp, len(files)))
    except FingerprintError as e:
        w("- Current harness fingerprint: unknown (%s)" % e)
    head = "\n".join(out) + "\n"
    out = [head]
    runs = D.runs
    # project x role
    out.append("\n## Project %s role\n\n" % TIMES)
    if not runs:
        out.append(TXT_NO_RUNS)
    else:
        out.append(TXT_ROLE_TABLE + "\n\n")
        rows = []
        for key in sorted(D.rows, key=lambda k: (okey(k[1]), 0 if k[0] else 1, okey(k[2]))):
            r = D.rows[key]
            cells = [key[1], key[2], str(r["count"]), ", ".join(sorted(r["models"], key=okey)) or "-",
                     ", ".join(sorted(r["efforts"], key=okey)) or "-"]
            for c in ("in", "out", "cache_read", "cache_write"):
                v = r["cols"][c]
                if not v:
                    cells.append("-")
                else:
                    s = total(v)
                    cells.append("%s / %s" % (fmt1(median(v)), "-" if s is None else s))
            for c in ("tools", "turns", "ms"):
                v = r["cols"][c]
                cells.append(fmt1(median(v)) if v else "-")
            cells.append(str(r["unread"]))
            rows.append(cells)
        out.append(table(["Project", "Role", "Count", "Model", "effort", "in", "out", "cache_read", "cache_write", "tools", "turns", "ms", "Read failures"], rows))
    # role x harness version
    out.append("\n## Role %s harness version\n\n" % TIMES)
    versions = {}
    for r in runs:
        v = versions.setdefault((r.kind, r.role, r.harness), [])
        v.append(r)
    vorder = sorted(versions, key=lambda k: (0 if k[0] == "turn" else 1, okey(k[1]), versions[k][0].seq))
    vtokens = dict((k, [r.tokens for r in versions[k] if r.tokens is not None]) for k in vorder)
    vms = dict((k, [r.ms for r in versions[k] if r.ms is not None]) for k in vorder)

    def dates(rs):
        ds = sorted(r.date for r in rs if r.date is not None)
        return span(ds[0] if ds else None, ds[-1] if ds else None)
    if not runs:
        out.append(TXT_NO_RUNS)
    else:
        out.append(TXT_VERSION_TABLE + "\n\n")
        rows = []
        for k in vorder:
            rows.append([k[1], k[2], str(len(versions[k])), dates(versions[k])] + stat(vtokens[k]) + stat(vms[k]))
        out.append(table(["Role", "Harness", "Runs", "First %s last run" % EN, "Tokens n", "Tokens median", "Tokens spread", "Time n", "Time median", "Time spread"], rows))
        out.append("\n### Version comparisons\n\n" + TXT_COMPARE + "\n\n")
        groups, gorder = {}, []
        for k in vorder:
            if k[2] == "(unknown)":
                continue
            if (k[0], k[1]) not in groups:
                groups[(k[0], k[1])] = []
                gorder.append((k[0], k[1]))
            groups[(k[0], k[1])].append(k)
        lines = []
        for g in gorder:
            vs = groups[g]
            if len(vs) < 2:
                continue
            by_last = sorted(vs, key=lambda k: versions[k][-1].seq)
            latest, prev = by_last[-1], by_last[-2]
            line = "- %s: %s %s %s | runs %d %s %d | tokens %s | time (ms) %s" % (
                g[1], prev[2], ARROW, latest[2], len(versions[prev]), ARROW, len(versions[latest]),
                compare_text(vtokens[prev], vtokens[latest]), compare_text(vms[prev], vms[latest]))
            if latest[2] in log:
                line += " | applied by " + log[latest[2]]
            lines.append(line + "\n")
        out.append("".join(lines) if lines else TXT_NONE_COMPARED)
    # role x model
    out.append("\n## Role %s model\n\n" % TIMES)
    if not runs:
        out.append(TXT_NO_RUNS)
    else:
        out.append(TXT_MODEL_1 + "\n\n" + TXT_MODEL_2 + "\n\n")
        mrows = {}
        for r in runs:
            mrows.setdefault((r.kind, r.role, r.model or UNKNOWN_MODEL), []).append(r)
        by_day = {}
        for r in runs:
            if r.date is not None:
                by_day.setdefault(day_key(r.date, r.project, r.main, r.role), []).append(r)
        sig = dict((k, {}) for k in mrows)
        amb, amb_sig = 0, {}
        vsig = dict((k, {}) for k in vorder)
        no_run = changed_day = joined = 0
        for e in events:
            hit = by_day.get(day_key(e["date"], e["project"], e["main"], e["role"]))
            if not hit:
                no_run += 1
                continue
            tuples = set((r.kind, r.role, r.model or UNKNOWN_MODEL) for r in hit)
            if len(tuples) == 1:
                d = sig[next(iter(tuples))]
                d[e["signal"]] = d.get(e["signal"], 0) + 1
            else:
                amb += 1
                amb_sig[e["signal"]] = amb_sig.get(e["signal"], 0) + 1
            vers = set((r.kind, r.role, r.harness) for r in hit)
            if len(vers) > 1:
                changed_day += 1
            else:
                joined += 1
                d = vsig[next(iter(vers))]
                d[e["signal"]] = d.get(e["signal"], 0) + 1
        rows = []
        for k in sorted(mrows, key=lambda k: (0 if k[0] == "turn" else 1, okey(k[1]), okey(k[2]))):
            rs = mrows[k]
            toks = [r.tokens for r in rs if r.tokens is not None]
            mss = [r.ms for r in rs if r.ms is not None]
            n, c = cost_of(rs, price_of(None if k[2] == UNKNOWN_MODEL else k[2], prices))
            if problem:
                cells = ["-"] * 6
            else:
                cells = [str(sig[k].get(s, 0)) for s in SIGNALS]
                cells.append(str(sum(v for s, v in sig[k].items() if s not in SIGNALS)))
            rows.append([k[1], k[2], str(len(rs)), dates(rs)] + stat(toks) + stat(mss) + cells + [str(n), money(c)])
        out.append(table(["Role", "Model", "Runs", "First %s last run" % EN, "Tokens n", "Tokens median", "Tokens spread", "Time n", "Time median", "Time spread",
                          "fix-request", "review-block", "review-wrong", "repeated-failure", "redone", "other signals", "Cost n", "Approx. cost (USD)"], rows))
        out.append("\n")
        if problem:
            out.append("- Signal columns show `-`: %s\n" % problem)
        else:
            line = "- Ambiguous model: %d event(s) matched runs of more than one model that day, so they are in no row above" % amb
            if amb:
                line += " (" + " \u00b7 ".join("%s %d" % (s, amb_sig[s]) for s in sorted(amb_sig, key=okey)) + ")"
            out.append(line + "\n")
        # cost per model
        out.append("\n### Approximate cost per model\n\n")
        out.append(TXT_COST.replace("{as_of}", (prices[0] if prices is not None and prices[0] else "unknown")) + "\n\n")
        per = {}
        for r in runs:
            per.setdefault(r.model or UNKNOWN_MODEL, []).append(r)
        rows = []
        for m in sorted(per, key=okey):
            rs = per[m]
            p = price_of(None if m == UNKNOWN_MODEL else m, prices)
            n, c = cost_of(rs, p)
            if p is None:
                cells = [m, "-", "-"]
            else:
                cells = [m, p.name, " / ".join(fmt_dec(x, 3) for x in (p.inp, p.out, p.cache_write, p.cache_read))]
            rows.append(cells + [str(len(rs)), str(len(rs) - n), money(c)])
        out.append(table(["Model", "Priced as", "List price per M tokens (in / out / cache write / cache read)", "Runs", "Left out", "Approx. cost (USD)"], rows))
    # outcome signals
    out.append("\n## Outcome signals (events.md)\n\n")
    if problem:
        out.append(problem + "\n")
    else:
        if not runs:
            by_day = {}
            vsig = {}
            no_run = len(events)
            changed_day = joined = 0
        out.append(TXT_EVENTS + "\n\n")
        if joined > 0:
            rows = []
            for k in vorder:
                for s in sorted(vsig[k], key=okey):
                    n = vsig[k][s]
                    rows.append([k[1], k[2], str(len(versions[k])), s, str(n), fmt2(Fraction(n, len(versions[k])))])
            out.append(table(["Role", "Harness", "Runs", "Signal", "Events", "Per run"], rows) + "\n")
        out.append("- Events in the period: %d \u00b7 joined to a harness version %d \u00b7 no run of that role in that project that day %d \u00b7 harness changed that day, so not attributed %d\n"
                   % (len(events), joined, no_run, changed_day))
        out.append("- Expected experiment iterations (`repeated-failure` \u00b7 `redone` with work type `experiment`; not in the counts above): %d\n" % expected)
        out.append("- Lines starting with `- ` that are not in the format (`- YYYY-MM-DD | project | signal | work type \u00b7 size | role | fact`): %d\n" % bad)
    # read failures
    out.append("\n## Read failures\n\n")
    out.append("- Lines with unread keys: %d / %d (role-run and turn lines whose `missing` is not empty)\n" % (D.unread, D.agents + D.turns))
    keys = " \u00b7 ".join("%s %d" % (k, D.unread_keys[k]) for k in sorted(D.unread_keys, key=okey)) or "none"
    out.append("- Unread keys: %s\n" % keys)
    # harness changes
    out.append("\n## Harness changes\n\n")
    if not D.changes:
        out.append("none\n")
    for c in D.changes:
        parts = ["%s | %s %s %s" % (c["when"] or "(time unknown)", c["prev"] or "(first)", ARROW, c["hash"] or "?")]
        for name in ("changed", "added", "removed"):
            if c[name]:
                parts.append("%s %s" % (name, ", ".join(c[name])))
        if c["version"]:
            parts.append("plugin " + c["version"])
        out.append("- " + " | ".join(parts) + "\n")
    return "".join(out)


def compare_text(prev, latest):
    if not prev:
        return "not measured (no readable value on the previous side)"
    if not latest:
        return "not measured (no readable value on the latest side)"
    mp, ml = median(prev), median(latest)
    head = "median %s (n=%d) %s %s (n=%d): " % (fmt1(mp), len(prev), ARROW, fmt1(ml), len(latest))
    reasons = []
    if len(prev) < 5 or len(latest) < 5:
        reasons.append("n < 5")
    _, lo1, hi1 = spread(prev)
    _, lo2, hi2 = spread(latest)
    if lo1 <= hi2 and lo2 <= hi1:
        reasons.append("spreads overlap")
    if reasons:
        return head + "noise / inconclusive (" + "; ".join(reasons) + ")"
    return head + "finding, median difference " + ("+" if ml > mp else "") + fmt1(ml - mp)


def cmd_report(argv):
    try:
        opts, pos, _ = parse_args(argv)
        if len(pos) > 1:
            raise UsageError("more than one output file")
        months = 2
        if "--months" in opts:
            m = opts["--months"]
            if not re.match(r"[0-9]+\Z", m) or not 1 <= int(m) <= 120:
                raise UsageError("--months needs a whole number from 1 to 120")
            months = int(m)
        ctx = Ctx(opts, default_project=os.getcwd())
        out = pos[0] if pos else os.path.join(ctx.lessons, "report.md")
        if out == "" or "\0" in out:
            raise UsageError("not a valid output path")
    except (UsageError, ValueError) as e:
        sys.stderr.write("spanharness report: %s\n%s\n" % (e, USAGE))
        return 2
    try:
        prices = load_prices(ctx.plugin_root)
        if prices is None:
            sys.stderr.write("spanharness report: warning: scripts/prices.json could not be read; prices are unknown\n")
        body = build_report(ctx, months, prices)
        path = os.path.abspath(out)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        for attempt in range(4):
            try:
                with open(tmp, "wb") as f:
                    f.write(enc(body))
                os.replace(tmp, path)
                break
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(0.15)
    except Exception as e:
        try:
            os.remove(os.path.abspath(out) + ".tmp")
        except OSError:
            pass
        sys.stderr.write("spanharness report: %s\n" % one_line("%s %s" % (type(e).__name__, getattr(e, "strerror", None) or e)))
        return 1
    sys.stdout.buffer.write(enc(path + "\n"))
    sys.stdout.flush()
    return 0


# --------------------------------------------------------------------------
# lint (tests/harness-rules.md)
# --------------------------------------------------------------------------

class LintConfigError(Exception):
    pass


_GLOBS = {}


def glob_re(pattern):
    r = _GLOBS.get(pattern)
    if r is None:
        segs = pattern.split("/")
        rx = ""
        for i, seg in enumerate(segs):
            last = i == len(segs) - 1
            if seg == "**":
                rx += ".+" if last else "(?:[^/]+/)*"
            else:
                rx += "[^/]*".join(re.escape(p) for p in seg.split("*")) + ("" if last else "/")
        r = _GLOBS[pattern] = re.compile(rx + r"\Z")
    return r


def section_of(txt, heading):
    lines = txt.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln == heading]
    if len(idx) != 1:
        return None
    i = idx[0]
    j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
    return "\n".join(lines[i:j]) + ("\n" if j < len(lines) else "")


def lint_front(txt):
    """(ordered keys, {key: str or list}) of the strict frontmatter; ValueError when it does not parse."""
    lines = txt.split("\n")
    if lines[0] != "---":
        raise ValueError("no frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError("frontmatter is not closed")
    order, values, cur = [], {}, None

    def unquote(v):
        v = trim(v)
        return v[1:-1] if len(v) >= 2 and v[0] == '"' and v[-1] == '"' else v
    for line in lines[1:end]:
        if not trim(line):
            continue
        m = re.match(r"([A-Za-z0-9_-]+):(?: ?)(.*)\Z", line)
        if m:
            if m.group(1) in values:
                raise ValueError("duplicate key " + m.group(1))
            cur = m.group(1)
            order.append(cur)
            values[cur] = unquote(m.group(2))
            continue
        m = re.match(r" +- (.*)\Z", line)
        if m and cur is not None and (values[cur] == "" or isinstance(values[cur], list)):
            if not isinstance(values[cur], list):
                values[cur] = []
            values[cur].append(unquote(m.group(1)))
            continue
        raise ValueError("cannot parse line: " + line)
    return order, values


def json_values(node, path):
    cur = [node]
    for seg in path.split("."):
        nxt = []
        for n in cur:
            if seg == "*":
                if isinstance(n, list):
                    nxt.extend(n)
                elif isinstance(n, dict):
                    nxt.extend(n.values())
            elif isinstance(n, dict):
                if seg in n:
                    nxt.append(n[seg])
            elif isinstance(n, list) and re.match(r"[0-9]+\Z", seg) and int(seg) < len(n):
                nxt.append(n[int(seg)])
        cur = nxt
    return cur


def same_json(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_json(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_json(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def check_text(rule, kind, txt):
    """Failure reasons of a text rule on the (normalized) text of one file."""
    if rule.get("section") is not None:
        scope = section_of(txt, rule["section"])
        if scope is None:
            return ["heading %r does not occur exactly once" % rule["section"]]
    else:
        scope = txt
    literals = rule["texts"] if "texts" in rule else ([rule["text"]] if "text" in rule else [])
    bad = []
    if kind == "contains":
        bad = ["missing text %r" % t for t in literals if t not in scope]
    elif kind == "containsOnce":
        bad = ["text %r occurs %d times" % (t, scope.count(t)) for t in literals if scope.count(t) != 1]
    elif kind == "mustNotContain":
        ic = bool(rule.get("ignoreCase"))
        if "regex" in rule:
            if re.search(rule["regex"], scope, (re.I | re.A) if ic else 0):
                bad.append("forbidden pattern %r matches" % rule["regex"])
        else:
            hay = ascii_lower(scope) if ic else scope
            for t in literals:
                if (ascii_lower(t) if ic else t) in hay:
                    bad.append("forbidden text %r" % t)
    return bad


def check_rule(rule, files, root, texts):
    """List of (path, reason) failures of one rule."""
    kind = rule.get("kind")
    if kind == "files":
        fails = []
        if "dir" in rule:
            d = rule["dir"]
            have = set(n for n in listdir(os.path.join(root, d)) if not n.startswith(".") and (d + "/" + n) in files)
            only = set(rule.get("only", []))
            for n in sorted(only - have, key=okey):
                fails.append((d + "/" + n, "missing"))
            for n in sorted(have - only, key=okey):
                fails.append((d + "/" + n, "unexpected file"))
        for p in rule.get("paths", []):
            if p not in files:
                fails.append((p, "missing file"))
        return fails
    if kind not in ("frontmatter", "sectionsInOrder", "contains", "containsOnce", "endsWithLine", "mustNotContain", "asciiOnly", "json"):
        raise LintConfigError("rule %s: unknown kind %r" % (rule.get("id"), kind))
    fails, targets = [], []
    for pat in rule.get("paths", []):
        if "*" in pat:
            found = sorted((f for f in files if glob_re(pat).match(f)), key=okey)
        else:
            found = [pat] if pat in files else []
            if not found:
                fails.append((pat, "missing file"))
        targets.extend(f for f in found if f not in targets)
    targets = [t for t in targets if not any(glob_re(e).match(t) for e in rule.get("exclude", []))]
    if not targets and not fails:
        fails.append(("-", "no files match"))
    for t in targets:
        if kind == "asciiOnly":
            data = read_file(os.path.join(root, t))
            if data.translate(None, bytes([9, 10, 13] + list(range(32, 127)))):
                fails.append((t, "non-ASCII byte"))
            continue
        txt = texts.get(t)
        if txt is None:
            txt = texts[t] = decode(read_file(os.path.join(root, t))).replace("\r\n", "\n").replace("\r", "\n")
        if kind in ("contains", "containsOnce", "mustNotContain"):
            reasons = check_text(rule, kind, txt)
        elif kind == "endsWithLine":
            reasons = [] if txt.endswith("\n" + rule["line"] + "\n") else ["does not end with the line %r" % rule["line"]]
        elif kind == "sectionsInOrder":
            heads = [ln for ln in txt.split("\n") if ln.startswith("## ")]
            want = rule["sections"]
            if rule.get("exact"):
                reasons = [] if heads == want else ["headings are %r" % heads]
            else:
                pos, reasons = 0, []
                for h in want:
                    if h in heads[pos:]:
                        pos = heads.index(h, pos) + 1
                    else:
                        reasons.append("heading %r missing or out of order" % h)
                        break
        elif kind == "frontmatter":
            reasons = []
            try:
                order, values = lint_front(txt)
            except ValueError as e:
                order, values, reasons = None, None, [str(e)]
            if values is not None:
                if "keys" in rule and order != rule["keys"]:
                    reasons.append("keys are %r" % order)
                for k, v in rule.get("equals", {}).items():
                    if k not in values or values[k] != v:
                        reasons.append("%s is %r, expected %r" % (k, values.get(k), v))
                for k in rule.get("absent", []):
                    if k in values:
                        reasons.append("%s must be absent" % k)
                for k in rule.get("nonEmpty", []):
                    if k not in values or values[k] in ("", []):
                        reasons.append("%s is empty or missing" % k)
        else:
            reasons = []
            try:
                doc = parse_json(decode(read_file(os.path.join(root, t))), 1000)
            except ValueError as e:
                doc, reasons = None, ["invalid JSON"]
            if not reasons:
                vals = json_values(doc, rule["path"])
                if "equals" in rule:
                    if "*" in rule["path"]:
                        raise LintConfigError("rule %s: equals needs a path without *" % rule.get("id"))
                    if not (len(vals) == 1 and same_json(vals[0], rule["equals"])):
                        reasons.append("%s is not %r" % (rule["path"], rule["equals"]))
                elif not any(isinstance(v, str) and rule["anyContains"] in v for v in vals):
                    reasons.append("no %s contains %r" % (rule["path"], rule["anyContains"]))
        fails.extend((t, r) for r in reasons)
    return fails


def lint(root, enabled):
    """(failed rules as [(id, path, reason, extra)], rules run, rules skipped). Raises LintConfigError."""
    rules_path = os.path.join(root, "tests", "harness-rules.json")
    try:
        doc = parse_json(decode(read_file(rules_path)), 1000)
    except (OSError, ValueError) as e:
        raise LintConfigError("cannot read %s" % rules_path)
    if not isinstance(doc, dict) or not isinstance(doc.get("rules"), list) or not isinstance(doc.get("groups"), dict):
        raise LintConfigError("%s needs groups and rules" % rules_path)
    groups = doc["groups"]
    for g in enabled:
        if g not in groups:
            raise UsageError("unknown group " + g)
    files = set()
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath == root and ".git" in dirnames:
            dirnames.remove(".git")
        for n in filenames:
            p = os.path.join(dirpath, n)
            if os.path.isfile(p):
                files.add(os.path.relpath(p, root).replace(os.sep, "/"))
    failed, ran, skipped, seen, texts = [], 0, 0, set(), {}
    for rule in doc["rules"]:
        rid = rule.get("id")
        if not isinstance(rid, str) or rid in seen:
            raise LintConfigError("rule id missing or repeated: %r" % rid)
        seen.add(rid)
        group = rule.get("group", "core")
        if group not in groups:
            raise LintConfigError("rule %s: group %r is not in groups" % (rid, group))
        if group not in enabled:
            skipped += 1
            continue
        ran += 1
        fails = check_rule(rule, files, root, texts)
        if fails:
            failed.append((rid, fails[0][0], fails[0][1], len(fails) - 1))
    return failed, ran, skipped


def cmd_lint(argv):
    try:
        opts, pos, groups = parse_args(argv)
        if pos:
            raise UsageError("unexpected argument " + pos[0])
        ctx = Ctx(opts, default_project=os.getcwd())
        root = opts.get("--root", ctx.plugin_root)
        failed, ran, skipped = lint(root, set(["core"] + groups))
    except (UsageError, ValueError) as e:
        sys.stderr.write("spanharness lint: %s\n%s\n" % (e, USAGE))
        return 2
    except LintConfigError as e:
        sys.stderr.write("spanharness lint: %s\n" % e)
        return 1
    except Exception as e:
        sys.stderr.write("spanharness lint: %s\n" % one_line("%s %s" % (type(e).__name__, getattr(e, "strerror", None) or e)))
        return 1
    for rid, path, reason, more in failed:
        sys.stdout.buffer.write(enc("%s %s: %s%s\n" % (rid, path, reason, " (and %d more)" % more if more else "")))
    sys.stdout.flush()
    sys.stderr.write("lint: %d rules checked, %d failed, %d skipped\n" % (ran, len(failed), skipped))
    return 1 if failed else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 2000))
    cmd = argv[0] if argv else None
    if cmd == "record":
        return cmd_record(argv[1:])
    if cmd == "report":
        return cmd_report(argv[1:])
    if cmd == "lint":
        return cmd_lint(argv[1:])
    sys.stderr.write(USAGE + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
