"""Tests of how `record` behaves when things go wrong or happen at once, run through each implementation:
parallel records (nothing lost, nothing counted twice), a transcript that is not a regular file, errors.log without
paths or ids, bad arguments, and the strict JSON reader that Windows PowerShell 5.1 needs.

The implementation is chosen as in test_conformance.py (run_tests.py --impl).
"""
import base64
import datetime
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

import test_conformance as conf

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
NOW = "2026-10-21T10:02:00+09:00"
IMPLS = ("py", "ps1")


def transcript(n, first_stamp_minute=0, start=0, prompt=True):
    """A transcript of one prompt and n answers (ids a<start>...), one tool call each."""
    lines = []
    if prompt:
        lines.append(json.dumps({"type": "user", "timestamp": "2026-10-21T10:%02d:00.000Z" % first_stamp_minute,
                                 "message": {"role": "user", "content": "do it"}}))
    for i in range(start, start + n):
        lines.append(json.dumps({"type": "assistant", "timestamp": "2026-10-21T10:%02d:%02d.000Z" % (first_stamp_minute, 1 + i % 58),
                                 "message": {"id": "a%d" % i, "model": "claude-sonnet-5-5",
                                             "content": [{"type": "tool_use", "id": "t%d" % i}],
                                             "usage": {"input_tokens": 1, "output_tokens": 2, "cache_read_input_tokens": 3,
                                                       "cache_creation_input_tokens": 4}}}))
    return ("\n".join(lines) + "\n").encode("utf-8")


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.root = conf.posix(os.path.realpath(tempfile.mkdtemp(prefix="sh-")))
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(self.root + "/home")
        os.makedirs(self.root + "/work/repo/.git")
        os.makedirs(self.root + "/transcripts")
        self.lessons = self.root + "/claude/lessons"

    def put(self, name, data):
        p = self.root + "/transcripts/" + name
        with open(p, "wb") as f:
            f.write(data)
        return p

    def append(self, path, data):
        with open(path, "ab") as f:
            f.write(data)

    def env(self, impl):
        env = dict(os.environ)
        for k in conf.CLEAN_ENV:
            env.pop(k, None)
        env["HOME"] = env["USERPROFILE"] = self.root + "/home"
        return conf.impl_env(impl, env)

    def start(self, impl, hook, extra=(), stdin=None, env_extra=None, now=NOW):
        cmd = conf.impl_command(impl)
        args = ["record", "--claude-dir", self.root + "/claude", "--plugin-root", conf.posix(conf.PLUGIN)]
        args += ["--now", now] if now else []
        env = self.env(impl)
        env.update(env_extra or {})
        p = subprocess.Popen(cmd + args + list(extra), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             cwd=self.root, env=env)
        data = hook if isinstance(hook, bytes) else json.dumps(hook).encode("utf-8")
        p.stdin.write(data)
        p.stdin.close()
        p.stdin = None  # Python 3.8 communicate() flushes a closed stdin
        return p

    def finish(self, p, timeout=120):
        try:
            out, err = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
            self.fail("record did not finish within %d s" % timeout)
        return p.returncode, out, err

    def hook_agent(self, agent_id, path, session="sessP"):
        return {"hook_event_name": "SubagentStop", "session_id": session, "cwd": self.root + "/work/repo/src",
                "agent_id": agent_id, "agent_type": "spanharness:coder", "agent_transcript_path": path}

    def hook_turn(self, session, path):
        return {"hook_event_name": "Stop", "session_id": session, "cwd": self.root + "/work/repo/src", "transcript_path": path}

    def records(self):
        p = self.lessons + "/runs/2026-10.jsonl"
        if not os.path.isfile(p):
            return []
        with open(p, "rb") as f:
            return [json.loads(l) for l in f.read().decode("utf-8").split("\n") if l]

    def errors(self):
        p = self.lessons + "/errors.log"
        if not os.path.isfile(p):
            return b""
        with open(p, "rb") as f:
            return f.read()


