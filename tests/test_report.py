"""Unit tests for `report`: number formats, the tables, the cost, the events join and the command line.

The numbers and the formats are tested in-process (the module is loaded from scripts/spanharness.py); whole
reports are built by running the script as a child process on a temporary claude dir. The cases in
tests/fixtures/cases are the shared contract for both implementations; these tests are for the Python one.
"""
import contextlib
import glob
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "spanharness.py")
SPEC = os.path.join(ROOT, "docs", "lessons-format.md")
PLUGIN_FIXTURE = os.path.join(HERE, "fixtures", "plugin")
CASES = os.path.join(HERE, "fixtures", "cases")

sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location("spanharness_under_test", SCRIPT)
sh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sh)
sh._imports()

NOW = "2026-10-21T14:00:00+09:00"
M1, M2 = "claude-sonnet-4-5-20250929", "claude-opus-4-1-20250805"
HUGE_QUARTER, HUGE_HALF = 3000000000000000000, 5000000000000000000     # 4 x quarter and 2 x half are past 2**63 - 1
EN = "\u2013"


def slurp(path):
    with open(path, "rb") as f:
        return f.read()


def rec(kind, t, project, agent, model, effort, inn, out, cache_read, cache_write, tools, turns, ms, *missing, harness="a1b2c3d4"):
    """A record line the way `record` writes it."""
    d = {"t": t, "kind": kind, "project": project, "cwd": "C:\\work\\" + project, "session": "s1"}
    if agent is not None:
        d["agent"] = agent
        d["agent_id"] = "id" + t
    d.update({"model": model, "effort": effort, "in": inn, "out": out, "cache_read": cache_read, "cache_write": cache_write,
              "tools": tools, "turns": turns, "ms": ms, "harness": harness, "missing": list(missing)})
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


def line_of(text, prefix):
    for l in text.split("\n"):
        if l.startswith(prefix):
            return l
    return None


def row_of(text, project, role):
    """The cells of one project x role row."""
    l = line_of(text, "| %s | %s | " % (project, role))
    return None if l is None else l[2:-2].split(" | ")


class ReportCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="spanharness-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.claude = os.path.join(self.tmp, "claude")
        self.plugin = os.path.join(self.tmp, "plugin")
        self.proj = os.path.join(self.tmp, "proj")
        shutil.copytree(PLUGIN_FIXTURE, self.plugin)
        os.makedirs(self.proj)
        self.lessons = os.path.join(self.claude, "lessons")
        self.put("claude/CLAUDE.md", "- rule\n")

    def put(self, rel, text):
        p = os.path.join(self.tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(text.encode("utf-8") if isinstance(text, str) else text)
        return p

    def runs(self, month, lines):
        self.put("claude/lessons/runs/%s.jsonl" % month, "\n".join(lines) + "\n")

    def events(self, lines):
        self.put("claude/lessons/events.md", "\n".join(lines) + "\n")

    def command(self, *args, now=NOW):
        return [sys.executable, "-I", SCRIPT, "report", "--claude-dir", self.claude, "--plugin-root", self.plugin,
                "--project-dir", self.proj, "--now", now] + list(args)

    def run_report(self, *args, now=NOW, cwd=None):
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CONFIG_DIR", "CLAUDE_PROJECT_DIR", "SPANHARNESS_RECORD")}
        env["HOME"] = env["USERPROFILE"] = self.tmp
        return subprocess.run(self.command(*args, now=now), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=env, cwd=cwd or self.tmp, timeout=120)

    def report(self, months=2, now=NOW):
        p = self.run_report("--months", str(months), now=now)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        return slurp(os.path.join(self.lessons, "report.md")).decode("utf-8")


# ----------------------------------------------------------------------------------------------
# number formats (5.4)
# ----------------------------------------------------------------------------------------------

class Numbers(unittest.TestCase):
    def test_fmt1_rounds_half_away_from_zero_on_exact_values(self):
        F = sh.Fraction
        cases = [(F(9, 2), "4.5"), (2500, "2500"), (0, "0"), (F(1, 20), "0.1"), (F(-1, 20), "-0.1"), (F(-1, 40), "0"),
                 (F(1, 40), "0"), (F(3, 2), "1.5"), (F(7, 4), "1.8"), (F(13, 4), "3.3"), (F(-7, 4), "-1.8"), (F(10), "10"),
                 (F(1, 3), "0.3"), (F(2, 3), "0.7"), (F(999, 1000), "1"), (F(-1, 3), "-0.3")]
        for value, want in cases:
            self.assertEqual(sh.fmt1(value), want, value)

    def test_fmt2_and_money_ties(self):
        F = sh.Fraction
        for value, want in [(F(15, 100), "0.15"), (F(285, 1000), "0.29"), (F(5, 2), "2.5"), (F(125, 1000), "0.13"), (F(1, 5), "0.2"),
                            (1, "1"), (F(57, 100), "0.57"), (F(1, 200), "0.01"), (F(1, 400), "0"), (F(-285, 1000), "-0.29")]:
            self.assertEqual(sh.fmt2(value), want, value)
        for value, want in [(F(15, 100), "$0.15"), (F(285, 1000), "$0.29"), (F(5, 2), "$2.50"), (F(125, 1000), "$0.13"), (F(27), "$27.00"),
                            (F(1, 200), "<$0.01"), (F(999, 100000), "<$0.01"), (F(1, 100), "$0.01"), (F(1, 1000), "<$0.01"), (0, "$0.00"),
                            (F(1, 100) - F(1, 10 ** 9), "<$0.01"), (None, "-")]:
            self.assertEqual(sh.money(value), want, value)

    def test_quantile_median_spread_stat_span(self):
        F = sh.Fraction
        self.assertEqual(sh.quantile([1, 2, 3, 4], F(1, 4)), F(7, 4))
        self.assertEqual(sh.quantile([1, 2, 3, 4], F(3, 4)), F(13, 4))
        self.assertEqual(sh.median([4, 1, 3, 2]), F(5, 2))
        self.assertEqual(sh.median([5]), 5)
        self.assertEqual(sh.quantile([10, 20], F(1, 4)), F(25, 2))
        self.assertEqual(sh.spread([500]), ("min" + EN + "max", 500, 500))
        self.assertEqual(sh.spread([1, 2, 3])[0], "min" + EN + "max")
        self.assertEqual(sh.spread([1, 2, 3, 4])[0], "p25" + EN + "p75")
        self.assertEqual(sh.stat([]), ["0", "-", "-"])
        self.assertEqual(sh.stat([3010, 1000, 2000, 5000, 2500]), ["5", "2500", "p25" + EN + "p75 2000" + EN + "3010"])
        self.assertEqual(sh.stat([500]), ["1", "500", "min" + EN + "max 500" + EN + "500"])
        self.assertEqual(sh.span(None, None), "-")
        self.assertEqual(sh.span("2026-10-01", "2026-10-01"), "2026-10-01")
        self.assertEqual(sh.span("2026-10-01", "2026-10-05"), "2026-10-01 " + EN + " 2026-10-05")

    def test_values_beyond_binary_floating_point(self):
        big = 5000000000000000001
        self.assertEqual(sh.fmt1(big), "5000000000000000001")
        self.assertEqual(sh.stat([big, big + 2])[1], "5000000000000000002")
        self.assertEqual(sh.money(sh.Fraction(3 * 10 ** 18 * 735, 1000 * 10 ** 6)), "$2205000000000.00")

    def test_cell_escaping(self):
        self.assertEqual(sh.esc("a|b\r\nc\nd\re"), "a\\|b  c d e")


# ----------------------------------------------------------------------------------------------
# the tables (5.5)
# ----------------------------------------------------------------------------------------------

class Basics(ReportCase):
    def setUp(self):
        super().setUp()
        self.runs("2026-08", [rec("agent", "2026-08-30T10:00:00+09:00", "old", "coder", M1, "high", 9, 9, 9, 9, 9, 9, 9)])
        self.runs("2026-09", [
            rec("agent", "2026-09-03T10:00:00+09:00", "alpha", "coder", M1, "high", 100, 10, 1000, 50, 4, 3, 1000),
            rec("agent", "2026-09-04T10:00:00+09:00", "alpha", "coder", M1, "high", 300, 30, 3000, 150, 8, 5, 3000),
            '{"t":"2026-09-05T10:00:00+09:00","kind":"agent","proj',
            rec("agent", "2026-09-06T10:00:00+09:00", "beta", "reviewer", None, None, None, 7, 700, 70, 2, 1, 500, "model", "in"),
            ""])
        self.runs("2026-10", [
            rec("agent", "2026-10-02T10:00:00+09:00", "alpha", "coder", M2, "high", 200, 20, 2000, 100, 6, 4, 2000),
            json.dumps({"t": "2026-10-03T09:12:00+09:00", "kind": "harness", "harness": "e5f6a7b8", "prev": "a1b2c3d4",
                        "changed": ["agents/coder.md"], "added": ["output-styles/x.md"], "removed": []}),
            rec("agent", "2026-10-04T10:00:00+09:00", "alpha", "coder", M1, "high", 400, 40, 4000, 200, 10, 6, 4000),
            rec("turn", "2026-10-05T10:00:00+09:00", "alpha", None, M2, "medium", 50, 5, 500, 25, 1, 1, 250),
            rec("turn", "2026-10-06T10:00:00+09:00", "beta", None, M1, None, 60, 6, 600, 30, 0, 1, None, "ms"),
            '{"t":"2026-10-07T10:00:00+09:00","kind":"mystery"}',
            rec("agent", "2026-10-08T10:00:00+09:00", "we|rd", "doc-writer", M1, None, 10, 1, 100, 10, 0, 1, 100)])
        self.text = self.report(2)

    def test_one_row_per_project_and_role(self):
        t = self.text
        self.assertIsNotNone(row_of(t, "alpha", "coder"))
        self.assertIsNotNone(row_of(t, "alpha", "main conversation"))
        self.assertIsNotNone(row_of(t, "beta", "reviewer"))
        self.assertIsNotNone(row_of(t, "beta", "main conversation"))
        self.assertIsNotNone(row_of(t, "we\\|rd", "doc-writer"))

    def test_counts_models_and_efforts(self):
        c = row_of(self.text, "alpha", "coder")
        self.assertEqual((len(c), c[2], c[3], c[4], c[12]), (13, "4", M2 + ", " + M1, "high", "0"))

    def test_median_and_total(self):
        c = row_of(self.text, "alpha", "coder")
        self.assertEqual(c[5:9], ["250 / 1000", "25 / 100", "2500 / 10000", "125 / 500"])
        self.assertEqual(c[9:12], ["7", "4.5", "2500"])

    def test_turn_lines_are_the_main_conversation(self):
        m = row_of(self.text, "alpha", "main conversation")
        self.assertEqual((m[2], m[3], m[4], m[5], m[11]), ("1", M2, "medium", "50 / 50", "250"))

    def test_unread_values_are_left_out(self):
        r = row_of(self.text, "beta", "reviewer")
        self.assertEqual((r[3], r[4], r[5], r[6], r[12]), ("-", "-", "-", "7 / 7", "1"))

    def test_row_order(self):
        keys = ["| alpha | main conversation |", "| alpha | coder |", "| beta | main conversation |", "| beta | reviewer |", "| we\\|rd | doc-writer |"]
        at = [self.text.index(k) for k in keys]
        self.assertEqual(at, sorted(at))

    def test_period_and_files(self):
        t = self.text
        self.assertIn("- Period: 2026-09 ~ 2026-10 (last 2 month(s)", t)
        self.assertIn("- Files read: runs/2026-09.jsonl, runs/2026-10.jsonl\n", t)
        self.assertNotIn("2026-08", t)
        self.assertIsNone(row_of(t, "old", "coder"))

    def test_line_counts(self):
        self.assertIn("- Lines: role runs 6 \u00b7 main-conversation turns 2 \u00b7 harness changes 1 \u00b7 skipped lines 2 ", self.text)

    def test_unread_keys(self):
        self.assertIn("- Lines with unread keys: 2 / 8 ", self.text)
        self.assertIn("- Unread keys: in 1 \u00b7 model 1 \u00b7 ms 1\n", self.text)

    def test_harness_change_line_and_record_times(self):
        self.assertIn("- 2026-10-03T09:12:00+09:00 | a1b2c3d4 \u2192 e5f6a7b8 | changed agents/coder.md | added output-styles/x.md\n", self.text)
        self.assertIn("- Record times: 2026-09-03T10:00:00+09:00 ~ 2026-10-08T10:00:00+09:00\n", self.text)

    def test_the_same_files_give_the_same_text(self):
        self.assertEqual(self.report(2, now="2026-10-30T01:00:00+09:00"), self.text)
        self.assertEqual(self.report(2), self.text)

    def test_months_one_and_three(self):
        one = self.report(1)
        c = row_of(one, "alpha", "coder")
        self.assertIn("- Period: 2026-10 ~ 2026-10", one)
        self.assertNotIn("runs/2026-09.jsonl", one)
        self.assertIsNone(row_of(one, "beta", "reviewer"))
        self.assertEqual((c[2], c[5]), ("2", "300 / 600"))
        self.assertIn("- Lines with unread keys: 1 / 5 ", one)
        self.assertIn("- Unread keys: ms 1\n", one)
        three = self.report(3)
        self.assertIn("runs/2026-08.jsonl", three)
        self.assertIsNotNone(row_of(three, "old", "coder"))
        self.assertEqual(row_of(three, "alpha", "coder")[2], "4")

    def test_a_year_boundary_and_no_files(self):
        t = self.report(2, now="2027-01-05T10:00:00+09:00")
        self.assertIn("- Period: 2026-12 ~ 2027-01", t)
        self.assertIn("- Files read: none\n", t)

    def test_role_x_harness_version_table(self):
        t = self.text
        self.assertEqual(line_of(t, "| coder | a1b2c3d4 | "),
                         "| coder | a1b2c3d4 | 4 | 2026-09-03 %s 2026-10-04 | 4 | 2900 | p25%sp75 2030%s3770 | 4 | 2500 | p25%sp75 1750%s3250 |" % ((EN,) * 5))
        self.assertEqual(line_of(t, "| reviewer | a1b2c3d4 | "),
                         "| reviewer | a1b2c3d4 | 1 | 2026-09-06 | 0 | - | - | 1 | 500 | min%smax 500%s500 |" % (EN, EN))
        self.assertTrue(line_of(t, "| main conversation | a1b2c3d4 | ").startswith("| main conversation | a1b2c3d4 | 2 | "))
        self.assertIn("\n### Version comparisons\n\n", t)
        self.assertIn("none: no role has two harness versions in this period.", t)
        self.assertIn("events.md not found: no outcome signals.", t)
        self.assertNotIn("applied by", t)

    def test_model_unknown_row(self):
        self.assertEqual(line_of(self.text, "| reviewer | (model unknown) | "),
                         "| reviewer | (model unknown) | 1 | 2026-09-06 | 0 | - | - | 1 | 500 | min%smax 500%s500 | - | - | - | - | - | - | 0 | - |" % (EN, EN))

    def test_empty_report(self):
        shutil.rmtree(self.lessons)
        t = self.report(2)
        for part in ("role runs 0 \u00b7 main-conversation turns 0 \u00b7 harness changes 0 \u00b7 skipped lines 0",
                     "No role runs or turns recorded.", "- Lines with unread keys: 0 / 0 ", "## Harness changes\n\nnone"):
            self.assertIn(part, t)


class Overflow(ReportCase):
    """A number that does not fit in 64 bits is an unread value of that line, not an error."""

    def test_number_that_is_too_large_or_not_whole_is_null(self):
        for v in (10 ** 20, 1e30, -1e30, float("nan"), float("inf"), 2 ** 63, float(2 ** 63), "7", True, None):
            self.assertIsNone(sh.number(v), repr(v))
        for v, want in ((2 ** 63 - 1, 2 ** 63 - 1), (-2 ** 63, -2 ** 63), (3000000000, 3000000000), (2.0, 2), (0, 0), (7.9, 7), (-7.9, -7)):
            self.assertEqual(sh.number(v), want, repr(v))

    def test_total_is_null_past_64_bits(self):
        self.assertEqual(sh.total([2 ** 62, 2 ** 62 - 1]), 2 ** 63 - 1)
        self.assertIsNone(sh.total([2 ** 62, 2 ** 62]))
        self.assertEqual(sh.total([]), 0)

    def test_huge_value_in_a_line_leaves_the_rest_of_the_line_and_file(self):
        huge = (rec("agent", "2026-10-03T10:00:00+09:00", "alpha", "coder", M1, "high", 1, 20, 2000, 100, 5, 4, 2000)
                .replace('"in":1,', '"in":100000000000000000000,').replace('"cache_read":2000,', '"cache_read":1e30,'))
        self.assertIn('"in":100000000000000000000,', huge)
        self.runs("2026-10", [rec("agent", "2026-10-02T10:00:00+09:00", "alpha", "coder", M1, "high", 100, 10, 1000, 50, 4, 3, 1000), huge,
                              rec("agent", "2026-10-04T10:00:00+09:00", "alpha", "coder", M1, "high", 300, 30, 3000, 150, 8, 5, 3000)])
        t = self.report(1)
        c = row_of(t, "alpha", "coder")
        self.assertEqual(c[2:13], ["3", M1, "high", "200 / 400", "20 / 60", "2000 / 4000", "100 / 300", "5", "4", "2000", "0"])
        self.assertIn("role runs 3 \u00b7 main-conversation turns 0 \u00b7 harness changes 0 \u00b7 skipped lines 0", t)
        self.assertNotIn("could not be opened", t)
        self.assertIn("- Record times: 2026-10-02T10:00:00+09:00 ~ 2026-10-04T10:00:00+09:00", t)

    def test_four_values_that_add_past_the_limit(self):
        self.runs("2026-10", [
            rec("agent", "2026-10-02T10:00:00+09:00", "alpha", "coder", M1, "high", 100, 10, 1000, 50, 4, 3, 1000),
            rec("agent", "2026-10-03T10:00:00+09:00", "alpha", "coder", M1, "high", HUGE_QUARTER, HUGE_QUARTER, HUGE_QUARTER, HUGE_QUARTER, 5, 4, 2000),
            rec("agent", "2026-10-04T10:00:00+09:00", "alpha", "coder", M1, "high", 300, 30, 3000, 150, 8, 5, 3000)])
        t = self.report(1)
        c = row_of(t, "alpha", "coder")
        self.assertEqual(c[2], "3")
        self.assertEqual(c[5:9], ["300 / 3000000000000000400", "30 / 3000000000000000040", "3000 / 3000000000000004000", "150 / 3000000000000000200"])
        self.assertEqual(c[9:13], ["5", "4", "2000", "0"])
        self.assertEqual(line_of(t, "| coder | a1b2c3d4 | "),
                         "| coder | a1b2c3d4 | 3 | 2026-10-02 %s 2026-10-04 | 2 | 2320 | min%smax 1160%s3480 | 3 | 2000 | min%smax 1000%s3000 |" % ((EN,) * 5))

    def test_a_column_total_past_the_limit_shows_a_dash_and_the_exit_code_stays_0(self):
        self.runs("2026-10", [rec("agent", "2026-10-02T10:00:00+09:00", "alpha", "coder", M1, "high", HUGE_HALF, 10, 1000, 50, 4, 3, 1000),
                              rec("agent", "2026-10-03T10:00:00+09:00", "alpha", "coder", M1, "high", HUGE_HALF, 30, 3000, 150, 8, 5, 3000)])
        t = self.report(1)
        c = row_of(t, "alpha", "coder")
        self.assertEqual(c[2:13], ["2", M1, "high", "5000000000000000000 / -", "20 / 40", "2000 / 4000", "100 / 200", "6", "4", "2000", "0"])
        self.assertIn("a total too large for 64 bits is shown as `-`", t)

    def test_model_sums_past_the_limit(self):
        self.runs("2026-10", [
            rec("agent", "2026-10-02T10:00:00+09:00", "alpha", "coder", "claude-sonnet-5-5", "high", HUGE_HALF, 10, 1000, 50, 4, 3, 1000),
            rec("agent", "2026-10-03T10:00:00+09:00", "alpha", "coder", "claude-sonnet-5-5", "high", HUGE_HALF, 30, 3000, 150, 8, 5, 3000),
            rec("agent", "2026-10-04T10:00:00+09:00", "alpha", "coder", "claude-haiku-5-5", "high", HUGE_QUARTER, HUGE_QUARTER, HUGE_QUARTER, HUGE_QUARTER, 5, 4, 2000),
            rec("agent", "2026-10-05T10:00:00+09:00", "alpha", "coder", "claude-opus-5-5", "high", 1000000, 0, 0, 0, 1, 1, 100)])
        t = self.report(1)
        self.assertEqual(line_of(t, "| claude-sonnet-5-5 | "), "| claude-sonnet-5-5 | Sonnet 5.5 | 2 / 10 / 2.5 / 0.1 | 2 | 0 | - |")
        self.assertTrue(line_of(t, "| coder | claude-sonnet-5-5 | ").startswith("| coder | claude-sonnet-5-5 | 2 | 2026-10-02 %s 2026-10-03 | 2 | " % EN))
        self.assertTrue(line_of(t, "| coder | claude-sonnet-5-5 | ").endswith(" | - | - | - | - | - | - | 2 | - |"))
        self.assertTrue(line_of(t, "| coder | claude-opus-5-5 | ").endswith(" | - | - | - | - | - | - | 1 | $4.00 |"))
        self.assertEqual(line_of(t, "| coder | claude-haiku-5-5 | "),
                         "| coder | claude-haiku-5-5 | 1 | 2026-10-04 | 0 | - | - | 1 | 2000 | min%smax 2000%s2000 | - | - | - | - | - | - | 1 | $2205000000000.00 |" % (EN, EN))
        self.assertEqual(line_of(t, "| claude-haiku-5-5 | "), "| claude-haiku-5-5 | Haiku 5.5 | 0.1 / 0.5 / 0.125 / 0.01 | 1 | 0 | $2205000000000.00 |")
        self.assertEqual(line_of(t, "| claude-opus-5-5 | "), "| claude-opus-5-5 | Opus 5.5 | 4 / 20 / 5 / 0.2 | 1 | 0 | $4.00 |")


class Versions(ReportCase):
    F1, F2 = "aaaa1111", "bbbb2222"
    APPLIED = " | applied by 2026-10-06 2026-10-06-1.md#2"

    def setUp(self):
        super().setUp()
        runs = []

        def add(day, hour, kind, role, h, tokens, ms, project="alpha"):
            t = "2026-10-%02dT%02d:00:00+09:00" % (day, hour)
            runs.append((t, rec(kind, t, project, role if kind == "agent" else None, M1, "high", tokens - 100, 100, 0, 0, 1, 1, ms, harness=h)))
        for i in range(5):
            add(1 + i, 10, "agent", "coder", self.F1, 1000 + 100 * i, 1000 + 100 * i)         # coder: clearly apart on both
            add(6 + i, 10, "agent", "coder", self.F2, 2000 + 100 * i, 3000 + 100 * i)
            add(1 + i, 11, "agent", "tester", self.F1, 1000 + 500 * i, 1000 + 100 * i)        # tester: tokens overlap, time is apart
            add(6 + i, 11, "agent", "tester", self.F2, 1400 + 500 * i, 5000 + 100 * i)
        for i in range(3):
            add(1 + i, 12, "agent", "reviewer", self.F1, 1000 + 100 * i, 1000 + 100 * i)      # reviewer: apart, but only 3 runs
            add(12 + i, 12, "agent", "reviewer", self.F2, 5000 + 100 * i, 5000 + 100 * i)
        add(5, 9, "agent", "designer", self.F1, 500, 500)                                      # designer: one run each, same tokens
        add(5, 15, "agent", "designer", self.F2, 500, 600)
        add(3, 13, "turn", None, self.F1, 300, 300)
        self.runs("2026-10", [l for _, l in sorted(runs, key=lambda r: r[0])])
        self.put("claude/lessons/harness-log.md", "\n".join([
            "- 2026-10-06 | 2026-10-06-1.md#2 | agents/coder.md | shorter | passed | " + self.F2,
            "- 2026-10-07 | 2026-10-07-1.md#1 | README.md | docs only (repo only, same fingerprint) | passed | " + self.F2]) + "\n")
        self.events(["# Events",
                     "- 2026-10-03 | alpha | fix-request | refactor · small | coder | user: wanted a rename",
                     "- 2026-10-04 | Alpha | Review-Block | feature · large | CODER | reviewer blocked",
                     "- 2026-10-08 | alpha | redone | docs · small | coder | redone after a miss",
                     "- 2026-10-09 | alpha | fix-request | docs · small | coder | user: asked for a fix",
                     "- 2026-10-03 | alpha | fix-request | chat · small | main | user: asked again",
                     "- 2026-10-13 | alpha | review-wrong | review · small | reviewer | finding was not a problem",
                     "- 2026-10-15 | alpha | fix-request | docs · small | coder | no coder run that day",
                     "- 2026-10-05 | gamma | fix-request | docs · small | coder | no run in that project",
                     "- 2026-10-05 | alpha | redone | docs · small | designer | the harness changed that day",
                     "- 2026-08-01 | alpha | fix-request | docs · small | coder | before the period",
                     "- not a date | alpha | fix-request | docs · small | coder | not in the format"])
        self.text = self.report(1)

    def test_one_row_per_role_and_version(self):
        t = self.text
        self.assertEqual(line_of(t, "| coder | aaaa1111 | "),
                         "| coder | aaaa1111 | 5 | 2026-10-01 %s 2026-10-05 | 5 | 1200 | p25%sp75 1100%s1300 | 5 | 1200 | p25%sp75 1100%s1300 |" % ((EN,) * 5))
        self.assertEqual(line_of(t, "| coder | bbbb2222 | "),
                         "| coder | bbbb2222 | 5 | 2026-10-06 %s 2026-10-10 | 5 | 2200 | p25%sp75 2100%s2300 | 5 | 3200 | p25%sp75 3100%s3300 |" % ((EN,) * 5))
        self.assertIn("| 3 | 1100 | min%smax 1000%s1200 | 3 | 1100 | min%smax 1000%s1200 |" % ((EN,) * 4), line_of(t, "| reviewer | aaaa1111 | "))
        self.assertLess(t.index("| coder | aaaa1111 | "), t.index("| coder | bbbb2222 | "))
        self.assertLess(t.index("| main conversation | aaaa1111 | "), t.index("| coder | aaaa1111 | "))

    def test_finding_needs_five_runs_each_and_apart_spreads(self):
        a = self.APPLIED
        self.assertIn("- coder: aaaa1111 \u2192 bbbb2222 | runs 5 \u2192 5 | tokens median 1200 (n=5) \u2192 2200 (n=5): finding, median difference +1000 "
                      "| time (ms) median 1200 (n=5) \u2192 3200 (n=5): finding, median difference +2000" + a + "\n", self.text)
        self.assertIn("- tester: aaaa1111 \u2192 bbbb2222 | runs 5 \u2192 5 | tokens median 2000 (n=5) \u2192 2400 (n=5): noise / inconclusive (spreads overlap) "
                      "| time (ms) median 1200 (n=5) \u2192 5200 (n=5): finding, median difference +4000" + a + "\n", self.text)

    def test_few_runs_are_noise_with_the_reason(self):
        a = self.APPLIED
        self.assertIn("- reviewer: aaaa1111 \u2192 bbbb2222 | runs 3 \u2192 3 | tokens median 1100 (n=3) \u2192 5100 (n=3): noise / inconclusive (n < 5) "
                      "| time (ms) median 1100 (n=3) \u2192 5100 (n=3): noise / inconclusive (n < 5)" + a + "\n", self.text)
        self.assertIn("- designer: aaaa1111 \u2192 bbbb2222 | runs 1 \u2192 1 | tokens median 500 (n=1) \u2192 500 (n=1): noise / inconclusive (n < 5; spreads overlap) "
                      "| time (ms) median 500 (n=1) \u2192 600 (n=1): noise / inconclusive (n < 5)" + a + "\n", self.text)
        self.assertNotIn("- main conversation:", self.text)

    def test_the_first_harness_log_line_of_a_fingerprint_is_used(self):
        self.assertNotIn("2026-10-07-1.md", self.text)
        self.assertEqual(self.text.count("applied by"), 4)

    def test_events_are_joined_by_date_project_and_role(self):
        t = self.text
        for row in ("| coder | aaaa1111 | 5 | fix-request | 1 | 0.2 |", "| coder | aaaa1111 | 5 | review-block | 1 | 0.2 |",
                    "| coder | bbbb2222 | 5 | fix-request | 1 | 0.2 |", "| coder | bbbb2222 | 5 | redone | 1 | 0.2 |",
                    "| main conversation | aaaa1111 | 1 | fix-request | 1 | 1 |", "| reviewer | bbbb2222 | 3 | review-wrong | 1 | 0.33 |"):
            self.assertIn(row, t)
        self.assertNotIn("| tester |", t[t.index("## Outcome signals"):])

    def test_event_counts(self):
        self.assertIn("- Events in the period: 9 \u00b7 joined to a harness version 6 \u00b7 no run of that role in that project that day 2 "
                      "\u00b7 harness changed that day, so not attributed 1\n", self.text)
        self.assertIn("`- YYYY-MM-DD | project | signal | work type \u00b7 size | role | fact`): 1\n", self.text)
        self.assertNotIn("2026-08", self.text)
        self.assertIn("a lower bound", self.text)
        self.assertIn("; not in the counts above): 0\n", self.text)

    def test_the_current_fingerprint_line(self):
        h, files = sh.fingerprint(self.claude, self.plugin, self.proj)
        self.assertIn("- Current harness fingerprint: %s (%d files)\n" % (h, len(files)), self.text)


class Models(ReportCase):
    OPUS, SONNET, HAIKU55, HAIKU45 = "claude-opus-5-5[1m]", "claude-sonnet-5-5-20261001", "claude-haiku-5-5", "claude-haiku-4-5-20251001"
    FABLE, OPUS41, MYSTERY = "claude-fable-5-1", "claude-opus-4-1-20250805", "claude-mystery-9-9"

    def setUp(self):
        super().setUp()
        self.runs("2026-10", [
            rec("agent", "2026-10-02T10:00:00+09:00", "alpha", "coder", self.OPUS, "high", 1000000, 100000, 10000000, 2000000, 4, 3, 1000),   # 18.00
            rec("agent", "2026-10-03T10:00:00+09:00", "alpha", "coder", self.OPUS, "high", 500000, 50000, 5000000, 1000000, 4, 3, 2000),      # 9.00
            rec("agent", "2026-10-04T10:00:00+09:00", "alpha", "coder", self.SONNET, "high", 2000000, 200000, 4000000, 1000000, 4, 3, 3000),  # 8.90
            rec("turn", "2026-10-05T10:00:00+09:00", "alpha", None, self.OPUS, "medium", None, 5000000, 5000000, 1000000, 1, 1, 250, "in"),   # unread in: left out
            rec("agent", "2026-10-06T10:00:00+09:00", "alpha", "tester", self.HAIKU55, "high", 10000000, 1000000, 100000000, 4000000, 2, 2, 400),
            rec("agent", "2026-10-06T11:00:00+09:00", "alpha", "tester", self.HAIKU45, "high", 1000000, 1000000, 1000000, 1000000, 2, 2, 500),
            rec("agent", "2026-10-07T10:00:00+09:00", "alpha", "designer", self.FABLE, "high", 1000000, 1000000, 1000000, 1000000, 2, 2, 600),
            rec("agent", "2026-10-08T10:00:00+09:00", "alpha", "reviewer", self.OPUS41, "high", 1000000, 1000000, 1000000, 1000000, 2, 2, 700),
            rec("agent", "2026-10-08T11:00:00+09:00", "alpha", "reviewer", self.MYSTERY, "high", 1000000, 1000000, 1000000, 1000000, 2, 2, 800),
            rec("agent", "2026-10-09T10:00:00+09:00", "alpha", "researcher", None, None, 100, 10, 1000, 50, 1, 1, 100, "model")])
        self.text = self.report(1)

    def row(self, role, model):
        return line_of(self.text, "| %s | %s | " % (role, model))

    def test_role_x_model_rows(self):
        mm = "min%smax" % EN
        self.assertEqual(self.row("coder", self.OPUS),
                         "| coder | %s | 2 | 2026-10-02 %s 2026-10-03 | 2 | 9825000 | %s 6550000%s13100000 | 2 | 1500 | %s 1000%s2000 | - | - | - | - | - | - | 2 | $27.00 |"
                         % (self.OPUS, EN, mm, EN, mm, EN))
        self.assertEqual(self.row("coder", self.SONNET),
                         "| coder | %s | 1 | 2026-10-04 | 1 | 7200000 | %s 7200000%s7200000 | 1 | 3000 | %s 3000%s3000 | - | - | - | - | - | - | 1 | $8.90 |"
                         % (self.SONNET, mm, EN, mm, EN))
        self.assertEqual(self.row("main conversation", self.OPUS),
                         "| main conversation | %s | 1 | 2026-10-05 | 0 | - | - | 1 | 250 | %s 250%s250 | - | - | - | - | - | - | 0 | - |" % (self.OPUS, mm, EN))
        self.assertEqual(self.row("researcher", "(model unknown)"),
                         "| researcher | (model unknown) | 1 | 2026-10-09 | 1 | 1160 | %s 1160%s1160 | 1 | 100 | %s 100%s100 | - | - | - | - | - | - | 1 | - |" % (mm, EN, mm, EN))
        self.assertTrue(line_of(self.text, "| coder | a1b2c3d4 | ").startswith("| coder | a1b2c3d4 | 3 | "))

    def test_section_and_row_order(self):
        t = self.text
        sections = [t.index(s) for s in ("\n## Role \u00d7 harness version\n", "\n## Role \u00d7 model\n", "\n### Approximate cost per model\n", "\n## Outcome signals")]
        self.assertEqual(sections, sorted(sections))
        start = sections[1]
        rows = [t.index(s, start) for s in ("| main conversation | %s | " % self.OPUS, "| coder | %s | " % self.OPUS, "| coder | %s | " % self.SONNET,
                                           "| designer | ", "| researcher | ", "| reviewer | %s | " % self.OPUS41, "| tester | %s | " % self.HAIKU45)]
        self.assertEqual(rows, sorted(rows))

    def test_cost_table(self):
        t = self.text
        self.assertEqual(line_of(t, "| %s | " % self.OPUS), "| %s | Opus 5.5 | 4 / 20 / 5 / 0.2 | 3 | 1 | $27.00 |" % self.OPUS)
        self.assertEqual(line_of(t, "| %s | " % self.SONNET), "| %s | Sonnet 5.5 | 2 / 10 / 2.5 / 0.1 | 1 | 0 | $8.90 |" % self.SONNET)
        self.assertEqual(line_of(t, "| %s | " % self.HAIKU55), "| %s | Haiku 5.5 | 0.1 / 0.5 / 0.125 / 0.01 | 1 | 0 | $3.00 |" % self.HAIKU55)
        self.assertEqual(line_of(t, "| %s | " % self.HAIKU45), "| %s | Haiku 4.5 | 1 / 5 / 1.25 / 0.1 | 1 | 0 | $7.35 |" % self.HAIKU45)
        self.assertEqual(line_of(t, "| %s | " % self.FABLE), "| %s | Fable 5.1 | 10 / 50 / 12.5 / 0.25 | 1 | 0 | $72.75 |" % self.FABLE)

    def test_a_model_without_a_known_price_is_never_guessed(self):
        t = self.text
        self.assertEqual(line_of(t, "| %s | " % self.OPUS41), "| %s | - | - | 1 | 0 | - |" % self.OPUS41)
        self.assertEqual(line_of(t, "| %s | " % self.MYSTERY), "| %s | - | - | 1 | 0 | - |" % self.MYSTERY)
        self.assertEqual(line_of(t, "| (model unknown) | "), "| (model unknown) | - | - | 1 | 0 | - |")

    def test_cost_text(self):
        for part in ("Approximate: tokens \u00d7 list price (USD per million tokens as of 2026-10-21)",
                     "Cache writes are priced at the 5-minute rate because the 1-hour split is not recorded.",
                     "Haiku 5.5 is priced at the rate for prompts up to 100K tokens, so its cost is a lower bound.",
                     "never a guess", "left out of the cost and counted under `Left out`"):
            self.assertIn(part, self.text)
        self.assertIn("- Signal columns show `-`: events.md not found: no outcome signals.\n", self.text)
        self.assertNotIn("- Ambiguous model:", self.text)

    def test_months_two_and_repeatable(self):
        self.assertEqual(self.report(1), self.text)
        self.assertIn("| %s | Opus 5.5 | " % self.OPUS, self.report(2))

    def test_prices_come_from_the_plugin_and_are_not_guessed_when_missing(self):
        os.remove(os.path.join(self.plugin, "scripts", "prices.json"))
        p = self.run_report("--months", "1")
        self.assertEqual(p.returncode, 0)
        self.assertIn(b"warning", p.stderr)
        t = slurp(os.path.join(self.lessons, "report.md")).decode("utf-8")
        self.assertIn("as of unknown)", t)
        self.assertEqual(line_of(t, "| %s | " % self.OPUS), "| %s | - | - | 3 | 1 | - |" % self.OPUS)


class Signals(ReportCase):
    def tokens(self, t, project, role, model, missing=None):
        return rec("turn" if role is None else "agent", t, project, role, model, "high", None if missing else 1000000, 0, 0, 0, 1, 1, 100,
                   *([missing] if missing else []))

    def test_signals_join_the_model_of_the_runs_of_that_day(self):
        self.runs("2026-10", [
            self.tokens("2026-10-02T10:00:00+09:00", "alpha", "coder", "claude-opus-5-5"),
            self.tokens("2026-10-03T10:00:00+09:00", "alpha", "coder", "claude-sonnet-5-5"),
            self.tokens("2026-10-04T10:00:00+09:00", "alpha", "coder", "claude-opus-5-5"),      # two models on 10-04: an event of that day is ambiguous
            self.tokens("2026-10-04T11:00:00+09:00", "alpha", "coder", "claude-sonnet-5-5"),
            self.tokens("2026-10-05T10:00:00+09:00", "alpha", "coder", "Claude-Opus-5-5"),      # the same model with another spelling
            self.tokens("2026-10-06T10:00:00+09:00", "beta", "coder", "claude-opus-5-5"),
            self.tokens("2026-10-07T10:00:00+09:00", "alpha", None, "claude-opus-5-5"),
            self.tokens("2026-10-08T10:00:00+09:00", "alpha", "reviewer", "claude-mystery-9-9"),
            self.tokens("2026-10-09T10:00:00+09:00", "alpha", "coder", "claude-sonnet-5-5", missing="in")])
        self.events(["# Events",
                     "- 2026-10-02 | alpha | fix-request | refactor · small | coder | user: wanted a rename",
                     "- 2026-10-02 | Alpha | Review-Block | feature · large | CODER | reviewer blocked",
                     "- 2026-10-02 | alpha | surprise | feature · small | coder | a signal word with no column of its own",
                     "- 2026-10-03 | alpha | fix-request | docs · small | coder | user: asked for a fix",
                     "- 2026-10-03 | alpha | redone | experiment · small | coder | an expected iteration: in no row",
                     "- 2026-10-04 | alpha | fix-request | docs · small | coder | two models that day",
                     "- 2026-10-04 | alpha | redone | docs · small | coder | two models that day",
                     "- 2026-10-05 | alpha | review-wrong | experiment · small | coder | the finding was not a problem",
                     "- 2026-10-05 | alpha | repeated-failure | experiment · small | coder | an expected iteration: in no row",
                     "- 2026-10-06 | beta | fix-request | docs · small | coder | another project, the same model row",
                     "- 2026-10-07 | alpha | fix-request | chat · small | main | user: asked again",
                     "- 2026-10-08 | alpha | repeated-failure | docs · small | reviewer | a model with no known price",
                     "- 2026-10-12 | alpha | fix-request | docs · small | coder | no coder run that day"])
        t = self.report(1)
        self.assertTrue(line_of(t, "| coder | claude-opus-5-5 | ").endswith(" | 2 | 1 | 1 | 0 | 0 | 1 | 4 | $16.00 |"))
        self.assertTrue(line_of(t, "| coder | claude-sonnet-5-5 | ").endswith(" | 1 | 0 | 0 | 0 | 0 | 0 | 2 | $4.00 |"))
        self.assertTrue(line_of(t, "| main conversation | claude-opus-5-5 | ").endswith(" | 1 | 0 | 0 | 0 | 0 | 0 | 1 | $4.00 |"))
        self.assertTrue(line_of(t, "| reviewer | claude-mystery-9-9 | ").endswith(" | 0 | 0 | 0 | 1 | 0 | 0 | 1 | - |"))
        self.assertIn("| Role | Model | Runs | First \u2013 last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread | fix-request "
                      "| review-block | review-wrong | repeated-failure | redone | other signals | Cost n | Approx. cost (USD) |\n", t)
        self.assertIn("- Ambiguous model: 2 event(s) matched runs of more than one model that day, so they are in no row above (fix-request 1 \u00b7 redone 1)\n", t)
        self.assertIn("- Events in the period: 11 \u00b7 joined to a harness version 10 \u00b7 no run of that role in that project that day 1 "
                      "\u00b7 harness changed that day, so not attributed 0\n", t)
        self.assertIn("; not in the counts above): 2\n", t)
        # the same model spelt in two ways is one row, shown in lower case, priced as one
        self.assertEqual(len([l for l in t.split("\n") if l.startswith("| coder | claude-opus-5-5 | ")]), 1)
        self.assertNotIn("Claude-Opus-5-5", t)
        self.assertTrue(line_of(t, "| coder | claude-opus-5-5 | ").startswith("| coder | claude-opus-5-5 | 4 | 2026-10-02 %s 2026-10-06 | 4 | 1000000 | " % EN))
        self.assertEqual(line_of(t, "| claude-opus-5-5 | "), "| claude-opus-5-5 | Opus 5.5 | 4 / 20 / 5 / 0.2 | 5 | 0 | $20.00 |")
        self.assertEqual(line_of(t, "| claude-sonnet-5-5 | "), "| claude-sonnet-5-5 | Sonnet 5.5 | 2 / 10 / 2.5 / 0.1 | 3 | 1 | $4.00 |")
        self.assertIn("Model ids that differ only in case are one row (shown in lower case).", t)


class Experiments(ReportCase):
    """Work type `experiment`: repeated-failure and redone are expected iterations; the other signals still count."""

    def setUp(self):
        super().setUp()
        self.runs("2026-10", [rec("agent", "2026-10-%02dT10:00:00+09:00" % d, "alpha", "coder", M1, "high", 100, 10, 1000, 50, 4, 3, 1000) for d in range(1, 5)])
        self.events(["# Events",
                     "- 2026-10-03 | alpha | fix-request | refactor · small | coder | user: wanted a rename",
                     "- 2026-10-03 | alpha | redone | docs · small | coder | experiment notes redone",
                     "- 2026-10-02 | alpha | fix-request | experiment · small | coder | a baseline run needed a fix",
                     "- 2026-10-04 | Alpha | Review-Block | Experiment · large | CODER | reviewer blocked a try",
                     "- 2026-10-01 | alpha | review-wrong | experiment · small | coder | a finding in an experiment was not a problem",
                     "- 2026-10-04 | alpha | repeated-failure | experiment | coder | no size given",
                     "- 2026-10-02 | alpha | Redone | Experiment · small | coder | a try was redone",
                     "- 2026-10-05 | gamma | redone | experiment · small | coder | no run in that project",
                     "- 2026-08-01 | alpha | redone | experiment · small | coder | before the period"])
        self.text = self.report(1)
        self.signals = self.text[self.text.index("## Outcome signals"):]

    def test_harness_signals_are_counted_whatever_the_work_type(self):
        s = self.signals
        for row in ("| coder | a1b2c3d4 | 4 | fix-request | 2 | 0.5 |", "| coder | a1b2c3d4 | 4 | review-block | 1 | 0.25 |",
                    "| coder | a1b2c3d4 | 4 | review-wrong | 1 | 0.25 |", "| coder | a1b2c3d4 | 4 | redone | 1 | 0.25 |"):
            self.assertIn(row, s)
        self.assertIsNone(line_of(s, "| coder | a1b2c3d4 | 4 | repeated-failure | "))
        self.assertIn("- Events in the period: 5 \u00b7 joined to a harness version 5 \u00b7 no run of that role in that project that day 0 "
                      "\u00b7 harness changed that day, so not attributed 0\n", s)

    def test_expected_iterations_are_a_count_of_their_own(self):
        s = self.signals
        self.assertIn("- Expected experiment iterations (`repeated-failure` \u00b7 `redone` with work type `experiment`; not in the counts above): 3\n", s)
        self.assertNotIn("2026-08", s)
        self.assertIn("A `repeated-failure` or `redone` event whose work type is `experiment` is an expected iteration", s)
        self.assertIn("The other signals (`fix-request` \u00b7 `review-block` \u00b7 `review-wrong`) with work type `experiment` are harness signals and are counted as usual.", s)

    def test_the_model_table_follows_the_same_rule(self):
        self.assertTrue(line_of(self.text, "| coder | %s | " % M1).endswith(" | 2 | 1 | 1 | 0 | 1 | 0 | 4 | - |"))

    def test_the_months_decide_which_expected_iterations_count(self):
        self.assertIn("; not in the counts above): 4\n", self.report(3))


# ----------------------------------------------------------------------------------------------
# the command line (5.1)
# ----------------------------------------------------------------------------------------------

class CommandLine(ReportCase):
    def setUp(self):
        super().setUp()
        self.runs("2026-10", [rec("agent", "2026-10-02T10:00:00+09:00", "alpha", "coder", M1, "high", 100, 10, 1000, 50, 4, 3, 1000)])

    def test_default_output_and_stdout(self):
        p = self.run_report("--months", "1")
        self.assertEqual(p.returncode, 0)
        out = os.path.join(self.lessons, "report.md")
        self.assertEqual(p.stdout.decode("utf-8").strip(), os.path.abspath(out))
        data = slurp(out)
        self.assertTrue(data.startswith(b"# Lessons record summary\n"))
        self.assertNotIn(b"\r", data)
        self.assertTrue(data.endswith(b"\n"))
        self.assertFalse(os.path.exists(out + ".tmp"))

    def test_named_output_relative_to_the_working_directory(self):
        work = os.path.join(self.tmp, "work")
        os.makedirs(work)
        p = self.run_report("deep/er/summary.md", cwd=work)
        self.assertEqual(p.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.lessons, "report.md")))
        self.assertTrue(slurp(os.path.join(work, "deep", "er", "summary.md")).startswith(b"# "))

    def test_bad_arguments_exit_2_and_write_nothing(self):
        bad = [["--months", "0"], ["--months", "121"], ["--months", "x"], ["--months", "-1"], ["--months", " 3"], ["--months", "+3"], ["--months", "1.0"],
               ["--months", ""], ["--months"], ["--bogus"], ["a.md", "b.md"], [""], ["--months=2"]]
        for args in bad:
            p = self.run_report(*args)
            self.assertEqual(p.returncode, 2, args)
            self.assertEqual(p.stdout, b"", args)
        self.assertFalse(os.path.exists(os.path.join(self.lessons, "report.md")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "a.md")))

    def test_months_accepts_leading_zeros_and_the_bounds(self):
        for m in ("1", "01", "09", "120"):
            self.assertEqual(self.run_report("--months", m).returncode, 0, m)

    def test_a_nul_in_the_output_path_is_a_usage_error(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = sh.main(["report", "a\0b.md", "--claude-dir", self.claude, "--plugin-root", self.plugin, "--now", NOW])
        self.assertEqual(code, 2)
        self.assertFalse(os.path.exists("a"))

    def test_an_output_that_cannot_be_written_exits_1(self):
        p = self.run_report(self.lessons)       # a folder
        self.assertEqual(p.returncode, 1)
        self.assertEqual(len(p.stderr.decode("utf-8").strip().split("\n")), 1)

    def test_bad_clock_exits_2(self):
        for now in ("bad", "2026-10-21T14:00:00", "2026-02-30T10:00:00Z", "2026-10-21T25:00:00Z", "2026-10-21T14:00:00+15:00"):
            self.assertEqual(self.run_report(now=now).returncode, 2, now)


# ----------------------------------------------------------------------------------------------
# the spec stays the source of the fixed text and of the examples
# ----------------------------------------------------------------------------------------------

class SpecLink(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = slurp(SPEC).decode("utf-8")

    def test_fixed_paragraphs_are_in_the_spec_word_for_word(self):
        for name in ("TXT_ROLE_TABLE", "TXT_VERSION_TABLE", "TXT_COMPARE", "TXT_MODEL_1", "TXT_MODEL_2", "TXT_COST", "TXT_EVENTS"):
            self.assertIn(getattr(sh, name).rstrip("\n"), self.spec, name)
        self.assertIn(sh.TXT_NO_RUNS.rstrip("\n"), self.spec)
        self.assertIn(sh.TXT_NONE_COMPARED.rstrip("\n"), self.spec)

    def test_example_blocks_of_the_spec_appear_in_the_example_cases(self):
        corpus = "\n".join(slurp(f).decode("utf-8") for f in glob.glob(os.path.join(CASES, "report-*", "expected", "**", "*.md"), recursive=True))
        blocks = re.findall(r"```[^\n]*\n(.*?)```", self.spec, re.S)
        checked = 0
        for b in blocks:
            first = b.split("\n")[0]
            concrete = "{" not in b and not first.startswith("- 20")
            if concrete and (first.startswith("| ") or first.startswith("# Lessons") or first.startswith("- coder:") or first.startswith("- Lines with unread")
                             or first.startswith("- Ambiguous")):
                checked += 1
                self.assertIn(b.rstrip("\n"), corpus, first)
        self.assertGreaterEqual(checked, 8)


if __name__ == "__main__":
    unittest.main()
