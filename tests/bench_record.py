#!/usr/bin/env python3
"""Time the first `record` (no saved state) of one implementation on synthetic transcripts. Not part of the test suite
(run_tests.py does not collect it); standard library only.

    python3 tests/bench_record.py                       Python implementation
    python3 tests/bench_record.py --impl ps1            PowerShell (powershell.exe on Windows, else pwsh; SPANHARNESS_PWSH)
    python3 tests/bench_record.py --sizes 1,4,16 --runs 3

The transcripts have the shape Claude Code writes: assistant lines with usage and tool_use blocks, user lines whose
tool_result content is large, typed prompts. Two kinds are timed, each with a fresh lessons folder (so no saved state, and
the harness line is written too):

  agent   one prompt at the top and the whole file is the stretch to count;
  turn    a long resumed session with many earlier prompts and no saved offset; the last typed prompt is near the end,
          so only the last ~150 KB is the turn (spec 3.3, summarize_turn).

The wall time of the whole process is measured, as the hook sees it, so it includes the start of the interpreter; the
first row ("baseline") is a tiny transcript and shows that part alone. One table goes to stdout, the rest to stderr.
"""
import argparse
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_conformance as conf  # noqa: E402

MB = 1024 * 1024
LAST_TURN = 150 * 1024
RESULT_SIZES = (800, 2000, 5000, 12000, 40000)
RESULT_WEIGHTS = (30, 30, 20, 15, 5)
WORDS = ("src", "lib", "main", "test", "config", "value", "return", "import", "class", "def", "error", "result", "path", "name")