class Parallel(Sandbox):
    """Several records at the same moment. The transcript summary is made outside the lock, so two records of one
    state file can sum up the same stretch; only one of them may write it."""

    def check(self, impl):
        conf.require(self, impl)
        agents = 6
        paths = {}
        for i in range(1, agents + 1):
            paths["ag%d" % i] = self.put("agent-ag%d.jsonl" % i, transcript(150, i))
        main = self.put("main.jsonl", transcript(150, 30))

        def round_(extra_turns, extra_agents):
            procs = [self.start(impl, self.hook_agent(a, paths[a])) for a in extra_agents]
            procs += [self.start(impl, self.hook_turn("sessP", main)) for _ in range(extra_turns)]
            return [self.finish(p) for p in procs]

        for code, out, err in round_(3, sorted(paths)):
            self.assertEqual((code, out), (0, b""))
        rows = self.records()
        agent_rows = [r for r in rows if r["kind"] == "agent"]
        turn_rows = [r for r in rows if r["kind"] == "turn"]
        self.assertEqual(sorted(r["agent_id"] for r in agent_rows), sorted(paths))
        self.assertTrue(all(r["turns"] == 150 and r["in"] == 150 for r in agent_rows))
        self.assertEqual([(r["turns"], r["in"]) for r in turn_rows], [(150, 150)])
        self.assertEqual(len([r for r in rows if r["kind"] == "harness"]), 1)
        self.assertEqual(self.errors(), b"")

        # a second stretch: new lines for one agent and the session, three records of the session, two of the agent
        self.append(main, transcript(40, 31, start=150, prompt=False))
        self.append(paths["ag1"], transcript(40, 32, start=150, prompt=False))
        procs = [self.start(impl, self.hook_turn("sessP", main)) for _ in range(3)]
        procs += [self.start(impl, self.hook_agent("ag1", paths["ag1"])) for _ in range(2)]
        for code, out, err in [self.finish(p) for p in procs]:
            self.assertEqual((code, out), (0, b""))
        rows = self.records()
        turn_rows = [r for r in rows if r["kind"] == "turn"]
        ag1 = [r for r in rows if r["kind"] == "agent" and r["agent_id"] == "ag1"]
        self.assertEqual([(r["turns"], r["in"]) for r in turn_rows], [(150, 150), (40, 40)])
        self.assertEqual([(r["turns"], r["in"]) for r in ag1], [(150, 150), (40, 40)])
        self.assertEqual(len([r for r in rows if r["kind"] == "agent"]), agents + 1)
        for name, path in (("turn-sessP", main), ("agent-ag1", paths["ag1"])):
            with open(self.lessons + "/state/%s.json" % name, "rb") as f:
                self.assertEqual(json.loads(f.read().decode("utf-8"))["offset"], os.path.getsize(path))
        self.assertEqual(self.errors(), b"")

    def test_nothing_is_lost_or_counted_twice__py(self):
        self.check("py")

    def test_nothing_is_lost_or_counted_twice__ps1(self):
        self.check("ps1")


class Gated(Sandbox):
    """The redo of step 12 (3.2) and the clock of step 13, without any luck in the timing: the test-only gate (3.9) stops
    a record after each summary, and the test does what "another record" would do before it lets the record go on."""

    def setUp(self):
        Sandbox.setUp(self)
        self.gate = self.root + "/gate"
        os.makedirs(self.gate)

    def run_gated(self, impl, hook, steps, **kw):
        """Start a record. For try 1, 2, ... wait until it has reached the gate, call steps[n - 1](), let it go on. Returns
        (code, out, err) once it has finished. Tries that the record does not make are not waited for."""
        p = self.start(impl, hook, env_extra={"SPANHARNESS_TEST_GATE": self.gate}, **kw)
        deadline = time.monotonic() + 120
        for n, step in enumerate(steps, 1):
            reached = self.gate + "/reached-%d" % n
            while not os.path.exists(reached):
                if p.poll() is not None or time.monotonic() > deadline:
                    break
                time.sleep(0.01)
            if not os.path.exists(reached):
                break
            if step is not None:
                step()
            open(self.gate + "/go-%d" % n, "wb").close()
        return self.finish(p)

    def reached(self):
        return sorted(n for n in os.listdir(self.gate) if n.startswith("reached-"))

    def lock_held(self):
        """Is state/lock locked by another process right now? (Opened without creating it.)"""
        path = self.lessons + "/state/lock"
        if not os.path.exists(path):
            return False
        try:
            fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
        except OSError:
            return True                          # Windows: the PowerShell lock is an open without sharing
        try:
            try:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except ImportError:
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return False
        except OSError:
            return True
        finally:
            os.close(fd)

    def saved(self, name):
        with open(self.lessons + "/state/%s.json" % name, "rb") as f:
            return json.loads(f.read().decode("utf-8"))

    def move_offset(self, name, path, offset):
        """What a record that has finished in the meantime leaves: the saved position moved on."""
        os.makedirs(self.lessons + "/state", exist_ok=True)
        with open(self.lessons + "/state/%s.json" % name, "wb") as f:
            f.write(json.dumps({"path": path, "offset": offset}, separators=(",", ":")).encode("utf-8"))

    def kind_rows(self, kind):
        return [r for r in self.records() if r["kind"] == kind]


