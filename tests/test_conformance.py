"""Conformance tests: every case under tests/fixtures/cases/ runs through each selected implementation.

A case is a folder:

    args.txt      one invocation per line (blank lines and lines starting with # are ignored). A line is the
                  command line after the script name, split like a POSIX shell; an optional "[N] " prefix is the
                  expected exit code (default 0); an optional " < path" suffix names the file (relative to the
                  sandbox) that is fed to stdin (default for "record": hook-input.json).
    input/        copied to a fresh sandbox folder. A path component "_git" becomes ".git" (git cannot store
                  one). The text {ROOT} inside any file is replaced by the sandbox path.
    generate.txt  optional, lines "<generator> <path>": files that are made at test time (too big to commit).
    touch.txt     optional, lines "<YYYY-MM-DDTHH:MM:SS (UTC)> <path>": sets the last-write time.
    env.txt       optional, lines NAME=value for the child process ({ROOT} and {PLUGIN} are replaced).
    stdout.txt    optional: the exact stdout of the last invocation ({ROOT} is replaced; "\\" counts as "/").
    deleted.txt   optional: sandbox paths that were in input/ and must be gone after the run.
    expected/     every file that the run created or changed, relative to the sandbox, byte for byte. The sandbox
                  path appears as {ROOT}. errors.log holds only the "what" of each line (3.6): no time, no detail.
                  state/lock is ignored. No expected/ folder means that nothing changes.

In args, {ROOT} is the sandbox (the "claude dir" is whatever the case puts in it, usually {ROOT}/claude) and
{PLUGIN} is tests/fixtures/plugin. Paths are written with "/" so that JSON stays valid on Windows.

Set SPANHARNESS_BLESS=1 (python3 tests/run_tests.py --bless) to write expected/ from the Python implementation.
"""
import calendar
import difflib
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, "fixtures")
CASES = os.path.join(FIXTURES, "cases")
PLUGIN = os.path.join(FIXTURES, "plugin")
SCRIPTS = {"py": os.path.join(REPO, "scripts", "spanharness.py"), "ps1": os.path.join(REPO, "scripts", "spanharness.ps1")}
CLEAN_ENV = ("CLAUDE_CONFIG_DIR", "CLAUDE_PROJECT_DIR", "SPANHARNESS_RECORD")


def posix(p):
    return p.replace(os.sep, "/")


def find_pwsh():
    env = os.environ.get("SPANHARNESS_PWSH")
    if env:
        return env
    if os.name == "nt":
        return shutil.which("powershell.exe") or shutil.which("pwsh")
    return shutil.which("pwsh")


HOST_GUARD = "if (-not $script:OnWindows) { return 0 }"
_TEMP = {}


def temp_dir(name):
    """A folder outside every case sandbox, removed when the test run ends."""
    if name not in _TEMP:
        import atexit
        _TEMP[name] = tempfile.mkdtemp(prefix="spanharness-" + name + "-")
        atexit.register(shutil.rmtree, _TEMP[name], True)
    return _TEMP[name]


def ps1_script():
    """The PowerShell script to run. Its `record` does nothing on a host that is not Windows (the plugin's hook runs on
    Windows only); there the tests run a copy in which that one guard line is blank. On Windows: the script itself."""
    real = SCRIPTS["ps1"]
    if os.name == "nt" or not os.path.isfile(real):
        return real
    if "ps1" not in _TEMP:
        with open(real, "rb") as f:
            lines = f.read().split(b"\n")
        hits = [i for i, l in enumerate(lines) if l.strip().decode("utf-8", "replace") == HOST_GUARD]
        if len(hits) != 1:
            raise RuntimeError("scripts/spanharness.ps1: the host guard line %r occurs %d times, expected exactly 1" % (HOST_GUARD, len(hits)))
        lines[hits[0]] = b"\r" if lines[hits[0]].endswith(b"\r") else b""
        path = os.path.join(temp_dir("ps1"), "spanharness.ps1")
        with open(path, "wb") as f:
            f.write(b"\n".join(lines))
        _TEMP["ps1"] = path
    return _TEMP["ps1"]


def impl_env(impl, env):
    """The environment of a child process. pwsh writes caches under the home folder (a sandbox here): point them elsewhere."""
    if impl == "ps1":
        cache = temp_dir("pwsh-cache")
        env = dict(env, XDG_CACHE_HOME=cache, XDG_CONFIG_HOME=cache, XDG_DATA_HOME=cache,
                   POWERSHELL_TELEMETRY_OPTOUT="1", POWERSHELL_UPDATECHECK="Off")
    return env