class Builder(object):
    def __init__(self, seed):
        self.rnd = random.Random(seed)
        self.n = 0
        self.t = 1760000000
        self.answers = []        # ids of the answers, in order
        self.tools = 0

    def stamp(self):
        self.t += self.rnd.randint(2, 30)
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(self.t)) + ".%03dZ" % self.rnd.randint(0, 999)

    def words(self, n):
        return " ".join(self.rnd.choice(WORDS) for _ in range(n))

    def meta(self, typ):
        self.n += 1
        return {"parentUuid": "%08x-0000-4000-8000-%012x" % (self.n - 1, self.n), "isSidechain": False, "userType": "external",
                "cwd": "/work/repo/src", "sessionId": "bench-session", "version": "2.1.0", "gitBranch": "main", "type": typ,
                "uuid": "%08x-0000-4000-8000-%012x" % (self.n, self.n + 1), "timestamp": self.stamp()}

    def prompt(self):
        d = self.meta("user")
        d["message"] = {"role": "user", "content": "please " + self.words(self.rnd.randint(8, 40))}
        return json.dumps(d)

    def answer(self, with_tool):
        """One answer written as two lines (text block, tool_use block) that share the id and the usage."""
        mid = "msg_%06d" % (len(self.answers) + 1)
        self.answers.append(mid)
        usage = {"input_tokens": self.rnd.randint(1, 50), "cache_creation_input_tokens": self.rnd.randint(0, 3000),
                 "cache_read_input_tokens": self.rnd.randint(10000, 90000), "output_tokens": self.rnd.randint(20, 900),
                 "service_tier": "standard"}
        out = []
        blocks = [[{"type": "text", "text": self.words(self.rnd.randint(30, 120))}]]
        if with_tool:
            self.tools += 1
            blocks.append([{"type": "tool_use", "id": "toolu_%06d" % self.tools, "name": "Bash",
                            "input": {"command": "grep -rn %s %s | head -50" % (self.rnd.choice(WORDS), self.rnd.choice(WORDS)),
                                      "description": self.words(6)}}])
        for content in blocks:
            d = self.meta("assistant")
            d["message"] = {"id": mid, "type": "message", "role": "assistant", "model": "claude-sonnet-5-5", "content": content,
                            "stop_reason": None, "stop_sequence": None, "usage": usage}
            d["requestId"] = "req_%06d" % len(self.answers)
            out.append(json.dumps(d))
        return out

    def tool_result(self):
        size = self.rnd.choices(RESULT_SIZES, RESULT_WEIGHTS)[0]
        body = "\n".join("%s/%s.py:%d: %s" % (self.rnd.choice(WORDS), self.rnd.choice(WORDS), self.rnd.randint(1, 900), self.words(8))
                         for _ in range(size // 60 + 1))[:size]
        d = self.meta("user")
        d["message"] = {"role": "user", "content": [{"tool_use_id": "toolu_%06d" % self.tools, "type": "tool_result", "content": body}]}
        d["toolUseResult"] = {"stdout": body[:200], "stderr": "", "interrupted": False}
        return json.dumps(d)

    def turn(self, size):
        """A typed prompt, then tool cycles until about `size` bytes, then a closing answer."""
        lines = [self.prompt()]
        total = len(lines[0])
        while total < size:
            for ln in self.answer(True) + [self.tool_result()]:
                lines.append(ln)
                total += len(ln) + 1
        lines += self.answer(False)
        return lines


def build(total, last_turn):
    """(bytes, answers counted, tool calls counted) for a session of about `total` bytes whose last turn is about
    `last_turn` bytes; with last_turn >= total it is one turn (an agent run)."""
    b = Builder(total)
    lines = []
    size = 0
    while total - size > last_turn:
        part = b.turn(min(random.Random(size).randint(60000, 400000), total - last_turn - size))
        lines += part
        size += sum(len(x) + 1 for x in part)
    counted_from = (len(b.answers), b.tools)
    part = b.turn(min(last_turn, total))
    lines += part
    data = ("\n".join(lines) + "\n").encode("utf-8")
    return data, len(b.answers) - counted_from[0], b.tools - counted_from[1]


class Bench(object):
    def __init__(self, impl, tmp):
        self.cmd = conf.impl_command(impl)
        if self.cmd is None:
            raise SystemExit("bench_record: %s cannot run here (no PowerShell found?)" % impl)
        self.impl = impl
        self.tmp = tmp
        self.env = conf.impl_env(impl, dict(os.environ, HOME=tmp + "/home", USERPROFILE=tmp + "/home"))
        for k in conf.CLEAN_ENV:
            self.env.pop(k, None)
        os.makedirs(tmp + "/home")
        os.makedirs(tmp + "/work/repo/.git")
        self.runs = 0

    def once(self, kind, path, timeout):
        """Seconds of one record with no saved state, and the record line it wrote."""
        self.runs += 1
        claude = "%s/claude%d" % (self.tmp, self.runs)
        hook = {"hook_event_name": "SubagentStop" if kind == "agent" else "Stop", "session_id": "bench-session",
                "cwd": self.tmp + "/work/repo/src"}
        if kind == "agent":
            hook.update(agent_id="bench-agent", agent_type="spanharness:coder", agent_transcript_path=path)
        else:
            hook["transcript_path"] = path
        args = ["record", "--claude-dir", claude, "--plugin-root", conf.posix(conf.PLUGIN)]
        start = time.perf_counter()
        done = subprocess.run(self.cmd + args, input=json.dumps(hook).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              cwd=self.tmp, env=self.env, timeout=timeout)
        elapsed = time.perf_counter() - start
        row = None
        runs = os.path.join(claude, "lessons", "runs")
        if done.returncode == 0 and os.path.isdir(runs):
            with open(os.path.join(runs, os.listdir(runs)[0]), "rb") as f:
                row = json.loads(f.read().decode("utf-8").split("\n")[-2])
        shutil.rmtree(claude, True)
        return elapsed, row


def main(argv=None):
    ap = argparse.ArgumentParser(description="Time the first record of one implementation on synthetic transcripts.")
    ap.add_argument("--impl", choices=("py", "ps1"), default="py")
    ap.add_argument("--sizes", default="1,4,16", help="transcript sizes in MB, comma separated (default 1,4,16)")
    ap.add_argument("--runs", type=int, default=3, help="timed runs per row (default 3)")
    ap.add_argument("--timeout", type=int, default=1200, help="seconds allowed to one run (default 1200)")
    args = ap.parse_args(argv)
    sizes = [float(x) for x in args.sizes.split(",") if x.strip()]

    tmp = tempfile.mkdtemp(prefix="sh-bench-")
    rows = []
    try:
        bench = Bench(args.impl, tmp)
        if args.impl == "ps1":
            probe = subprocess.run(bench.cmd[:bench.cmd.index("-File")] + ["-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=bench.env)
            sys.stderr.write("PowerShell %s\n" % probe.stdout.decode("utf-8", "replace").strip())
        sys.stderr.write("Python %s, %s\n" % (sys.version.split()[0], sys.platform))
        plan = [("baseline", "agent", 8 * 1024)] + [(None, k, int(s * MB)) for s in sizes for k in ("agent", "turn")]
        for label, kind, total in plan:
            data, answers, tools = build(total, total if kind == "agent" else LAST_TURN)
            path = "%s/t-%s-%d.jsonl" % (tmp, kind, total)
            with open(path, "wb") as f:
                f.write(data)
            times, ok = [], True
            for i in range(args.runs):
                try:
                    secs, row = bench.once(kind, path, args.timeout)
                except subprocess.TimeoutExpired:
                    times, ok = [], False
                    break
                times.append(secs)
                if row is None or row.get("turns") != answers or row.get("tools") != tools:
                    ok = False
                sys.stderr.write("  %s %s %.1f MB run %d: %.2f s\n" % (args.impl, kind, len(data) / MB, i + 1, secs))
            os.remove(path)
            rows.append((args.impl, label or kind, "%.2f" % (len(data) / MB), str(answers),
                         ["%.2f" % min(times), "%.2f" % statistics.median(times), "%.2f" % max(times)] if times else ["-", "-", "-"],
                         "ok" if ok else "WRONG"))
    finally:
        shutil.rmtree(tmp, True)

    header = ("impl", "kind", "MB", "answers counted", "min s", "median s", "max s", "record")
    table = [header] + [(r[0], r[1], r[2], r[3], r[4][0], r[4][1], r[4][2], r[5]) for r in rows]
    widths = [max(len(row[i]) for row in table) for i in range(len(header))]
    for n, row in enumerate(table):
        sys.stdout.write("  ".join(c.ljust(widths[i]) if i < 2 or i == 7 else c.rjust(widths[i]) for i, c in enumerate(row)).rstrip() + "\n")
        if n == 0:
            sys.stdout.write("  ".join("-" * w for w in widths) + "\n")
    return 0 if all(r[5] == "ok" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