class Redo(Gated):
    FIRST = 10

    def setup_kind(self, kind):
        """(name of the state file, the hook, the transcript path) with a transcript of a prompt and FIRST answers."""
        path = self.put("t.jsonl", transcript(self.FIRST, 5))
        if kind == "agent":
            return "agent-ag1", self.hook_agent("ag1", path), path
        return "turn-sessP", self.hook_turn("sessP", path), path

    def check_one_redo(self, impl, kind):
        conf.require(self, impl)
        name, hook, path = self.setup_kind(kind)
        first_size = os.path.getsize(path)
        lock_at = []

        def other_record_finishes():
            lock_at.append(self.lock_held())
            self.move_offset(name, path, first_size)             # it has counted the first stretch ...
            self.append(path, transcript(5, 6, start=self.FIRST, prompt=False))      # ... and the file grew

        def nothing_more():
            lock_at.append(self.lock_held())

        code, out, err = self.run_gated(impl, hook, [other_record_finishes, nothing_more])
        self.assertEqual((code, out), (0, b""))
        self.assertEqual(lock_at, [False, False], "the summary is made without the lock")
        self.assertEqual(self.reached(), ["reached-1", "reached-2"])
        rows = self.kind_rows(kind)
        self.assertEqual(len(rows), 1)
        # only the new part: 5 answers of usage 1/2/3/4 and one tool call each, not the first 10
        self.assertEqual([rows[0][k] for k in ("turns", "tools", "in", "out", "cache_read", "cache_write")], [5, 5, 5, 10, 15, 20])
        self.assertEqual(rows[0]["missing"], [])
        self.assertEqual(self.saved(name), {"path": path, "offset": os.path.getsize(path)})
        self.assertEqual(self.errors(), b"")

    def check_nothing_new(self, impl, kind):
        conf.require(self, impl)
        name, hook, path = self.setup_kind(kind)
        size = os.path.getsize(path)
        code, out, err = self.run_gated(impl, hook, [lambda: self.move_offset(name, path, size)])
        self.assertEqual((code, out), (0, b""))
        # the other record has counted everything: the redo finds nothing changed and writes nothing
        self.assertEqual(self.reached(), ["reached-1"])
        self.assertEqual(self.records(), [])
        self.assertEqual(self.saved(name), {"path": path, "offset": size})
        self.assertEqual(self.errors(), b"")

    def check_fourth_try(self, impl, kind):
        conf.require(self, impl)
        name, hook, path = self.setup_kind(kind)
        sizes = [os.path.getsize(path)]
        held = []

        def moved_again(n):
            def step():
                held.append(self.lock_held())
                if n < 4:
                    # a record has counted up to here; the file has 3 answers more
                    self.move_offset(name, path, sizes[-1])
                self.append(path, transcript(3, 7 + n, start=self.FIRST + 3 * n, prompt=False))
                sizes.append(os.path.getsize(path))
                if n == 4:
                    self.move_offset(name, path, 0)              # too late: the record holds the lock
            return step

        code, out, err = self.run_gated(impl, hook, [moved_again(n) for n in (1, 2, 3, 4, 5)])
        self.assertEqual((code, out), (0, b""))
        # tries 1 to 3 do not hold the lock, try 4 holds it from before its summary; there is no try 5
        self.assertEqual(held, [False, False, False, True])
        self.assertEqual(self.reached(), ["reached-%d" % n for n in (1, 2, 3, 4)])
        rows = self.kind_rows(kind)
        self.assertEqual(len(rows), 1)
        # try 4 started where the third other record had stopped (after 3 + 3 new answers) and read up to its own length
        self.assertEqual([rows[0][k] for k in ("turns", "in", "out")], [3, 3, 6])
        self.assertEqual(self.saved(name), {"path": path, "offset": sizes[3]})
        self.assertEqual(self.errors(), b"")

    def test_one_redo_counts_only_the_new_part__agent__py(self):
        self.check_one_redo("py", "agent")

    def test_one_redo_counts_only_the_new_part__agent__ps1(self):
        self.check_one_redo("ps1", "agent")

    def test_one_redo_counts_only_the_new_part__turn__py(self):
        self.check_one_redo("py", "turn")

    def test_one_redo_counts_only_the_new_part__turn__ps1(self):
        self.check_one_redo("ps1", "turn")

    def test_redo_finds_nothing_new__agent__py(self):
        self.check_nothing_new("py", "agent")

    def test_redo_finds_nothing_new__agent__ps1(self):
        self.check_nothing_new("ps1", "agent")

    def test_redo_finds_nothing_new__turn__py(self):
        self.check_nothing_new("py", "turn")

    def test_redo_finds_nothing_new__turn__ps1(self):
        self.check_nothing_new("ps1", "turn")

    def test_the_fourth_try_holds_the_lock_and_ends__agent__py(self):
        self.check_fourth_try("py", "agent")

    def test_the_fourth_try_holds_the_lock_and_ends__agent__ps1(self):
        self.check_fourth_try("ps1", "agent")

    def test_the_fourth_try_holds_the_lock_and_ends__turn__py(self):
        self.check_fourth_try("py", "turn")

    def test_the_fourth_try_holds_the_lock_and_ends__turn__ps1(self):
        self.check_fourth_try("ps1", "turn")