def impl_command(impl):
    """The command prefix that runs an implementation, or None when it cannot run here."""
    if impl == "py":
        return [sys.executable, "-I", SCRIPTS["py"]]
    exe = find_pwsh()
    if not exe or not os.path.isfile(SCRIPTS["ps1"]):
        return None
    cmd = [exe, "-NoProfile", "-NonInteractive"]
    if os.name == "nt":
        cmd += ["-ExecutionPolicy", "Bypass"]
    return cmd + ["-File", ps1_script()]


def ci():
    return os.environ.get("CI", "").lower() == "true"


def wanted():
    """The implementations this run is about (run_tests.py --impl sets SPANHARNESS_IMPLS)."""
    v = os.environ.get("SPANHARNESS_IMPLS", "")
    if v == "py":
        return set(["py"])
    if v == "ps1":
        return set(["ps1"])
    if v == "both":
        return set(["py", "ps1"])
    return set(["py", "ps1"]) if ci() or impl_command("ps1") else set(["py"])


def require(tc, impl):
    """The command of an implementation, or skip (a failure when CI=true and the runtime is missing)."""
    if impl not in wanted():
        tc.skipTest("%s not selected" % impl)
    cmd = impl_command(impl)
    if cmd is None:
        msg = "%s cannot run here (no PowerShell found, or scripts/spanharness.ps1 is missing)" % impl
        if ci():
            tc.fail(msg)
        tc.skipTest(msg)
    return cmd


# --------------------------------------------------------------------------
# files made at test time
# --------------------------------------------------------------------------

BIG_ANSWERS = 4000
BIG_FILL = "x" * 560
BIG_WIDE = 70000


