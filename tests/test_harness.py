"""Harness tests: `lint` of every selected implementation, and the Claude Code plugin validator.

* tests/fixtures/lint/<case>/ are small trees with their own tests/harness-rules.json. A rule whose id ends in
  ".bad" must fail and a rule whose id ends in ".ok" must pass; expect.txt lists the exit code and the failing ids.
  args.txt (optional) holds extra arguments, for example "--group later".
* The repository itself must pass its own rules (every rule is in group "core"; tests/harness-rules.md, "Groups").
* Copies of the repository with one change each must fail with the expected rule ids.
* `claude plugin validate . --strict` runs when the claude command is on PATH.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

import test_conformance as conf

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
LINT_CASES = os.path.join(HERE, "fixtures", "lint")
IMPLS = ("py", "ps1")
# what the rules look at; the copies for the mutation tests hold only these
REPO_PARTS = (".claude-plugin", "agents", "output-styles", "skills", "docs", "hooks", "scripts", "README.md", "CHANGELOG.md", "LICENSE",
              os.path.join("tests", "harness-rules.json"), os.path.join("tests", "harness-rules.md"))


def slurp(path):
    with open(path, "rb") as f:
        return f.read()


def failed_ids(stdout):
    """The rule ids on the lines of a lint run: the first word, or the second after FAIL."""
    ids = []
    for line in stdout.decode("utf-8", "replace").splitlines():
        words = line.split()
        if not words:
            continue
        ids.append(words[1] if words[0] == "FAIL" and len(words) > 1 else words[0])
    return sorted(ids)


def run_lint(command, root, extra=(), impl="py"):
    env = conf.impl_env(impl, {k: v for k, v in os.environ.items() if k not in conf.CLEAN_ENV})
    return subprocess.run(command + ["lint", "--root", root] + list(extra), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env=env, timeout=180)


def copy_tree(src, dst):
    """Copy a lint fixture root; a folder named _git becomes .git."""
    for folder, dirs, files in os.walk(src):
        rel = os.path.relpath(folder, src)
        target = dst if rel == "." else os.path.join(dst, *[".git" if p == "_git" else p for p in rel.split(os.sep)])
        os.makedirs(target, exist_ok=True)
        for name in files:
            shutil.copyfile(os.path.join(folder, name), os.path.join(target, name))


def copy_repo(dst):
    for part in REPO_PARTS:
        src = os.path.join(REPO, part)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dst, part), ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(os.path.join(dst, part)), exist_ok=True)
            shutil.copyfile(src, os.path.join(dst, part))


def case_names():
    return sorted(n for n in os.listdir(LINT_CASES) if os.path.isdir(os.path.join(LINT_CASES, n)))


# ----------------------------------------------------------------------------------------------
# the fixtures describe themselves consistently
# ----------------------------------------------------------------------------------------------

class LintFixtureSanity(unittest.TestCase):
    def test_expectations_follow_the_id_suffixes(self):
        for name in case_names():
            base = os.path.join(LINT_CASES, name)
            doc = json.loads(slurp(os.path.join(base, "root", "tests", "harness-rules.json")).decode("ascii"))
            args = shlex.split(slurp(os.path.join(base, "args.txt")).decode("utf-8")) if os.path.exists(os.path.join(base, "args.txt")) else []
            groups = set(["core"] + [args[i + 1] for i, a in enumerate(args) if a == "--group"])
            want = sorted(r["id"] for r in doc["rules"] if r["id"].endswith(".bad") and r.get("group", "core") in groups)
            lines = slurp(os.path.join(base, "expect.txt")).decode("utf-8").split("\n")
            code = int(lines[0].split()[1])
            listed = sorted(l for l in lines[1:] if l)
            if code in (0, 1) and not name.startswith(("rules-", "group-rule", "group-unknown")):
                self.assertEqual(listed, want, name)
                self.assertEqual(code, 1 if want else 0, name)
            for r in doc["rules"]:
                self.assertRegex(r["id"], r"^[a-z0-9.-]+$", name)

    def test_rule_files_are_pure_ascii(self):
        for name in case_names():
            slurp(os.path.join(LINT_CASES, name, "root", "tests", "harness-rules.json")).decode("ascii")
        slurp(os.path.join(HERE, "harness-rules.json")).decode("ascii")

    def test_no_hangul_in_the_fixtures(self):
        rx = re.compile("[\uac00-\ud7a3]")
        for folder, _, files in os.walk(LINT_CASES):
            for n in files:
                self.assertIsNone(rx.search(slurp(os.path.join(folder, n)).decode("utf-8", "replace")), os.path.join(folder, n))


# ----------------------------------------------------------------------------------------------
# lint on the fixture trees, per implementation
# ----------------------------------------------------------------------------------------------

class LintFixtures(unittest.TestCase):
    def run_case(self, name, impl):
        command = conf.require(self, impl)
        base = os.path.join(LINT_CASES, name)
        tmp = tempfile.mkdtemp(prefix="spanharness-lint-")
        self.addCleanup(shutil.rmtree, tmp, True)
        root = os.path.join(tmp, "root")
        copy_tree(os.path.join(base, "root"), root)
        extra = shlex.split(slurp(os.path.join(base, "args.txt")).decode("utf-8")) if os.path.exists(os.path.join(base, "args.txt")) else []
        lines = slurp(os.path.join(base, "expect.txt")).decode("utf-8").split("\n")
        code = int(lines[0].split()[1])
        want = sorted(l for l in lines[1:] if l)
        p = run_lint(command, root, extra, impl)
        self.assertEqual(p.returncode, code, "exit code\nstdout: %s\nstderr: %s" % (p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")))
        self.assertEqual(failed_ids(p.stdout), want, p.stdout.decode("utf-8", "replace"))


def _add_fixture_tests():
    for name in case_names():
        for impl in IMPLS:
            def t(self, name=name, impl=impl):
                self.run_case(name, impl)
            setattr(LintFixtures, "test_%s__%s" % (name.replace("-", "_"), impl), t)


_add_fixture_tests()


# ----------------------------------------------------------------------------------------------
# the repository
# ----------------------------------------------------------------------------------------------

class RepoLint(unittest.TestCase):
    def lint_repo(self, impl):
        command = conf.require(self, impl)
        p = run_lint(command, REPO, (), impl)
        self.assertEqual(p.returncode, 0, "the repository fails its own rules:\n%s%s" % (p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")))
        self.assertEqual(p.stdout, b"")

    def test_repo_passes_py(self):
        self.lint_repo("py")

    def test_repo_passes_ps1(self):
        self.lint_repo("ps1")


def _mutations():
    """name -> (function that changes a copy of the repo, rule ids that must be among the failures)."""
    def agent(role):
        return os.path.join("agents", role + ".md")

    def edit(rel, fn):
        def go(root):
            p = os.path.join(root, rel)
            text = slurp(p).decode("utf-8")
            new = fn(text)
            assert new != text, "the mutation changed nothing: " + rel
            with open(p, "wb") as f:
                f.write(new.encode("utf-8"))
        return go

    def delete(rel):
        return lambda root: os.remove(os.path.join(root, rel))

    def add(rel, text):
        def go(root):
            p = os.path.join(root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(text.encode("utf-8"))
        return go

    def chain(*fns):
        return lambda root: [f(root) for f in fns]

    hangul = chr(0xAC00) + chr(0xB098)
    return {
        "agent-file-deleted": (delete(agent("tester")), ["files.agents.exact", "agent.tester.frontmatter"]),
        "extra-agent-file": (add(agent("intruder"), "---\nname: intruder\n---\nx\n"), ["files.agents.exact"]),
        "haiku-model": (edit(agent("coder"), lambda t: re.sub(r"(?m)^model: \w+$", "model: haiku", t, 1)), ["agents.model.no-haiku", "agent.coder.frontmatter"]),
        "unknown-effort": (edit(agent("coder"), lambda t: re.sub(r"(?m)^effort: \w+$", "effort: enormous", t, 1)), ["agents.effort.known", "agent.coder.frontmatter"]),
        "report-line-removed": (edit(agent("reviewer"), lambda t: t[:t.rstrip("\n").rfind("\n")] + "\n"), ["agents.report-line.last"]),
        "section-order": (edit(agent("coder"), lambda t: t.replace("## Do not", "## Not to do", 1)), ["agents.sections.required"]),
        "hangul-in-readme": (edit("README.md", lambda t: t + "\n" + hangul + "\n"), ["forbid.hangul"]),
        "hangul-in-agent": (edit(agent("coder"), lambda t: t.replace("\n---\n", "\n---\n" + hangul + "\n", 1)), ["forbid.hangul"]),
        "home-path-in-docs": (edit(os.path.join("docs", "development.md"), lambda t: t + "\nSee /home/someone/work.\n"), ["forbid.home-path"]),
        "windows-path-in-docs": (edit(os.path.join("docs", "development.md"), lambda t: t + "\nSee C:\\Users\\someone\\work.\n"), ["forbid.windows-user-path"]),
        "mail-in-readme": (edit("README.md", lambda t: t + "\nwrite to somebody@gmail.com\n"), ["forbid.gmail"]),
        "co-authored-by-in-orchestrator": (edit(os.path.join("output-styles", "orchestrator.md"), lambda t: t + "\nCo-Authored-By: x\n"), ["forbid.co-authored-by"]),
        "plugin-renamed": (edit(os.path.join(".claude-plugin", "plugin.json"), lambda t: t.replace('"spanharness"', '"other"', 1)), ["plugin.name"]),
        "marketplace-renamed": (edit(os.path.join(".claude-plugin", "marketplace.json"), lambda t: t.replace('"name": "spanharness"', '"name": "other"', 1)), ["marketplace.name"]),
        "skill-deleted": (delete(os.path.join("skills", "new-project", "SKILL.md")), ["skill.frontmatter", "files.plugin.exist"]),
        "orchestrator-deleted": (delete(os.path.join("output-styles", "orchestrator.md")), ["orch.frontmatter", "files.plugin.exist"]),
        "readme-deleted": (delete("README.md"), ["files.plugin.exist"]),
        "hook-command-without-plugin-root": (edit(os.path.join("hooks", "hooks.json"), lambda t: t.replace("${CLAUDE_PLUGIN_ROOT}/scripts/", "scripts/")),
                                             ["hooks.SubagentStop.script", "hooks.Stop.script"]),
        "launcher-deleted": (delete(os.path.join("scripts", "spanharness.sh")), ["files.recorder.exist"]),
        "script-with-non-ascii": (chain(add(os.path.join("scripts", "spanharness.ps1"), "# caf\u00e9\n")), ["scripts.ps1.ascii-only"]),
    }


MUTATIONS = _mutations()


class RepoMutations(unittest.TestCase):
    def run_mutation(self, name, impl):
        command = conf.require(self, impl)
        change, want = MUTATIONS[name]
        tmp = tempfile.mkdtemp(prefix="spanharness-mutation-")
        self.addCleanup(shutil.rmtree, tmp, True)
        copy_repo(tmp)
        change(tmp)
        p = run_lint(command, tmp, (), impl)
        ids = failed_ids(p.stdout)
        self.assertEqual(p.returncode, 1, p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace"))
        for rid in want:
            self.assertIn(rid, ids, "expected %s among %s" % (rid, ids))
        if name == "script-with-non-ascii":
            self.assertIn("scripts.ps1.ascii-only", ids)


def _add_mutation_tests():
    for name in MUTATIONS:
        for impl in IMPLS:
            def t(self, name=name, impl=impl):
                self.run_mutation(name, impl)
            setattr(RepoMutations, "test_%s__%s" % (name.replace("-", "_"), impl), t)


_add_mutation_tests()


# ----------------------------------------------------------------------------------------------
# lint command line
# ----------------------------------------------------------------------------------------------

class LintArguments(unittest.TestCase):
    def test_bad_arguments_exit_2(self):
        command = conf.require(self, "py")
        env = {k: v for k, v in os.environ.items() if k not in conf.CLEAN_ENV}
        for args in (["--bogus"], ["extra"], ["--root"], ["--group", "nope", "--root", REPO]):
            p = subprocess.run(command + ["lint"] + args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=60)
            self.assertEqual(p.returncode, 2, args)

    def test_a_root_without_rules_is_a_failure(self):
        command = conf.require(self, "py")
        tmp = tempfile.mkdtemp(prefix="spanharness-lint-")
        self.addCleanup(shutil.rmtree, tmp, True)
        self.assertEqual(run_lint(command, tmp).returncode, 1)

    def test_default_root_is_the_plugin_root(self):
        command = conf.require(self, "py")
        env = {k: v for k, v in os.environ.items() if k not in conf.CLEAN_ENV}
        p = subprocess.run(command + ["lint"], stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=120, cwd=tempfile.gettempdir())
        self.assertEqual(p.returncode, 0, p.stdout.decode("utf-8", "replace"))


# ----------------------------------------------------------------------------------------------
# the Claude Code validator
# ----------------------------------------------------------------------------------------------

class PluginValidate(unittest.TestCase):
    def test_claude_plugin_validate_strict(self):
        exe = shutil.which("claude")
        if not exe:
            self.skipTest("the claude command is not on PATH")
        p = subprocess.run([exe, "plugin", "validate", ".", "--strict"], cwd=REPO, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=300)
        self.assertEqual(p.returncode, 0, p.stdout.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