class Clock(Gated):
    """Step 13 takes the time after the lock, not when the process starts (3.2)."""

    def check(self, impl):
        conf.require(self, impl)
        path = self.put("t.jsonl", transcript(3))
        released = []

        def wait_two_seconds():
            time.sleep(2.2)
            released.append(time.time())

        code, out, err = self.run_gated(impl, self.hook_agent("ag1", path), [wait_two_seconds], now=None)
        self.assertEqual((code, out), (0, b""))
        runs = os.listdir(self.lessons + "/runs")
        self.assertEqual(len(runs), 1)
        with open(self.lessons + "/runs/" + runs[0], "rb") as f:
            rows = [json.loads(l) for l in f.read().decode("utf-8").split("\n") if l]
        when = datetime.datetime.strptime(rows[-1]["t"][:19] + rows[-1]["t"][19:].replace(":", ""), "%Y-%m-%dT%H:%M:%S%z").timestamp()
        self.assertGreaterEqual(when, int(released[0]), "t is the time before the wait, not after it")
        self.assertLessEqual(when, time.time())
        self.assertEqual(rows[0]["t"], rows[-1]["t"])
        self.assertEqual(rows[0]["t"][:7], runs[0][:7])

    def test_py(self):
        self.check("py")

    def test_ps1(self):
        self.check("ps1")