def big_transcript_bytes():
    """A transcript of more than 3 MB. Answer i (0-based) has id big-i, usage (i%7+1, 2, 3, 4) and a tool call on every
    third answer; line 2 is a tool-result line of 70000 two-byte characters (it crosses every read buffer)."""
    lines = ['{"type":"user","timestamp":"2026-10-21T09:00:00.000Z","message":{"role":"user","content":"start"}}']
    lines.append('{"type":"user","timestamp":"2026-10-21T09:00:01.000Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"x","content":"%s"}]}}'
                 % ("λ" * BIG_WIDE))
    for i in range(BIG_ANSWERS):
        sec = 2 + i
        stamp = "2026-10-21T%02d:%02d:%02d.250Z" % (9 + sec // 3600, sec // 60 % 60, sec % 60)
        tool = '{"type":"tool_use","id":"big-t%d"},' % i if i % 3 == 0 else ""
        lines.append('{"type":"assistant","timestamp":"%s","message":{"id":"big-%d","model":"claude-sonnet-5-5","content":[%s{"type":"text","text":"%s"}],'
                     '"usage":{"input_tokens":%d,"output_tokens":2,"cache_read_input_tokens":3,"cache_creation_input_tokens":4}}}'
                     % (stamp, i, tool, BIG_FILL, i % 7 + 1))
    return ("\n".join(lines) + "\n").encode("utf-8")


def errors_log_big_bytes():
    """An errors.log of 262197 bytes: over the 256 KB limit, so the next failure starts the file over."""
    return b"2026-01-01 00:00:00 filler\n" * 9711


def turn_resume_bytes():
    """A resumed session of about 340 KB, with no saved position, whose last prompt is in the middle: it starts after a byte
    order mark, 150 answers of 1 KB come first, then the last prompt (its type written with \\u escapes), an answer with a tool
    call, a tool result of 70000 two-byte characters (it crosses every read block), 3 more answers and a line of meta text."""
    def answer(i, tool):
        stamp = "09:%02d:%02d" % (i // 60, i % 60) if i < 150 else "10:00:%02d" % (i - 199)
        return ('{"type":"assistant","timestamp":"2026-10-21T%s.000Z","message":{"id":"r%d","model":"claude-sonnet-5-5","content":[%s{"type":"text","text":"%s"}],'
                '"usage":{"input_tokens":%d,"output_tokens":2,"cache_read_input_tokens":3,"cache_creation_input_tokens":4}}}'
                % (stamp, i, tool, "y" * 1000, i % 7 + 1))
    lines = ['{"type":"user","timestamp":"2026-10-21T08:59:00.000Z","message":{"role":"user","content":"first prompt"}}']
    lines += [answer(i, "") for i in range(150)]
    lines.append('{"\\u0074ype":"\\u0075ser","timestamp":"2026-10-21T10:00:00.000Z","message":{"role":"user","content":"the last prompt"}}')
    lines.append(answer(200, '{"type":"tool_use","id":"far-t1"},'))
    lines.append('{"type":"user","timestamp":"2026-10-21T10:00:30.000Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"far-t1","content":"%s"}]}}' % ("\u03bb" * 70000))
    lines += [answer(201 + i, "") for i in range(3)]
    lines.append('{"type":"user","timestamp":"2026-10-21T10:01:30.000Z","isMeta":true,"message":{"role":"user","content":"meta text"}}')
    return b"\xef\xbb\xbf" + ("\n".join(lines) + "\n").encode("utf-8")


GENERATORS = {"big_transcript": big_transcript_bytes, "errors_log_big": errors_log_big_bytes, "turn_resume": turn_resume_bytes}


# --------------------------------------------------------------------------
# running a case
# --------------------------------------------------------------------------

def read(path):
    with open(path, "rb") as f:
        return f.read()


def read_lines_file(path):
    if not os.path.isfile(path):
        return []
    out = []
    for line in read(path).decode("utf-8").split("\n"):
        line = line.strip("\r")
        if line.strip() and not line.startswith("#"):
            out.append(line)
    return out


def snapshot(root):
    snap = {}
    for dirpath, _, names in os.walk(root):
        for n in names:
            p = os.path.join(dirpath, n)
            snap[posix(os.path.relpath(p, root))] = hashlib.sha256(read(p)).hexdigest()
    return snap


def sub(data, root):
    return data.replace(b"{ROOT}", root.encode("utf-8")).replace(b"{PLUGIN}", posix(PLUGIN).encode("utf-8"))


def copy_input(src, root):
    for dirpath, dirnames, names in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        parts = [] if rel == "." else [".git" if c == "_git" else c for c in rel.split(os.sep)]
        dest = os.path.join(root, *parts)
        os.makedirs(dest, exist_ok=True)
        for d in dirnames:
            os.makedirs(os.path.join(dest, ".git" if d == "_git" else d), exist_ok=True)
        for n in names:
            with open(os.path.join(dest, ".git" if n == "_git" else n), "wb") as f:
                f.write(sub(read(os.path.join(dirpath, n)), root))


def prepare(case):
    # realpath: the scripts print paths resolved from the working directory (macOS /private/var, Windows long names)
    root = posix(os.path.realpath(tempfile.mkdtemp(prefix="sh-")))
    src = os.path.join(case, "input")
    if os.path.isdir(src):
        copy_input(src, root)
    for line in read_lines_file(os.path.join(case, "generate.txt")):
        name, rel = line.split(" ", 1)
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(GENERATORS[name]())
    for line in read_lines_file(os.path.join(case, "touch.txt")):
        stamp, rel = line.split(" ", 1)
        t = calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%S"))
        os.utime(os.path.join(root, rel), (t, t))
    return root


def parse_invocations(case):
    """[(expected exit, tokens, stdin file or None)]"""
    out = []
    for line in read_lines_file(os.path.join(case, "args.txt")):
        code = 0
        m = re.match(r"\[(\d+)\]\s+", line)
        if m:
            code, line = int(m.group(1)), line[m.end():]
        stdin = None
        if " < " in line:
            line, stdin = line.rsplit(" < ", 1)
            stdin = stdin.strip()
        tokens = shlex.split(line)
        if stdin is None and tokens and tokens[0] == "record":
            stdin = "hook-input.json"
        out.append((code, tokens, stdin))
    return out


def child_env(case, root):
    env = dict(os.environ)
    for k in CLEAN_ENV:
        env.pop(k, None)
    env["HOME"] = env["USERPROFILE"] = root + "/home"
    for line in read_lines_file(os.path.join(case, "env.txt")):
        k, v = line.split("=", 1)
        env[k] = v.replace("{ROOT}", root).replace("{PLUGIN}", posix(PLUGIN))
    return env


def run_args(cmd, tokens, root, env, stdin_bytes, timeout=180):
    args = [t.replace("{ROOT}", root).replace("{PLUGIN}", posix(PLUGIN)) for t in tokens]
    return subprocess.run(cmd + args, input=stdin_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          cwd=root, env=env, timeout=timeout)


def normalize_errors_log(data):
    """Only the `what` of each line: no time, no detail."""
    out = []
    for line in data.decode("utf-8").split("\n"):
        if not line:
            continue
        line = re.sub(r"^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} ", "", line)
        out.append(line.split(" — ")[0])
    return ("\n".join(out) + "\n").encode("utf-8") if out else b""


def changed_files(root, before):
    """({path: bytes with {ROOT} and a normalized errors.log}, deleted paths) of a run."""
    after = snapshot(root)
    root_b = root.encode("utf-8")
    files = {}
    for rel, digest in after.items():
        if rel.endswith("state/lock") or before.get(rel) == digest:
            continue
        data = read(os.path.join(root, rel)).replace(root_b, b"{ROOT}")
        if rel.endswith("errors.log"):
            data = normalize_errors_log(data)
        files[rel] = data
    return files, sorted(set(before) - set(after))


def expected_files(case):
    base = os.path.join(case, "expected")
    out = {}
    for dirpath, _, names in os.walk(base):
        for n in names:
            p = os.path.join(dirpath, n)
            out[posix(os.path.relpath(p, base))] = read(p)
    return out


def show_diff(name, want, got):
    a = want.decode("utf-8", "replace").splitlines(True)
    b = got.decode("utf-8", "replace").splitlines(True)
    return "".join(list(difflib.unified_diff(a, b, "expected/" + name, "actual/" + name))[:60])


def bless(case, files, deleted, stdout):
    base = os.path.join(case, "expected")
    shutil.rmtree(base, ignore_errors=True)
    for rel, data in files.items():
        p = os.path.join(base, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
    for name, content in (("deleted.txt", "".join(d + "\n" for d in deleted).encode("utf-8") if deleted else None),
                          ("stdout.txt", stdout if stdout else None)):
        p = os.path.join(case, name)
        if content is None:
            if os.path.exists(p):
                os.remove(p)
        else:
            with open(p, "wb") as f:
                f.write(content)


def run_case(tc, impl, case):
    cmd = require(tc, impl)
    invocations = parse_invocations(case)
    root = prepare(case)
    try:
        env = impl_env(impl, child_env(case, root))
        before = snapshot(root)
        last = None
        for code, tokens, stdin in invocations:
            data = b""
            if stdin is not None:
                p = os.path.join(root, stdin)
                data = read(p) if os.path.isfile(p) else b""
            last = run_args(cmd, tokens, root, env, data)
            tc.assertEqual(last.returncode, code, "exit code of %r\nstderr: %s" % (tokens, last.stderr.decode("utf-8", "replace")))
            if tokens[0] == "record":
                tc.assertEqual(last.stdout, b"", "record must print nothing on stdout")
        files, deleted = changed_files(root, before)
        out = last.stdout.replace(b"\\", b"/").replace(root.encode("utf-8"), b"{ROOT}").replace(b"\r\n", b"\n")
        if os.environ.get("SPANHARNESS_BLESS") == "1" and impl == "py":
            bless(case, files, deleted, out)
        want = expected_files(case)
        for rel in sorted(set(want) | set(files)):
            if rel not in files:
                tc.fail("expected file was not written: " + rel)
            if rel not in want:
                tc.fail("unexpected file written or changed: %s\n%s" % (rel, files[rel][:400].decode("utf-8", "replace")))
            if want[rel] != files[rel]:
                tc.fail("file differs: " + rel + "\n" + show_diff(rel, want[rel], files[rel]))
        tc.assertEqual(deleted, [d.strip() for d in read_lines_file(os.path.join(case, "deleted.txt"))], "deleted files")
        p = os.path.join(case, "stdout.txt")
        want_out = read(p).replace(b"\r\n", b"\n") if os.path.isfile(p) else None
        if want_out is not None:
            tc.assertEqual(out, want_out, "stdout of the last invocation")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_names():
    if not os.path.isdir(CASES):
        return []
    return sorted(n for n in os.listdir(CASES) if os.path.isfile(os.path.join(CASES, n, "args.txt")))


class Conformance(unittest.TestCase):
    """One test per case and implementation (test_<case>__<impl>)."""


def _make(impl, name):
    def test(self):
        run_case(self, impl, os.path.join(CASES, name))
    return test


for _name in case_names():
    for _impl in ("py", "ps1"):
        setattr(Conformance, "test_%s__%s" % (_name.replace("-", "_"), _impl), _make(_impl, _name))


class FixtureSanity(unittest.TestCase):
    def test_generated_transcript_is_big(self):
        data = big_transcript_bytes()
        self.assertGreater(len(data), 3 * 1024 * 1024)
        self.assertEqual(data, big_transcript_bytes())

    def test_no_hangul_in_fixtures(self):
        bad = []
        for dirpath, _, names in os.walk(FIXTURES):
            for n in names:
                text = read(os.path.join(dirpath, n)).decode("utf-8", "replace")
                if re.search("[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3]", text):
                    bad.append(os.path.join(dirpath, n))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
