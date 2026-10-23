"""Unit tests for `record`: transcript summary, project name, harness fingerprint and the record flow.

The pure functions are tested in-process (the module is loaded from scripts/spanharness.py); the flows run the
script as a child process (`python3 -I`), the way the hook starts it. These tests are for the Python implementation
only; the cases in tests/fixtures/cases are the shared contract for both implementations.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "spanharness.py")
PLUGIN_FIXTURE = os.path.join(HERE, "fixtures", "plugin")

sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location("spanharness_under_test", SCRIPT)
sh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sh)

MODEL = "claude-sonnet-4-5-20250929"
NOW = "2026-10-21T10:02:00+09:00"
MONTH_FILE = os.path.join("runs", "2026-10.jsonl")
SECRET = "Ceci ne doit pas rester dans les fichiers"   # stands for last_assistant_message
BODY = "Le texte de la conversation ne compte pas"


# ----------------------------------------------------------------------------------------------
# transcript lines the way Claude Code writes them (only the keys we read)
# ----------------------------------------------------------------------------------------------

def line(kind, stamp, message=None, **extra):
    d = {"type": kind, "timestamp": stamp}
    if message is not None:
        d["message"] = message
    d.update(extra)
    return json.dumps(d, ensure_ascii=False)


def line_bytes(text):
    return (text + "\n").encode("utf-8")


def said(text):
    return {"role": "user", "content": text}


def said_blocks(text):
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def tool_back(tool_id):
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": "ok"}]}


def answer(mid, usage, *tools, model=MODEL):
    m = {"id": mid, "model": model, "content": [{"type": "tool_use", "id": t} for t in tools]}
    if usage is not None:
        m["usage"] = dict(zip(("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"), usage))
    return m


def system(stamp, subtype):
    return line("system", stamp, subtype=subtype)


HUMAN = {"origin": {"kind": "human"}}


def joined(lines):
    return "\n".join(lines) + "\n"


def write(path, text, newline="\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(text.replace("\n", newline).encode("utf-8"))


def slurp(path):
    with open(path, "rb") as f:
        return f.read()


def read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        return [json.loads(l) for l in f.read().decode("utf-8").split("\n") if l]


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="spanharness-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)


# ----------------------------------------------------------------------------------------------
# 3.3 transcript summary
# ----------------------------------------------------------------------------------------------

AGENT_LINES = [
    line("user", "2026-10-21T10:00:00.000Z", said(BODY)),
    line("assistant", "2026-10-21T10:00:05.000Z", answer("m1", [10, 5, 100, 20], "t1")),
    line("assistant", "2026-10-21T10:00:06.000Z", answer("m1", [10, 5, 100, 20], "t2")),
    "{this line is not JSON",
    line("assistant", "2026-10-21T10:01:30.500Z", answer("m2", [7, 3, 50, 0])),
]


class Summary(TempCase):
    def agent_file(self):
        p = self.path("agent.jsonl")
        write(p, joined(AGENT_LINES))
        return p

    def test_same_message_id_counts_once(self):
        s = sh.summarize(self.agent_file(), 0)
        self.assertEqual((s["in"], s["out"], s["cache_read"], s["cache_write"]), (17, 8, 150, 20))
        self.assertEqual((s["tools"], s["turns"], s["ms"], s["model"]), (2, 2, 90500, MODEL))
        self.assertEqual(s["broken"], 1)

    def test_no_usage_leaves_values_null(self):
        p = self.path("bare.jsonl")
        write(p, joined([line("assistant", "2026-10-21T10:00:00.000Z", answer("m1", None))]))
        s = sh.summarize(p, 0)
        self.assertIsNone(s["in"])
        self.assertIsNone(s["cache_write"])
        self.assertEqual((s["turns"], s["tools"], s["model"]), (1, 0, MODEL))

    def test_missing_file_counts_nothing_and_keeps_offset(self):
        s = sh.summarize(self.path("nothing.jsonl"), 0)
        self.assertTrue(all(s[k] is None for k in ("in", "out", "cache_read", "cache_write", "tools", "turns", "ms", "model")))
        self.assertEqual(s["offset"], 0)
        self.assertFalse(s["unchanged"])
        self.assertEqual(sh.summarize(self.path("nothing.jsonl"), 77)["offset"], 77)
        self.assertIsNone(sh.summarize(None, 5)["turns"])

    def test_read_error_partway_counts_nothing_and_keeps_offset(self):
        p = self.agent_file()
        real = sh._read_lines

        def boom(f, start, size, res):
            res["in"] = 999      # a partial result that must not survive
            raise OSError("disk went away")
        sh._read_lines = boom
        try:
            s = sh.summarize(p, 12)
        finally:
            sh._read_lines = real
        self.assertEqual((s["in"], s["turns"], s["offset"], s["unchanged"], s["broken"]), (None, None, 12, False, 0))

    def test_incremental_reading_and_line_in_progress(self):
        p = self.path("main.jsonl")
        write(p, joined([line("user", "2026-10-21T11:00:00.000Z"),
                         line("assistant", "2026-10-21T11:00:02.000Z", answer("a1", [1, 2, 3, 4], "x1"))]))
        length1 = os.path.getsize(p)
        whole = line("assistant", "2026-10-21T11:00:09.000Z", answer("a2", [5, 6, 7, 8]))
        unfinished = line("assistant", "2026-10-21T11:00:12.000Z", answer("a3", [1, 1, 1, 1]))
        t1 = sh.summarize(p, 0)
        half = len(unfinished) // 2
        with open(p, "ab") as f:
            f.write((whole + "\n" + unfinished[:half]).encode("utf-8"))
        t2 = sh.summarize(p, t1["offset"])
        with open(p, "ab") as f:
            f.write((unfinished[half:] + "\n").encode("utf-8"))
        t3 = sh.summarize(p, t2["offset"])
        t4 = sh.summarize(p, t3["offset"])
        self.assertEqual((t1["turns"], t1["tools"], t1["offset"]), (1, 1, length1))
        self.assertEqual((t2["turns"], t2["in"], t2["offset"], t2["broken"]), (1, 5, length1 + len(whole.encode("utf-8")) + 1, 0))
        self.assertEqual((t3["turns"], t3["in"], t3["offset"]), (1, 1, os.path.getsize(p)))
        self.assertEqual((t4["turns"], t4["offset"], t4["unchanged"]), (None, t3["offset"], True))

    def test_complete_json_without_final_newline_is_counted(self):
        p = self.path("nonl.jsonl")
        text = line("assistant", "2026-10-21T11:00:02.000Z", answer("a1", [1, 2, 3, 4]))
        write(p, text)
        s = sh.summarize(p, 0)
        self.assertEqual((s["turns"], s["offset"]), (1, len(text.encode("utf-8"))))

    def test_crlf_gives_the_same_values_and_byte_offsets(self):
        p = self.path("crlf.jsonl")
        write(p, joined(AGENT_LINES), "\r\n")
        s = sh.summarize(p, 0)
        self.assertEqual((s["in"], s["out"], s["tools"], s["turns"], s["ms"], s["broken"]), (17, 8, 2, 2, 90500, 1))
        self.assertEqual(s["offset"], os.path.getsize(p))
        head = len("\r\n".join(AGENT_LINES[:3]).encode("utf-8")) + 2
        rest = sh.summarize(p, head)
        self.assertEqual((rest["turns"], rest["in"], rest["broken"]), (1, 7, 1))

    def test_offset_beyond_the_end_or_negative_starts_over(self):
        p = self.agent_file()
        size = os.path.getsize(p)
        for offset in (size + 1000, -5):
            s = sh.summarize(p, offset)
            self.assertEqual((s["in"], s["turns"], s["offset"]), (17, 2, size), offset)
        self.assertTrue(sh.summarize(p, size)["unchanged"])
        self.assertFalse(sh.summarize(p, 0)["unchanged"])

    def test_multibyte_text_across_the_read_buffer(self):
        model = "claude-\u03b1\u03b2\u03b3\u03b4-20250929"
        row = line("assistant", "2026-10-21T12:00:05.000Z", answer("h1", [1, 2, 3, 4], "ht1", model=model)) + "\n"
        before = len(row[:row.index("\u03b1")].encode("utf-8"))
        empty_head = len((line("user", "2026-10-21T12:00:00.000Z", said("")) + "\n").encode("utf-8"))
        for cut in (1, 2):
            head = line("user", "2026-10-21T12:00:00.000Z", said("x" * (64 * 1024 - cut - empty_head - before))) + "\n"
            p = self.path("wide.jsonl")
            write(p, head + row)
            self.assertEqual(len(head.encode("utf-8")) + before, 64 * 1024 - cut)    # the setup itself
            s = sh.summarize(p, 0)
            self.assertEqual((s["model"], s["turns"], s["in"], s["tools"], s["broken"], s["offset"]),
                             (model, 1, 1, 1, 0, os.path.getsize(p)), cut)

    def test_time_comes_from_user_and_assistant_lines_only(self):
        head = [line("assistant", "2026-10-21T11:00:00.000Z", answer("i1", [1, 1, 1, 1])),
                line("assistant", "2026-10-21T11:00:10.000Z", answer("i2", [1, 1, 1, 1]))]
        tail = [system("2026-10-21T11:00:11.000Z", "turn_duration"),
                system("2026-10-21T11:30:00.000Z", "stop_hook_summary"),
                line("user", "2026-10-21T11:40:00.000Z", said("next")),
                line("assistant", "2026-10-21T11:40:05.000Z", answer("i3", [1, 1, 1, 1])),
                system("2026-10-21T11:55:00.000Z", "turn_duration")]
        p = self.path("idle.jsonl")
        write(p, joined(head + tail))
        nxt = sh.summarize(p, len(joined(head).encode("utf-8")))
        self.assertEqual((nxt["turns"], nxt["ms"]), (1, 5000))
        self.assertEqual(sh.summarize(p, 0)["ms"], 40 * 60 * 1000 + 5000)

    def test_only_typed_text_is_a_prompt(self):
        shapes = [
            ("string", said("hi"), {}, True),
            ("text blocks", said_blocks("hi"), {}, True),
            ("origin human", said("hi"), HUMAN, True),
            ("tool result", tool_back("t1"), {}, False),
            ("isMeta", said("hi"), {"isMeta": True}, False),
            ("origin other session", said("hi"), {"origin": {"kind": "peer"}}, False),
            ("compaction summary", said("hi"), {"isCompactSummary": True}, False),
            ("blank text", said("  "), {}, False),
            ("no message", None, {}, False),
        ]
        first = line("user", "2026-10-21T13:00:00.000Z", said("first prompt")) + "\n"
        p = self.path("shape.jsonl")
        wrong = []
        for name, message, extra, is_prompt in shapes:
            write(p, first + line("user", "2026-10-21T13:00:01.000Z", message, **extra) + "\n")
            want = len(first.encode("utf-8")) if is_prompt else 0
            if sh.summarize(p, 0)["last_prompt"] != want:
                wrong.append(name)
        self.assertEqual(wrong, [])

    EARLIER = [
        line("user", "2026-10-21T11:00:00.000Z", said(BODY)),
        line("assistant", "2026-10-21T11:00:05.000Z", answer("r1", [100, 10, 1000, 50], "rt1")),
        line("user", "2026-10-21T11:00:06.000Z", tool_back("rt1")),
        line("assistant", "2026-10-21T11:00:09.000Z", answer("r2", [200, 20, 2000, 0])),
        system("2026-10-21T11:00:10.000Z", "turn_duration"),
    ]
    LATEST = [
        line("user", "2026-10-21T11:10:00.000Z", said_blocks(BODY), **HUMAN),
        line("assistant", "2026-10-21T11:10:04.000Z", answer("r3", [1, 2, 3, 4], "rt2", "rt3")),
        line("user", "2026-10-21T11:10:05.000Z", tool_back("rt2")),
        line("user", "2026-10-21T11:10:06.000Z", said(BODY), isMeta=True),
        line("user", "2026-10-21T11:10:07.000Z", said(BODY), origin={"kind": "peer"}),
        line("user", "2026-10-21T11:10:08.000Z", said(BODY), isCompactSummary=True),
        line("assistant", "2026-10-21T11:10:12.000Z", answer("r4", [10, 20, 30, 40])),
        system("2026-10-21T11:10:13.000Z", "turn_duration"),
    ]

    def test_turn_without_saved_offset_starts_at_the_last_prompt(self):
        p = self.path("resume.jsonl")
        write(p, joined(self.EARLIER + self.LATEST))
        self.assertEqual(sh.summarize(p, 0)["last_prompt"], len(joined(self.EARLIER).encode("utf-8")))
        t = sh.summarize_turn(p, None)
        self.assertEqual((t["turns"], t["tools"], t["in"], t["out"], t["cache_read"], t["cache_write"], t["ms"], t["offset"]),
                         (2, 2, 11, 22, 33, 44, 12000, os.path.getsize(p)))

    def test_turn_with_saved_offset_ignores_the_last_prompt_rule(self):
        p = self.path("resume.jsonl")
        write(p, joined(self.EARLIER + self.LATEST))
        t = sh.summarize_turn(p, len(joined(self.EARLIER[:2]).encode("utf-8")))
        self.assertEqual((t["turns"], t["in"]), (3, 211))

    def test_first_turn_of_a_new_session_counts_all(self):
        p = self.path("fresh.jsonl")
        write(p, joined([line("queue-operation", "2026-10-21T14:00:00.000Z", operation="enqueue"),
                         line("user", "2026-10-21T14:00:01.000Z", said(BODY), **HUMAN),
                         line("assistant", "2026-10-21T14:00:05.000Z", answer("f1", [3, 1, 4, 1], "ft1")),
                         line("user", "2026-10-21T14:00:06.000Z", tool_back("ft1")),
                         line("assistant", "2026-10-21T14:00:09.000Z", answer("f2", [5, 9, 2, 6]))]))
        t = sh.summarize_turn(p, None)
        self.assertEqual((t["turns"], t["tools"], t["in"], t["out"], t["ms"]), (2, 1, 8, 10, 8000))
        self.assertEqual(t["in"], sh.summarize(p, 0)["in"])

    def turn_files(self):
        """Transcripts of every shape that decides where the last prompt is (name, bytes)."""
        first = line("user", "2026-10-21T15:00:00.000Z", said("première ☃ \U0001f600"))
        ask = line("user", "2026-10-21T15:01:00.000Z", said_blocks("deux éè \U0001f600"), **HUMAN)
        tool = line("user", "2026-10-21T15:01:02.000Z", tool_back("x1"))
        asst = line("assistant", "2026-10-21T15:01:03.000Z", answer("z1", [1, 2, 3, 4], "x1"))
        escaped = '{"\\u0074ype":"\\u0075ser","timestamp":"2026-10-21T15:02:00.000Z","message":{"role":"user","content":"esc"}}'
        wide = line("user", "2026-10-21T15:03:00.000Z", tool_back("w1")).replace('"ok"', '"%s"' % ("λ" * 300))
        junk = "{not json at all"
        files = [
            ("empty", b""),
            ("one prompt", line_bytes(first)),
            ("no prompt", joined([tool, asst]).encode("utf-8")),
            ("prompt then answers", joined([first, asst, tool, asst]).encode("utf-8")),
            ("two prompts", joined([first, asst, ask, tool, asst, system("2026-10-21T15:01:04.000Z", "turn_duration")]).encode("utf-8")),
            ("escaped type", joined([first, asst, escaped, asst]).encode("utf-8")),
            ("wide lines", joined([first, wide, asst, ask, wide, wide, asst]).encode("utf-8")),
            ("broken lines", joined([first, junk, ask, junk, asst, junk]).encode("utf-8")),
            ("blank lines", ("\n\n" + joined([first, "", " \t ", ask, "", asst])).encode("utf-8")),
            ("crlf", joined([first, asst, ask, asst]).replace("\n", "\r\n").encode("utf-8")),
            ("bom, prompt first", b"\xef\xbb\xbf" + joined([first, asst]).encode("utf-8")),
            ("bom, prompt only", b"\xef\xbb\xbf" + line_bytes(first)),
            ("bom inside", joined([first, asst]).encode("utf-8") + b"\xef\xbb\xbf" + line_bytes(ask)),
            ("last line without line feed", joined([first, asst, ask]).encode("utf-8")[:-1]),
            ("last line is a partial prompt", (joined([first, asst]) + ask[:40]).encode("utf-8")),
            ("last line is a partial prompt, cut in a character", joined([first, asst]).encode("utf-8") + ask.encode("utf-8")[:ask.index("é") + 1]),
            ("invalid utf-8", joined([first, asst]).encode("utf-8") + b'{"type":"user","message":{"content":"\xff\xfe"}}\n'),
            ("lone prompt line, no line feed", ask.encode("utf-8")),
        ]
        return files

    def test_last_prompt_read_from_the_end_is_the_one_the_whole_file_gives(self):
        p = self.path("shapes.jsonl")
        for name, data in self.turn_files():
            with open(p, "wb") as f:
                f.write(data)
            want = sh.summarize(p, 0)["last_prompt"]
            for block in (1, 2, 5, 17, 64, 65536):
                self.assertEqual(sh.last_prompt_start(p, block), want, "%s, block %d" % (name, block))

    def test_turn_without_saved_offset_and_nothing_to_read(self):
        os.makedirs(self.path("folder.jsonl"))
        for name in (None, self.path("missing.jsonl"), self.path("folder.jsonl")):
            self.assertIsNone(sh.last_prompt_start(name), name)
            self.assertEqual(sh.summarize_turn(name, None), sh.summarize(name, 0), name)

    def test_turn_without_saved_offset_equals_the_whole_file_rule(self):
        p = self.path("shapes.jsonl")
        for name, data in self.turn_files():
            with open(p, "wb") as f:
                f.write(data)
            whole = sh.summarize(p, 0)
            lp = whole["last_prompt"]
            want = sh.summarize(p, lp) if lp is not None and lp != 0 else whole
            self.assertEqual(sh.summarize_turn(p, None), want, name)

    def test_turn_without_saved_offset_does_not_read_before_the_last_prompt(self):
        def padded(i):
            m = answer("e%d" % i, [1, 1, 1, 1])
            m["pad"] = "x" * 1000
            return line("assistant", "2026-10-21T16:00:00.000Z", m)
        early = [padded(i) for i in range(3000)]       # about 3 MB
        tail = [line("user", "2026-10-21T16:10:00.000Z", said("go")), line("assistant", "2026-10-21T16:10:05.000Z", answer("t1", [5, 6, 7, 8]))]
        p = self.path("long.jsonl")
        write(p, joined(early + tail))
        size = os.path.getsize(p)
        read = []
        real = sh.open_regular

        class Counting(object):
            def __init__(self, f):
                self.f = f

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.f.close()

            def read(self, *a):
                d = self.f.read(*a)
                read.append(len(d))
                return d

            def readline(self, *a):
                d = self.f.readline(*a)
                read.append(len(d))
                return d

            def __getattr__(self, k):
                return getattr(self.f, k)

        sh.open_regular = lambda path: Counting(real(path))
        try:
            t = sh.summarize_turn(p, None)
        finally:
            sh.open_regular = real
        self.assertEqual((t["turns"], t["in"], t["offset"]), (1, 5, size))
        self.assertLess(sum(read), 200 * 1024, "read %d of %d bytes" % (sum(read), size))

    def test_nothing_after_the_length_seen_at_the_start_is_read(self):
        p = self.agent_file()
        size = os.path.getsize(p)
        with open(p, "rb") as f:
            first_two = len(f.readline()) + len(f.readline())
        res = {"in": None, "out": None, "cache_read": None, "cache_write": None, "tools": None, "turns": None,
               "ms": None, "model": None, "offset": 0, "unchanged": False, "last_prompt": None, "broken": 0}
        with open(p, "rb") as f:
            s = sh._read_lines(f, 0, first_two - 5, res)      # the file "grew" after the length was taken
        self.assertEqual(s["offset"], 0 + len(line_bytes(AGENT_LINES[0])))     # line 2 was cut short: left for the next time
        self.assertEqual(s["turns"], None)
        self.assertGreater(size, first_two)

    def test_only_a_regular_file_is_read(self):
        os.mkdir(self.path("folder"))
        s = sh.summarize(self.path("folder"), 7)
        self.assertEqual((s["turns"], s["offset"], s["unchanged"]), (None, 7, False))
        if hasattr(os, "mkfifo"):
            os.mkfifo(self.path("pipe"))
            started = time.time()
            s = sh.summarize(self.path("pipe"), 0)      # must not wait for a writer
            self.assertLess(time.time() - started, 5)
            self.assertEqual((s["turns"], s["offset"], s["unchanged"]), (None, 0, False))
        if os.path.exists("/dev/zero"):
            self.assertIsNone(sh.summarize("/dev/zero", 0)["turns"])

    def test_a_byte_order_mark_is_removed_from_the_first_line_only(self):
        p = self.path("bom.jsonl")
        bom = b"\xef\xbb\xbf"
        a = line("assistant", "2026-10-21T10:00:05.000Z", answer("m1", [1, 2, 3, 4]))
        b = line("assistant", "2026-10-21T10:00:06.000Z", answer("m2", [1, 2, 3, 4]))
        with open(p, "wb") as f:
            f.write(bom + a.encode("utf-8") + b"\n" + bom + b.encode("utf-8") + b"\n")
        s = sh.summarize(p, 0)
        self.assertEqual((s["turns"], s["in"], s["broken"]), (1, 1, 1))

    def test_large_transcript_is_read_in_bounded_time(self):
        p = self.path("large.jsonl")
        with open(p, "wb") as f:
            for i in range(6000):
                f.write((line("assistant", "2026-10-21T10:00:%02d.000Z" % (i % 60), answer("big-%d" % i, [1, 1, 1, 1], "tool-%d" % i),
                              pad="x" * 400) + "\n").encode("utf-8"))
        self.assertGreater(os.path.getsize(p), 2 * 1024 * 1024)
        started = time.time()
        s = sh.summarize(p, 0)
        self.assertEqual((s["turns"], s["tools"], s["in"]), (6000, 6000, 6000))
        self.assertLess(time.time() - started, 20)


class ProjectName(TempCase):
    def test_nearest_git_folder_or_file_else_last_folder(self):
        repo = self.path("repo-a")
        os.makedirs(os.path.join(repo, ".git"))
        os.makedirs(os.path.join(repo, "src"))
        tree = self.path("tree-b")
        os.makedirs(os.path.join(tree, "sub"))
        write(os.path.join(tree, ".git"), "gitdir: elsewhere")
        self.assertEqual(sh.project_name(os.path.join(repo, "src")), "repo-a")
        self.assertEqual(sh.project_name(os.path.join(tree, "sub")), "tree-b")
        self.assertEqual(sh.project_name(repo + os.sep), "repo-a")
        self.assertEqual(sh.project_name("Q:\\nowhere\\no-git-here"), "no-git-here")
        self.assertEqual(sh.project_name(""), None)
        self.assertEqual(sh.project_name(None), None)


# ----------------------------------------------------------------------------------------------
# 4 harness fingerprint
# ----------------------------------------------------------------------------------------------

SPEC_FILE_HASHES = {
    "CLAUDE.md": "8633657562154c9df489e6620a516ad95081412e73730819376a112647687cb4",
    "output-style": "37a8eec1ce19687d132fe29051dca629d164e2c4958ba141d5f4133a33f0688f",
    "plugin/agents/coder.md": "ce57f2797ecef612cffcf986d40350144d3da63c3fb029cea8c201112159c693",
    "plugin/agents/tester.md": "3fc8998e3411814040cf6e1ea75b2abd9b25f74cb4db9f8e1008a1d1978cf4cb",
    "plugin/output-styles/orchestrator.md": "7aa397df66304bab4fe275afe0507a01844e7fda848b4e194a9402d010721839",
    "plugin/skills/new-project/SKILL.md": "28312e346b76a3f91e8283519baab5f103d79547dedff5fb7ccc0dc3c5119bbe",
    "skills/ponytail/SKILL.md": "852a478ece1b66d04d107ae488dd476a5a43b317f62729e25152e4bfba096cac",
}


class Profile(TempCase):
    """A claude dir, a plugin root (a copy of the fixture) and a project dir under a temp folder."""

    def setUp(self):
        super().setUp()
        self.claude = self.path("claude")
        self.plugin = self.path("plugin")
        self.project = self.path("proj")
        shutil.copytree(PLUGIN_FIXTURE, self.plugin)
        os.makedirs(self.project)
        write(os.path.join(self.claude, "CLAUDE.md"), "- rule\n", "\r\n")
        write(os.path.join(self.claude, "skills", "ponytail", "SKILL.md"), "P\n")

    def fp(self):
        return sh.fingerprint(self.claude, self.plugin, self.project)

    def agent(self, name):
        return os.path.join(self.plugin, "agents", name + ".md")


class Fingerprint(Profile):
    def test_spec_example(self):
        h, files = self.fp()
        self.assertEqual(h, "006494ff")
        self.assertEqual(files, SPEC_FILE_HASHES)

    def test_same_files_same_hash(self):
        self.assertEqual(self.fp(), self.fp())

    def test_editing_one_role_file_changes_only_that_key(self):
        before = self.fp()
        write(self.agent("coder"), "---\nname: coder\nmodel: sonnet\neffort: high\nskills:\n  - ponytail\n---\nA, edited\n")
        after = self.fp()
        self.assertNotEqual(before[0], after[0])
        self.assertEqual(sh.compare(before[1], after[1]), (["plugin/agents/coder.md"], [], []))

    def test_line_ends_and_creation_order_do_not_matter(self):
        base = self.fp()[0]
        tester = slurp(self.agent("tester")).decode("utf-8")
        os.remove(self.agent("tester"))
        write(self.agent("tester"), tester, "\r\n")
        self.assertEqual(self.fp()[0], base)

    def test_a_bom_in_a_file_is_not_hashed(self):
        base = self.fp()[0]
        data = slurp(self.agent("tester"))
        with open(self.agent("tester"), "wb") as f:
            f.write(b"\xef\xbb\xbf" + data)
        self.assertEqual(self.fp()[0], base)

    def test_a_role_file_added_or_removed(self):
        base = self.fp()
        write(self.agent("reviewer"), "---\nname: reviewer\n---\nR\n")
        added = sh.compare(base[1], self.fp()[1])
        os.remove(self.agent("reviewer"))
        os.remove(self.agent("tester"))
        removed = sh.compare(base[1], self.fp()[1])
        self.assertEqual(added, ([], ["plugin/agents/reviewer.md"], []))
        self.assertEqual(removed, ([], [], ["plugin/agents/tester.md"]))

    def test_compare_without_a_before_counts_everything_as_added(self):
        files = self.fp()[1]
        self.assertEqual(sh.compare(None, files), ([], sorted(files, key=sh.okey), []))

    def test_own_output_style_is_hashed_by_file(self):
        write(os.path.join(self.claude, "output-styles", "\u03b2\u03b2.md"), "---\nname: \u03b3\u03b3\n---\nShort\n")
        write(os.path.join(self.claude, "settings.json"), json.dumps({"outputStyle": "\u03b3\u03b3"}, ensure_ascii=False))
        files = self.fp()[1]
        self.assertIn("output-styles/\u03b2\u03b2.md", files)
        self.assertEqual(files["output-style"], sh.file_hash("\u03b3\u03b3".encode("utf-8")))

    def test_built_in_output_style_is_the_name_only(self):
        write(os.path.join(self.claude, "settings.json"), '{"outputStyle": "Learning"}')
        files = self.fp()[1]
        self.assertEqual(files["output-style"], sh.file_hash(b"Learning"))
        self.assertFalse([k for k in files if k.startswith("output-styles/")])

    def test_preloaded_skills_only(self):
        write(self.agent("coder"), "---\nname: coder\nskills:\n  - ponytail\n  - not-installed\n  - ../escape\n---\nA\n")
        write(os.path.join(self.claude, "skills", "unused", "SKILL.md"), "unused\n")
        write(os.path.join(self.claude, "escape", "SKILL.md"), "outside the skills folder\n")
        base = self.fp()
        self.assertEqual([k for k in base[1] if k.startswith("skills/")], ["skills/ponytail/SKILL.md"])
        write(os.path.join(self.claude, "skills", "unused", "SKILL.md"), "unused, edited\n")
        self.assertEqual(self.fp()[0], base[0])
        write(os.path.join(self.claude, "skills", "ponytail", "SKILL.md"), "P, edited\n")
        after = self.fp()
        self.assertEqual(sh.compare(base[1], after[1]), (["skills/ponytail/SKILL.md"], [], []))

    def test_removing_the_role_drops_its_skills(self):
        self.assertIn("skills/ponytail/SKILL.md", self.fp()[1])
        os.remove(self.agent("coder"))
        self.assertFalse([k for k in self.fp()[1] if k.startswith("skills/")])

    def test_crlf_skills_list_is_read(self):
        write(self.agent("coder"), "---\nname: coder\nskills:\n  - ponytail\n---\nA\n", "\r\n")
        self.assertIn("skills/ponytail/SKILL.md", self.fp()[1])


# ----------------------------------------------------------------------------------------------
# 3 record: the child process flows
# ----------------------------------------------------------------------------------------------

class Flow(Profile):
    def setUp(self):
        super().setUp()
        self.repo = self.path("work", "repo-a")
        os.makedirs(os.path.join(self.repo, ".git"))
        self.cwd = os.path.join(self.repo, "src")
        os.makedirs(self.cwd)
        self.lessons = os.path.join(self.claude, "lessons")
        self.home = self.path("home")
        os.makedirs(self.home)
        self.agent_file = self.path("transcripts", "agent.jsonl")
        write(self.agent_file, joined(AGENT_LINES))
        self.main_file = self.path("transcripts", "main.jsonl")

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if k not in ("SPANHARNESS_RECORD", "CLAUDE_CONFIG_DIR", "CLAUDE_PROJECT_DIR")}
        env["HOME"] = env["USERPROFILE"] = self.home
        env.update(extra)
        return env

    def command(self, now=NOW, extra=()):
        return [sys.executable, "-I", SCRIPT, "record", "--claude-dir", self.claude, "--plugin-root", self.plugin,
                "--now", now] + list(extra)

    def launch(self, stdin, now=NOW, env=None):
        p = subprocess.Popen(self.command(now), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             env=env or self.env())
        p.stdin.write(stdin if isinstance(stdin, bytes) else stdin.encode("utf-8"))
        p.stdin.close()
        return p

    @staticmethod
    def finish(p):
        out = p.stdout.read()
        err = p.stderr.read()
        p.stdout.close()
        p.stderr.close()
        return p.wait(60), out, err

    def run_hook(self, stdin, now=NOW, env=None):
        code, out, err = self.finish(self.launch(stdin, now, env))
        self.assertEqual(out, b"")
        return code

    def hook(self, event, agent_type=None, agent_id=None, session="sess1", transcript=None, agent_transcript=None, effort=True):
        d = {"hook_event_name": event, "session_id": session, "cwd": self.cwd,
             "transcript_path": transcript or self.main_file, "last_assistant_message": SECRET}
        if effort:
            d["effort"] = {"level": "high"}
        if agent_type is not None:
            d["agent_type"] = agent_type
        if agent_id is not None:
            d["agent_id"] = agent_id
            d["agent_transcript_path"] = agent_transcript or self.agent_file
        return json.dumps(d, ensure_ascii=False)

    def rows(self):
        return read_lines(os.path.join(self.lessons, MONTH_FILE))

    def of(self, kind, session):
        return [r for r in self.rows() if r.get("kind") == kind and r.get("session") == session]

    def state(self, name):
        return os.path.join(self.lessons, "state", name + ".json")

    def saved(self, name):
        with open(self.state(name), "rb") as f:
            return json.loads(f.read().decode("utf-8"))["offset"]

    def write_main(self):
        write(self.main_file, joined([
            line("user", "2026-10-21T11:00:00.000Z"),
            line("assistant", "2026-10-21T11:00:02.000Z", answer("a1", [1, 2, 3, 4], "x1")),
            line("assistant", "2026-10-21T11:00:09.000Z", answer("a2", [5, 6, 7, 8])),
            line("assistant", "2026-10-21T11:00:12.000Z", answer("a3", [1, 1, 1, 1]))]))


class RecordFlow(Flow):
    def test_agent_record(self):
        self.assertEqual(self.run_hook(self.hook("SubagentStop", "spanharness:coder", "ag1")), 0)
        rows = self.rows()
        self.assertEqual([r["kind"] for r in rows], ["harness", "agent"])
        first, run = rows
        self.assertEqual((first["harness"], first["prev"], first["changed"], first["removed"]), ("006494ff", None, [], []))
        self.assertEqual(len(first["added"]), 7)
        self.assertEqual((run["agent"], run["agent_id"], run["project"], run["cwd"], run["session"]),
                         ("spanharness:coder", "ag1", "repo-a", self.cwd, "sess1"))
        self.assertEqual((run["model"], run["role_model"], run["effort"], run["role_effort"]), (MODEL, "sonnet", "high", "high"))
        self.assertEqual((run["in"], run["out"], run["cache_read"], run["cache_write"], run["tools"], run["turns"], run["ms"]),
                         (17, 8, 150, 20, 2, 2, 90500))
        self.assertEqual((run["missing"], run["harness"], run["t"]), ([], "006494ff", NOW))
        with open(self.state("harness"), "rb") as f:
            saved = json.loads(f.read().decode("utf-8"))
        self.assertEqual((saved["harness"], saved["files"]), ("006494ff", SPEC_FILE_HASHES))

    def test_events_that_make_no_line(self):
        self.run_hook(self.hook("SubagentStop", "spanharness:coder", "ag1"))
        for payload in (self.hook("SubagentStop", "", "ag9"), self.hook("Stop", None, "ag8"), self.hook("SessionEnd")):
            self.assertEqual(self.run_hook(payload), 0)
        self.assertEqual(len(self.rows()), 2)

    def test_turn_records_count_only_what_was_added(self):
        self.write_main()
        self.assertEqual(self.run_hook(self.hook("Stop")), 0)
        turn = self.rows()[-1]
        self.assertEqual((turn["kind"], turn["turns"], turn["in"]), ("turn", 3, 7))
        self.assertNotIn("agent", turn)
        self.assertNotIn("role_model", turn)
        self.assertTrue(os.path.exists(self.state("turn-sess1")))
        with open(self.main_file, "ab") as f:
            f.write(joined([line("assistant", "2026-10-21T11:05:00.000Z", answer("a4", [2, 2, 2, 2])),
                            line("assistant", "2026-10-21T11:05:09.000Z", answer("a5", [3, 3, 3, 3], "x2"))]).encode("utf-8"))
        self.run_hook(self.hook("Stop"))
        turn = self.rows()[-1]
        self.assertEqual((turn["turns"], turn["in"], turn["tools"], turn["ms"]), (2, 5, 1, 9000))

    def test_resume_without_a_saved_offset_starts_at_the_last_prompt(self):
        p = self.path("transcripts", "resume.jsonl")
        write(p, joined(Summary.EARLIER + Summary.LATEST))
        self.assertEqual(self.run_hook(self.hook("Stop", session="sess-resume", transcript=p, effort=False)), 0)
        turns = self.of("turn", "sess-resume")
        self.assertEqual(len(turns), 1)
        self.assertEqual((turns[0]["turns"], turns[0]["tools"], turns[0]["in"], turns[0]["ms"]), (2, 2, 11, 12000))
        self.assertEqual(self.saved("turn-sess-resume"), os.path.getsize(p))
        # a later Stop counts only the new part (the system line's time is not part of the turn)
        with open(p, "ab") as f:
            f.write(joined([line("user", "2026-10-21T11:20:00.000Z", said(BODY), **HUMAN),
                            line("assistant", "2026-10-21T11:20:03.000Z", answer("r5", [5, 5, 5, 5])),
                            system("2026-10-21T11:20:04.000Z", "turn_duration")]).encode("utf-8"))
        self.run_hook(self.hook("Stop", session="sess-resume", transcript=p, effort=False))
        turns = self.of("turn", "sess-resume")
        self.assertEqual((len(turns), turns[1]["turns"], turns[1]["in"], turns[1]["ms"]), (2, 1, 5, 3000))
        # nothing new: no empty line
        count = len(self.rows())
        self.run_hook(self.hook("Stop", session="sess-resume", transcript=p, effort=False))
        self.assertEqual(len(self.rows()), count)

    def test_first_stop_of_a_new_session_counts_the_whole_first_turn(self):
        p = self.path("transcripts", "fresh.jsonl")
        write(p, joined([line("queue-operation", "2026-10-21T14:00:00.000Z", operation="enqueue"),
                         line("user", "2026-10-21T14:00:01.000Z", said(BODY), **HUMAN),
                         line("assistant", "2026-10-21T14:00:05.000Z", answer("f1", [3, 1, 4, 1], "ft1")),
                         line("user", "2026-10-21T14:00:06.000Z", tool_back("ft1")),
                         line("assistant", "2026-10-21T14:00:09.000Z", answer("f2", [5, 9, 2, 6]))]))
        self.run_hook(self.hook("Stop", session="sess-fresh", transcript=p, effort=False))
        turns = self.of("turn", "sess-fresh")
        self.assertEqual((len(turns), turns[0]["turns"], turns[0]["in"], turns[0]["ms"]), (1, 2, 8, 8000))

    def test_harness_change_writes_a_harness_line_first(self):
        self.run_hook(self.hook("SubagentStop", "spanharness:coder", "ag1"))
        before = self.rows()[1]["harness"]
        write(self.agent("coder"), "---\nname: coder\nmodel: opus\neffort: high\nskills:\n  - ponytail\n---\nA, edited\n")
        self.run_hook(self.hook("SubagentStop", "spanharness:coder", "ag2"))
        rows = self.rows()
        self.assertEqual([r["kind"] for r in rows], ["harness", "agent", "harness", "agent"])
        change = rows[2]
        self.assertEqual((change["prev"], change["changed"], change["added"], change["removed"]),
                         (before, ["plugin/agents/coder.md"], [], []))
        self.assertEqual(change["harness"], self.fp()[0])
        self.assertEqual(rows[3]["role_model"], "opus")

    def test_two_processes_at_once_lose_nothing(self):
        self.run_hook(self.hook("SubagentStop", "spanharness:coder", "ag1"))
        write(self.agent("coder"), "---\nname: coder\nmodel: opus\n---\nA, edited\n")
        procs = [self.launch(self.hook("SubagentStop", "spanharness:coder", "ag2")),
                 self.launch(self.hook("SubagentStop", "spanharness:coder", "ag3"))]
        self.assertEqual([self.finish(p)[0] for p in procs], [0, 0])
        racing = self.rows()[2:]
        self.assertEqual(sorted(r["agent_id"] for r in racing if r["kind"] == "agent"), ["ag2", "ag3"])
        self.assertEqual(len([r for r in racing if r["kind"] == "harness"]), 1)

    def test_two_stops_of_one_session_count_a_stretch_once(self):
        p = self.path("transcripts", "race.jsonl")
        write(p, joined([line("user", "2026-10-21T15:00:00.000Z", said(BODY), **HUMAN)] +
                        [line("assistant", "2026-10-21T15:00:0%d.000Z" % (2 * i), answer("c%d" % i, [i] * 4)) for i in (1, 2, 3)]))

        def twin():
            procs = [self.launch(self.hook("Stop", session="sess-race", transcript=p)) for _ in range(2)]
            return [self.finish(x)[0] for x in procs]
        self.assertEqual(twin(), [0, 0])
        turns = self.of("turn", "sess-race")
        self.assertEqual((len(turns), turns[0]["turns"], turns[0]["in"]), (1, 3, 6))
        self.assertEqual(self.saved("turn-sess-race"), os.path.getsize(p))
        with open(p, "ab") as f:
            f.write(joined([line("assistant", "2026-10-21T15:00:08.000Z", answer("c4", [4] * 4)),
                            line("assistant", "2026-10-21T15:00:10.000Z", answer("c5", [5] * 4))]).encode("utf-8"))
        self.assertEqual(twin(), [0, 0])
        turns = self.of("turn", "sess-race")
        self.assertEqual((len(turns), turns[1]["turns"], sum(t["in"] for t in turns)), (2, 2, 15))
        self.assertEqual(self.saved("turn-sess-race"), os.path.getsize(p))

    def test_same_agent_id_called_again_counts_the_addition_only(self):
        p = self.path("transcripts", "agent-resumed.jsonl")
        write(p, joined([line("user", "2026-10-21T16:00:00.000Z", said(BODY)),
                         line("assistant", "2026-10-21T16:00:05.000Z", answer("g1", [10, 1, 100, 5], "gt1")),
                         line("assistant", "2026-10-21T16:00:20.000Z", answer("g2", [20, 2, 200, 0]))]))

        def call(agent_id):
            return self.run_hook(self.hook("SubagentStop", "spanharness:coder", agent_id, "sess-ag", agent_transcript=p, effort=False))
        self.assertEqual(call("agR"), 0)
        with open(p, "ab") as f:
            f.write(joined([line("user", "2026-10-21T16:20:00.000Z", said(BODY)),
                            line("assistant", "2026-10-21T16:20:08.000Z", answer("g3", [7] * 4, "gt2", "gt3")),
                            line("assistant", "2026-10-21T16:20:30.000Z", answer("g4", [8] * 4))]).encode("utf-8"))
        self.assertEqual(call("agR"), 0)
        rows = self.of("agent", "sess-ag")
        self.assertEqual(len(rows), 2)
        self.assertEqual((rows[0]["turns"], rows[0]["in"], rows[0]["ms"]), (2, 30, 20000))
        self.assertEqual((rows[1]["turns"], rows[1]["tools"], rows[1]["in"], rows[1]["out"], rows[1]["cache_read"], rows[1]["cache_write"], rows[1]["ms"]),
                         (2, 2, 15, 15, 15, 15, 30000))
        self.assertEqual(self.saved("agent-agR"), os.path.getsize(p))
        count = len(self.rows())
        self.assertEqual(call("agR"), 0)
        self.assertEqual(len(self.rows()), count)
        self.assertEqual(call("agS"), 0)
        rows = self.of("agent", "sess-ag")
        self.assertEqual((len(rows), rows[2]["agent_id"], rows[2]["turns"]), (3, "agS", 4))
        self.assertTrue(os.path.exists(self.state("agent-agS")))
        self.assertIsNone(rows[0]["effort"])
        self.assertIn("effort", rows[0])
        self.assertEqual((rows[0]["role_effort"], rows[0]["missing"]), ("high", []))

    def test_saved_offset_beyond_the_file_starts_over(self):
        p = self.path("transcripts", "restarted.jsonl")
        write(p, joined([line("user", "2026-10-21T17:00:00.000Z", said(BODY), **HUMAN),
                         line("assistant", "2026-10-21T17:00:02.000Z", answer("k1", [1] * 4)),
                         line("assistant", "2026-10-21T17:00:04.000Z", answer("k2", [2] * 4))]))
        write(self.state("turn-sess-restarted"), json.dumps({"path": p, "offset": 1000000}))
        self.run_hook(self.hook("Stop", session="sess-restarted", transcript=p, effort=False))
        turns = self.of("turn", "sess-restarted")
        self.assertEqual((len(turns), turns[0]["turns"]), (1, 2))
        self.assertEqual(self.saved("turn-sess-restarted"), os.path.getsize(p))

    def test_old_state_files_go_after_30_days(self):
        now = 1792544520       # NOW as epoch seconds (2026-10-21T01:02:00Z)
        day = 86400
        names = {"turn-old": 40, "agent-old": 40, "agent-recent": 29, "other-old": 40}
        for name, age in names.items():
            write(self.state(name), "{}")
            os.utime(self.state(name), (now - age * day, now - age * day))
        self.run_hook(self.hook("Stop", session="sess-gone", transcript=self.path("transcripts", "gone.jsonl"), effort=False))
        self.assertFalse(os.path.exists(self.state("turn-old")))
        self.assertFalse(os.path.exists(self.state("agent-old")))
        self.assertTrue(os.path.exists(self.state("agent-recent")))
        self.assertTrue(os.path.exists(self.state("other-old")))      # only turn-* and agent-* are cleaned

    def test_unreadable_transcript_lists_the_missing_keys_but_not_effort(self):
        self.run_hook(self.hook("Stop", session="sess-gone", transcript=self.path("transcripts", "gone.jsonl"), effort=False))
        turns = self.of("turn", "sess-gone")
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["missing"], ["model", "in", "out", "cache_read", "cache_write", "tools", "turns", "ms"])
        self.assertIsNone(turns[0]["effort"])

    def test_bad_input_exits_0_and_is_logged(self):
        self.assertEqual(self.run_hook("this is not hook input"), 0)
        self.assertEqual(self.run_hook(""), 0)
        self.assertEqual(self.run_hook("[1, 2]"), 0)
        self.assertEqual(self.rows(), [])
        log = slurp(os.path.join(self.lessons, "errors.log")).decode("utf-8").split("\n")
        self.assertEqual(len([l for l in log if l]), 3)
        self.assertNotIn("this is not hook input", "\n".join(log))

    def test_opt_out_writes_nothing(self):
        self.assertEqual(self.run_hook(self.hook("SubagentStop", "spanharness:coder", "ag1"), env=self.env(SPANHARNESS_RECORD="0")), 0)
        self.assertFalse(os.path.exists(self.lessons))
        self.assertEqual(self.run_hook(self.hook("SubagentStop", "spanharness:coder", "ag1"), env=self.env(SPANHARNESS_RECORD="1")), 0)
        self.assertEqual(len(self.rows()), 2)

    def test_no_conversation_text_is_stored(self):
        self.write_main()
        self.run_hook(self.hook("SubagentStop", "spanharness:coder", "ag1"))
        self.run_hook(self.hook("Stop"))
        self.run_hook("garbage " + SECRET)
        found = 0
        for folder, _, names in os.walk(self.lessons):
            for name in names:
                found += 1
                data = slurp(os.path.join(folder, name)).decode("utf-8", "replace")
                self.assertNotIn(SECRET, data)
                self.assertNotIn(BODY, data)
        self.assertGreater(found, 3)
        self.assertIn(BODY, slurp(self.agent_file).decode("utf-8"))

    def test_the_run_is_fast(self):
        self.write_main()
        times = []
        for _ in range(5):
            started = time.time()
            self.run_hook(self.hook("Stop"))
            times.append(time.time() - started)
        times.sort()
        self.assertLess(times[len(times) // 2], 3.0, times)

    @unittest.skipIf(os.name == "nt", "needs a pseudo terminal")
    def test_terminal_stdin_prints_usage_and_does_nothing(self):
        import pty
        master, slave = pty.openpty()
        try:
            p = subprocess.run(self.command(), stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env(), timeout=30)
        finally:
            os.close(master)
            os.close(slave)
        self.assertEqual(p.returncode, 0)
        self.assertIn(b"usage", p.stderr)
        self.assertFalse(os.path.exists(self.lessons))


# ----------------------------------------------------------------------------------------------
# 3.6 errors.log, the lock and the wait for a complete last line
# ----------------------------------------------------------------------------------------------

class Support(TempCase):
    def test_errors_log_is_started_over_only_past_the_limit(self):
        now = sh.parse_now("2026-10-21T10:02:00+09:00")
        lessons = self.path("lessons")
        log = os.path.join(lessons, "errors.log")
        os.makedirs(lessons)
        for size, kept in ((sh.ERRORS_MAX, True), (sh.ERRORS_MAX + 1, False)):
            with open(log, "wb") as f:
                f.write(b"x" * size)
            sh.log_error(lessons, now, "record failed", "OSError: disk\nfull")
            data = slurp(log)
            self.assertEqual(len(data) > sh.ERRORS_MAX, kept, size)
            self.assertTrue(data.endswith(b"\n"))
            tail = data[-120:].decode("utf-8").splitlines()[-1]
            self.assertIn("record failed", tail)
            self.assertNotIn("\r", tail)
            if not kept:
                self.assertEqual(data.count(b"\n"), 1)

    def test_lock_is_exclusive_and_gives_up(self):
        path = self.path("state", "lock")
        fd = sh.acquire_lock(path)
        self.assertIsNotNone(fd)
        old = sh.LOCK_TIMEOUT
        sh.LOCK_TIMEOUT = 0.2
        try:
            started = time.time()
            self.assertIsNone(sh.acquire_lock(path))
            self.assertLess(time.time() - started, 5)
        finally:
            sh.LOCK_TIMEOUT = old
        os.close(fd)
        fd2 = sh.acquire_lock(path)
        self.assertIsNotNone(fd2)
        os.close(fd2)
        self.assertEqual(os.path.getsize(path), 0)

    def test_wait_for_a_complete_last_line(self):
        p = self.path("t.jsonl")
        for content, polls in ((b"", 0), (b"{}\n", 0), (b"{}", 20)):
            with open(p, "wb") as f:
                f.write(content)
            clock = [0.0]
            slept = []

            def sleep(s):
                slept.append(s)
                clock[0] += s
            sh.wait_last_line(p, lambda: clock[0], sleep)
            self.assertEqual(len(slept), polls, content)
            self.assertTrue(all(abs(s - 0.05) < 1e-9 for s in slept))
        slept = []
        sh.wait_last_line(self.path("missing.jsonl"), lambda: 0.0, slept.append)
        self.assertEqual(slept, [])

    def test_wait_ends_as_soon_as_the_line_is_finished(self):
        p = self.path("t.jsonl")
        with open(p, "wb") as f:
            f.write(b"{}")
        clock = [0.0]
        slept = []

        def sleep(s):
            slept.append(s)
            clock[0] += s
            if len(slept) == 3:
                with open(p, "ab") as f:
                    f.write(b"\n")
        sh.wait_last_line(p, lambda: clock[0], sleep)
        self.assertEqual(len(slept), 3)

    def test_atomic_write_and_saved_offset(self):
        p = self.path("state", "turn-x.json")
        sh.write_atomic(p, {"path": "/t/a.jsonl", "offset": 5})
        self.assertFalse(os.path.exists(p + ".tmp"))
        self.assertEqual(sh.saved_offset(p, "/T/A.JSONL"), 5)       # compared ignoring case
        self.assertIsNone(sh.saved_offset(p, "/t/b.jsonl"))
        self.assertIsNone(sh.saved_offset(p, None))
        self.assertIsNone(sh.saved_offset(self.path("state", "none.json"), "/t/a.jsonl"))

    def test_atomic_write_tries_four_times(self):
        tries, sleeps = [], []
        real_replace, real_sleep = sh.os.replace, sh.time.sleep

        def refuse(a, b):
            tries.append(a)
            raise PermissionError("busy")
        sh.os.replace, sh.time.sleep = refuse, sleeps.append
        try:
            with self.assertRaises(OSError):
                sh.write_atomic(self.path("state", "turn-y.json"), {"path": "x", "offset": 1})
        finally:
            sh.os.replace, sh.time.sleep = real_replace, real_sleep
        self.assertEqual((len(tries), sleeps), (4, [0.15, 0.15, 0.15]))

    def test_a_lone_surrogate_is_written_as_u_fffd(self):
        self.assertEqual(sh.enc("a\ud83db\ud83d\ud83dc\U0001F600"), "a\ufffdb\ufffd\ufffdc\U0001F600".encode("utf-8"))
        self.assertEqual(sh.text({"k": "\ud83d"}, "k"), "\ud83d")        # and it is a usable string


if __name__ == "__main__":
    unittest.main()