class NotARegularFile(Sandbox):
    def check(self, impl, make):
        conf.require(self, impl)
        path = make()
        code, out, err = self.finish(self.start(impl, self.hook_agent("ag1", path)), timeout=60)
        self.assertEqual((code, out), (0, b""))
        rows = [r for r in self.records() if r["kind"] == "agent"]
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["turns"])
        self.assertIn("turns", rows[0]["missing"])

    def fifo(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("no named pipes here")
        p = self.root + "/transcripts/pipe.jsonl"
        os.mkfifo(p)
        return p

    def zero(self):
        if not os.path.exists("/dev/zero"):
            self.skipTest("no /dev/zero here")
        return "/dev/zero"

    def test_named_pipe__py(self):
        self.check("py", self.fifo)

    def test_named_pipe__ps1(self):
        self.check("ps1", self.fifo)

    def test_device__py(self):
        self.check("py", self.zero)

    def test_device__ps1(self):
        self.check("ps1", self.zero)

    def test_folder__py(self):
        self.check("py", lambda: os.makedirs(self.root + "/transcripts/dir.jsonl") or self.root + "/transcripts/dir.jsonl")

    def test_folder__ps1(self):
        self.check("ps1", lambda: os.makedirs(self.root + "/transcripts/dir.jsonl") or self.root + "/transcripts/dir.jsonl")


class ErrorsLogPrivacy(Sandbox):
    """errors.log never holds a path or an id from the hook input (3.6)."""

    def check(self, impl):
        conf.require(self, impl)
        path = self.put("t.jsonl", transcript(3))
        hook = self.hook_agent("agent-SECRETID", path, session="session-SECRETID")
        hook["cwd"] = self.root + "/work/repo/SECRETCWD"
        os.makedirs(self.lessons + "/state/agent-agent-SECRETID.json")      # the read position cannot be saved
        os.makedirs(self.lessons + "/runs/2026-10.jsonl")                    # the record cannot be written
        code, out, err = self.finish(self.start(impl, hook))
        self.assertEqual((code, out), (0, b""))
        log = self.errors().decode("utf-8")
        self.assertIn("could not write the record", log)
        for secret in ("SECRETID", "SECRETCWD", self.root, "state"):
            self.assertNotIn(secret, log)
        # the same with a record that is written but a position that is not
        shutil.rmtree(self.lessons + "/runs/2026-10.jsonl")
        os.remove(self.lessons + "/errors.log")
        code, out, err = self.finish(self.start(impl, hook))
        self.assertEqual((code, out), (0, b""))
        log = self.errors().decode("utf-8")
        self.assertIn("could not save the read position", log)
        for secret in ("SECRETID", "SECRETCWD", self.root):
            self.assertNotIn(secret, log)

    def test_py(self):
        self.check("py")

    def test_ps1(self):
        self.check("ps1")


class BadArguments(Sandbox):
    def check(self, impl):
        conf.require(self, impl)
        path = self.put("t.jsonl", transcript(3))
        hook = self.hook_agent("ag1", path)
        for extra in (["--bogus", "x"], ["--now"], ["extra"], ["--now", "2026-10-21T10:02:00"]):
            cmd = conf.impl_command(impl)
            p = subprocess.Popen(cmd + ["record", "--claude-dir", self.root + "/claude", "--plugin-root", conf.posix(conf.PLUGIN)] + extra,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.root, env=self.env(impl))
            p.stdin.write(json.dumps(hook).encode("utf-8"))
            p.stdin.close()
            p.stdin = None  # Python 3.8 communicate() flushes a closed stdin
            code, out, err = self.finish(p)
            self.assertEqual((code, out), (0, b""), extra)
            self.assertTrue(err.strip(), "a bad argument is reported on stderr: %r" % extra)
            self.assertEqual(self.records(), [])
            self.assertFalse(os.path.exists(self.lessons))

    def test_py(self):
        self.check("py")

    def test_ps1(self):
        self.check("ps1")


# ------------------------------------------------------------------------------------------------
# the strict JSON reader of Windows PowerShell 5.1
# ------------------------------------------------------------------------------------------------

FIXED = ['{}', '[]', '{"a":1}', '[1,2,3]', 'NaN', '[NaN]', '{"a":Infinity}', '{"a":-Infinity}', "{'a':1}", '{a:1}', '{"a":+1}',
         '{"a":.5}', '{"a":5.}', '{"a":01}', '{"a":-0}', '{"a":1e5}', '{"a":1E+5}', '{"a":1.5e-3}', '{"a":1,}', '[1,]', '[,1]',
         '{,}', '{"a":}', '{"a" 1}', '{"a":1 "b":2}', '[1 2]', '{"a":1}{"b":2}', '{"a":1} x', '   ', 'null', 'true', '"s"', '5', '-',
         '{"a":"\\/Date(123)\\/"}', '{"a":"/Date(123)/"}', '{"\\/Date(5)\\/":"\\/Date(5)\\/"}', '["\\u002fDate(1)\\u002f"]',
         '{"a":"\\u002FDate(1)\\/"}', '{"a":"/Dat\\u0065(1)/"}', '{"a":"x\ty"}', '{"a":"x\u0001y"}', '{"a":"\\x"}', '{"a":"\\u12"}',
         '{"a":"\\ud83d"}', '{"a":"\\ud83d\\ude00"}', '{"a":"\u00a0"}', '{"a":1}\u00a0', '\u00a0{"a":1}', '{"a":1}\n', '\n{"a":1}\r\n',
         '{\t"a"\t:\t1\t}', '{"a":tru}', '{"a":truee}', '{"a":True}', '{"a":null,"a":2}', '{"a":{"a":{"a":[[[]]]}}}',
         '{"k":[{"x":1},{"y":[2,3,{"z":null}]}]}', '["a","b",]', '{"a":1,"b":[1,2,{"c":"d\\n\\t\\"\\\\\\/\\b\\f\\r"}]}', '{"":1}',
         '{"a":9223372036854775808}', '{"a":0.1}', '[1e5,2E5,3e+5,4e-5]', '[0,-0,0.0,10,1.0e1]', '[+1]', '[Infinity]', '[1,2,3',
         '{"a":[1,2}', '{"a":1]', '[}', '{]', '[1,2]]', ']', '}', '{"a":"unterminated}', '"\\', '{"a":"b" "c"}', '/* c */{}', '{"a":1 // c\n}']
ALPHABET = list('{}[],:"\\/ \t\n0123456789-+.eE') + ['true', 'false', 'null', 'NaN', 'Infinity', "'", 'a', 'u0041', '\\u00e9', '\x01', 'é', '\u00a0']
LIMIT = 100


def json_corpus():
    rnd = random.Random(20261021)
    scalars = [1, -5, 0, 1.5, -0.25, 1e10, "s", "é\"\\/\n", "", None, True, False, "/Date(1)/", 12345678901234567890]

    def val(d):
        r = rnd.random()
        if d > 4 or r < 0.3:
            return rnd.choice(scalars)
        if r < 0.65:
            return [val(d + 1) for _ in range(rnd.randint(0, 3))]
        return {rnd.choice(["a", "b", "type", "ké", "/Date(1)/"]): val(d + 1) for _ in range(rnd.randint(0, 3))}
    cases = list(FIXED)
    for _ in range(500):
        t = json.dumps(val(0), ensure_ascii=rnd.random() < 0.5, indent=rnd.choice([None, None, 2]))
        if rnd.random() < 0.3:
            cases.append(t)
            continue
        chars = list(t)
        for _ in range(rnd.randint(1, 3)):
            if not chars:
                break
            i = rnd.randrange(len(chars))
            op = rnd.random()
            if op < 0.4:
                del chars[i]
            elif op < 0.8:
                chars.insert(i, rnd.choice(ALPHABET))
            else:
                chars[i] = rnd.choice(ALPHABET)
        cases.append("".join(chars))
    for d in (99, 100, 101):
        cases.append("[" * d + "]" * d)
        cases.append('{"a":' * d + "1" + "}" * d)
    # numbers that are not exact in a double are not specified (section 0)
    return [c for c in cases if not (re.search(r"[0-9]{16}", c) and re.search(r"[.eE]", c))]


DRIVER = r'''
param($lib, $file, $limit)
. $lib
function Canon($v) {
  if ($null -eq $v) { return 'null' }
  if ($v -is [bool]) { return 'b' + [string]$v }
  if ($v -is [string]) { return 's' + (($v.ToCharArray() | ForEach-Object { [int]$_ }) -join ',') }
  if ($v -is [System.Collections.IDictionary]) {
    $p = New-Object System.Collections.Generic.List[string]
    foreach ($k in $v.Keys) { $p.Add((Canon $k) + '=' + (Canon $v[$k])) }
    $a = $p.ToArray(); [Array]::Sort($a, [System.StringComparer]::Ordinal)
    return '{' + ($a -join ';') + '}'
  }
  if ($v -is [System.Collections.IList]) { $p = @(); foreach ($x in $v) { $p += (Canon $x) }; return '[' + ($p -join ';') + ']' }
  $n = Get-Number $v
  if ($null -eq $n) { return 'nnull' }
  return 'n' + [string]$n
}
foreach ($line in [System.IO.File]::ReadAllLines($file)) {
  $t = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($line))
  if ($t.Length -gt 0 -and (Test-StrictJson $t $limit)) { 'S ok ' + (Canon (ConvertFrom-StrictJson $t)) } else { 'S bad' }
  if (Try-ParseJson $t $limit) { 'P ok ' + (Canon $script:JsonValue) } else { 'P bad' }
}
'''


def canon(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "b" + str(v)
    if isinstance(v, str):
        return "s" + ",".join(str(u) for u in memoryview(v.encode("utf-16-le", "surrogatepass")).cast("H"))
    if isinstance(v, (int, float)):
        n = SH.number(v)
        return "n" + ("null" if n is None else str(n))
    if isinstance(v, list):
        return "[" + ";".join(canon(x) for x in v) + "]"
    return "{" + ";".join(sorted(canon(k) + "=" + canon(x) for k, x in v.items())) + "}"


def _load_py():
    import importlib.util
    spec = importlib.util.spec_from_file_location("spanharness_robust", os.path.join(REPO, "scripts", "spanharness.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SH = _load_py()


class StrictJson(unittest.TestCase):
    """Test-StrictJson and ConvertFrom-StrictJson (the reader of Windows PowerShell 5.1) and Try-ParseJson (whatever
    reader the host uses: JavaScriptSerializer on 5.1, System.Text.Json on 7) accept exactly what Python accepts and read
    the same values. On a host with PowerShell 7 only the first two run the 5.1 code; the Windows CI runs all three."""

    def test_accepts_exactly_rfc_8259_json(self):
        conf.require(self, "ps1")
        tmp = tempfile.mkdtemp(prefix="sh-")
        self.addCleanup(shutil.rmtree, tmp, True)
        with open(conf.SCRIPTS["ps1"], "rb") as f:
            src = f.read().decode("ascii")
        marker = "$script:ExitCode = 0\ntry {"
        text = src.replace("\r\n", "\n")
        self.assertEqual(text.count(marker), 1, "the main call of scripts/spanharness.ps1 was not found exactly once")
        lib = os.path.join(tmp, "lib.ps1")
        with open(lib, "wb") as f:
            f.write(text[:text.index(marker)].encode("ascii"))
        driver = os.path.join(tmp, "driver.ps1")
        with open(driver, "wb") as f:
            f.write(DRIVER.encode("ascii"))
        corpus = json_corpus()
        data = os.path.join(tmp, "corpus.txt")
        with open(data, "w") as f:
            for c in corpus:
                f.write(base64.b64encode(c.encode("utf-8", "surrogatepass")).decode("ascii") + "\n")
        want = []
        for c in corpus:
            try:
                r = "ok " + canon(SH.parse_json(c, LIMIT))
            except ValueError:
                r = "bad"
            want.append(r)
        cmd = conf.impl_command("ps1")
        # the script itself is not run: lib is the script without its last lines, dot-sourced by the driver
        exe = cmd[:cmd.index("-File")]
        env = conf.impl_env("ps1", dict(os.environ, HOME=tmp))
        done = subprocess.run(exe + ["-File", driver, lib, data, str(LIMIT)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=600)
        got = done.stdout.decode("utf-8").replace("\r\n", "\n").split("\n")
        got = [g for g in got if g]
        self.assertEqual(len(got), 2 * len(corpus), done.stderr.decode("utf-8", "replace")[:500])
        for i, c in enumerate(corpus):
            self.assertEqual(got[2 * i], "S " + want[i], "strict reader: %r" % c)
            self.assertEqual(got[2 * i + 1], "P " + want[i], "Try-ParseJson: %r" % c)


if __name__ == "__main__":
    unittest.main()
