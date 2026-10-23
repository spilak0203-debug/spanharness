"""Hook tests: the commands in hooks/hooks.json run the way Claude Code runs them, and the launcher scripts/spanharness.sh.

* The commands are read from hooks/hooks.json, `${CLAUDE_PLUGIN_ROOT}` is replaced by the repository path textually, and the
  command is run by `sh -c` (Linux, macOS), or by Git Bash `bash -c` and by `powershell.exe -Command` (Windows), with a
  SubagentStop or a Stop input on stdin and CLAUDE_CONFIG_DIR / HOME in a sandbox.
* Each event must exit 0, print nothing on stdout, and leave exactly one record in runs/YYYY-MM.jsonl: the second runtime of
  the command (the PowerShell script on Linux and macOS, the shell script on Windows) must not add a second one.
* The launcher branches are tested with stub programs on PATH where the host does not give them for free.
* The latency of the whole hook command is measured and printed to stderr (no limit is asserted).
"""
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import unittest

import test_conformance as conf

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPTS = os.path.join(REPO, "scripts")
LAUNCHER = os.path.join(SCRIPTS, "spanharness.sh")
WINDOWS = os.name == "nt"
ROOT_VAR = "${CLAUDE_PLUGIN_ROOT}"
AGENT_TRANSCRIPT = os.path.join(conf.CASES, "agent-basic", "input", "transcripts", "agent-ag1.jsonl")
MAIN_TRANSCRIPT = (
    '{"type":"user","timestamp":"2026-10-21T10:00:00.000Z","message":{"role":"user","content":"hello"}}\n'
    '{"type":"assistant","timestamp":"2026-10-21T10:00:04.000Z","message":{"id":"main1","model":"claude-sonnet-5-5","content":[],'
    '"usage":{"input_tokens":3,"output_tokens":2,"cache_read_input_tokens":10,"cache_creation_input_tokens":0}}}\n')


def hook_commands():
    """event -> the one shell-form command of the plugin's hook; the shape of hooks.json is checked on the way."""
    with open(os.path.join(REPO, "hooks", "hooks.json"), "rb") as f:
        doc = json.loads(f.read().decode("utf-8"))
    out = {}
    for event in ("SubagentStop", "Stop"):
        groups = doc["hooks"][event]
        handlers = [h for g in groups for h in g["hooks"]]
        if len(handlers) != 1:
            raise AssertionError("%s: expected exactly one handler, found %d" % (event, len(handlers)))
        h = handlers[0]
        if h.get("type") != "command" or "args" in h:
            raise AssertionError("%s: the handler must be shell-form (type command, no args)" % event)
        for key in ("async", "timeout", "statusMessage"):
            if key in h:
                raise AssertionError("%s: the handler must be synchronous and plain; found %r" % (event, key))
        out[event] = h["command"]
    return out


def find_git_bash():
    cands = []
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(var):
            cands.append(os.path.join(os.environ[var], "Git", "bin", "bash.exe"))
    if os.environ.get("LOCALAPPDATA"):
        cands.append(os.path.join(os.environ["LOCALAPPDATA"], "Programs", "Git", "bin", "bash.exe"))
    git = shutil.which("git")
    if git:
        cands.append(os.path.join(os.path.dirname(os.path.dirname(git)), "bin", "bash.exe"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def runners():
    """(name, function that turns a command text into an argv, root path form) for each way Claude Code may run a hook here."""
    out = []
    if WINDOWS:
        bash = find_git_bash()
        if bash:
            out.append(("git-bash", lambda cmd, b=bash: [b, "-c", cmd], "native"))
            out.append(("git-bash-slashes", lambda cmd, b=bash: [b, "-c", cmd], "slashes"))
        ps = shutil.which("powershell.exe")
        if ps:
            out.append(("powershell", lambda cmd, p=ps: [p, "-NoProfile", "-NonInteractive", "-Command", cmd], "native"))
    else:
        out.append(("sh", lambda cmd: ["sh", "-c", cmd], "native"))
        if shutil.which("bash"):
            out.append(("bash", lambda cmd: ["bash", "-c", cmd], "native"))
    return out


def runners_or_skip(tc):
    found = runners()
    if not found:
        msg = "no shell to run the hook command (Git Bash or powershell.exe missing)"
        if conf.ci():
            tc.fail(msg)
        tc.skipTest(msg)
    return found


def substituted(command, form):
    root = REPO.replace("\\", "/") if form == "slashes" else REPO
    return command.replace(ROOT_VAR, root)


class Box:
    """A sandbox: a claude dir, a home dir, a work dir and the transcripts."""

    def __init__(self, tc):
        self.root = tempfile.mkdtemp(prefix="spanharness-hook-")
        tc.addCleanup(shutil.rmtree, self.root, True)
        self.claude = os.path.join(self.root, "claude")
        self.home = os.path.join(self.root, "home")
        self.work = os.path.join(self.root, "work", "repo-a")
        self.transcripts = os.path.join(self.root, "transcripts")
        for d in (self.home, self.work, self.transcripts):
            os.makedirs(d)
        self.main = os.path.join(self.transcripts, "main.jsonl")
        with open(self.main, "wb") as f:
            f.write(MAIN_TRANSCRIPT.encode("ascii"))

    @property
    def lessons(self):
        return os.path.join(self.claude, "lessons")

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if k not in conf.CLEAN_ENV}
        env.update(CLAUDE_CONFIG_DIR=self.claude, HOME=self.home)
        env.update(extra)
        return env

    def agent_input(self, agent_id, role="coder"):
        path = os.path.join(self.transcripts, "agent-%s.jsonl" % agent_id)
        shutil.copyfile(AGENT_TRANSCRIPT, path)
        return json.dumps({"hook_event_name": "SubagentStop", "session_id": "sess1", "cwd": self.work, "agent_id": agent_id,
                           "agent_type": "spanharness:" + role, "effort": {"level": "high"}, "transcript_path": self.main,
                           "agent_transcript_path": path, "last_assistant_message": "not recorded"}).encode("utf-8")

    def stop_input(self):
        return json.dumps({"hook_event_name": "Stop", "session_id": "sess1", "cwd": self.work, "transcript_path": self.main,
                           "effort": {"level": "high"}, "stop_hook_active": False}).encode("utf-8")

    def records(self, lessons=None):
        """The decoded lines of every file under runs/ (the file names are checked)."""
        runs = os.path.join(lessons or self.lessons, "runs")
        if not os.path.isdir(runs):
            return []
        names = sorted(os.listdir(runs))
        out = []
        for n in names:
            if not re.match(r"^\d{4}-\d{2}\.jsonl$", n):
                raise AssertionError("unexpected file in runs/: " + n)
            with open(os.path.join(runs, n), "rb") as f:
                text = f.read().decode("utf-8")
            if text and not text.endswith("\n"):
                raise AssertionError(n + " does not end with a line break")
            out += [json.loads(line) for line in text.split("\n") if line]
        return out

    def kinds(self, lessons=None):
        return [r.get("kind") for r in self.records(lessons)]


def run(argv, data=b"", env=None, cwd=None):
    t0 = time.perf_counter()
    p = subprocess.run(argv, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=cwd, timeout=180)
    return p, time.perf_counter() - t0


def text(b):
    return b.decode("utf-8", "replace")


class HookCommands(unittest.TestCase):
    def test_hooks_json_shape(self):
        cmds = hook_commands()
        self.assertEqual(cmds["SubagentStop"], cmds["Stop"])
        self.assertEqual(
            cmds["Stop"],
            'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "${CLAUDE_PLUGIN_ROOT}/scripts/spanharness.ps1" record; '
            'sh "${CLAUDE_PLUGIN_ROOT}/scripts/spanharness.sh" record; exit 0')

    def test_each_event_records_exactly_once(self):
        cmds = hook_commands()
        for name, argv, form in runners_or_skip(self):
            with self.subTest(runner=name):
                box = Box(self)
                env = box.env()
                p, _ = run(argv(substituted(cmds["SubagentStop"], form)), box.agent_input("ag1"), env)
                self.assertEqual(p.returncode, 0, text(p.stderr))
                self.assertEqual(p.stdout, b"", "nothing may be printed on stdout")
                recs = box.records()
                self.assertEqual([r["kind"] for r in recs if r["kind"] != "harness"], ["agent"], recs)
                agent = [r for r in recs if r["kind"] == "agent"][0]
                self.assertEqual((agent["agent"], agent["agent_id"], agent["effort"], agent["turns"]), ("spanharness:coder", "ag1", "high", 2))
                self.assertLessEqual(box.kinds().count("harness"), 1)

                p, _ = run(argv(substituted(cmds["Stop"], form)), box.stop_input(), env)
                self.assertEqual(p.returncode, 0, text(p.stderr))
                self.assertEqual(p.stdout, b"")
                kinds = box.kinds()
                self.assertEqual(sorted(k for k in kinds if k != "harness"), ["agent", "turn"], kinds)
                self.assertLessEqual(kinds.count("harness"), 1)
                self.assertEqual(len(os.listdir(os.path.join(box.lessons, "runs"))), 1, "one file per month")

                # the same events again: nothing happened since, so nothing is added
                before = box.records()
                for event, data in (("SubagentStop", box.agent_input("ag1")), ("Stop", box.stop_input())):
                    p, _ = run(argv(substituted(cmds[event], form)), data, env)
                    self.assertEqual(p.returncode, 0)
                    self.assertEqual(p.stdout, b"")
                self.assertEqual(box.records(), before)
                self.assertFalse(os.path.exists(os.path.join(box.lessons, "errors.log")), "errors.log was written")

    def test_garbage_input_still_exits_0_silently(self):
        cmds = hook_commands()
        for name, argv, form in runners_or_skip(self):
            with self.subTest(runner=name):
                box = Box(self)
                for data in (b"", b"not json", b"[1,2]"):
                    p, _ = run(argv(substituted(cmds["Stop"], form)), data, box.env())
                    self.assertEqual(p.returncode, 0, text(p.stderr))
                    self.assertEqual(p.stdout, b"")
                self.assertEqual(box.records(), [])

    def test_opt_out(self):
        cmds = hook_commands()
        for name, argv, form in runners_or_skip(self):
            with self.subTest(runner=name):
                box = Box(self)
                p, _ = run(argv(substituted(cmds["SubagentStop"], form)), box.agent_input("ag1"), box.env(SPANHARNESS_RECORD="0"))
                self.assertEqual(p.returncode, 0)
                self.assertEqual(p.stdout, b"")
                self.assertFalse(os.path.exists(box.lessons))

    def test_default_folder_is_home_dot_claude(self):
        cmds = hook_commands()
        for name, argv, form in runners_or_skip(self):
            with self.subTest(runner=name):
                box = Box(self)
                env = box.env()
                del env["CLAUDE_CONFIG_DIR"]
                env["USERPROFILE"] = box.home
                p, _ = run(argv(substituted(cmds["SubagentStop"], form)), box.agent_input("ag1"), env)
                self.assertEqual(p.returncode, 0, text(p.stderr))
                self.assertEqual([k for k in box.kinds(os.path.join(box.home, ".claude", "lessons")) if k != "harness"], ["agent"])
                self.assertFalse(os.path.exists(box.claude))

    @unittest.skipIf(WINDOWS, "a `powershell` next to the shell is the Linux and macOS case being guarded")
    def test_a_powershell_on_posix_does_not_record_twice(self):
        exe = conf.find_pwsh()
        if not exe:
            if conf.ci():
                self.fail("pwsh not found")
            self.skipTest("pwsh not found")
        cmds = hook_commands()
        box = Box(self)
        shim = os.path.join(box.root, "shim")
        os.makedirs(shim)
        with open(os.path.join(shim, "powershell"), "w") as f:
            f.write('#!/bin/sh\nexec "%s" "$@"\n' % exe)
        os.chmod(os.path.join(shim, "powershell"), 0o755)
        env = conf.impl_env("ps1", box.env(PATH=shim + os.pathsep + os.environ.get("PATH", "")))
        for event, data in (("SubagentStop", box.agent_input("ag1")), ("Stop", box.stop_input())):
            p, _ = run(["sh", "-c", substituted(cmds[event], "native")], data, env)
            self.assertEqual(p.returncode, 0, text(p.stderr))
            self.assertEqual(p.stdout, b"")
        self.assertEqual(sorted(k for k in box.kinds() if k != "harness"), ["agent", "turn"])

    def test_latency_of_the_whole_hook_command(self):
        cmds = hook_commands()
        for name, argv, form in runners_or_skip(self):
            box = Box(self)
            env = box.env()
            times = []
            for i in range(6):
                p, dt = run(argv(substituted(cmds["SubagentStop"], form)), box.agent_input("lat%d" % i), env)
                self.assertEqual(p.returncode, 0, text(p.stderr))
                times.append(dt * 1000)
            self.assertEqual(box.kinds().count("agent"), 6)
            sys.stderr.write("\nhook latency [%s, %s]: first %.0f ms, then min %.0f / median %.0f / max %.0f ms (SubagentStop, full command)\n"
                             % (name, sys.platform, times[0], min(times[1:]), statistics.median(times[1:]), max(times[1:])))


# ----------------------------------------------------------------------------------------------
# the launcher
# ----------------------------------------------------------------------------------------------

def tool(name):
    path = shutil.which(name)
    if not path:
        raise unittest.SkipTest("%s is not available" % name)
    return path


def stub(path, body):
    with open(path, "w") as f:
        f.write("#!/bin/sh\n" + body)
    os.chmod(path, 0o755)


@unittest.skipIf(WINDOWS, "the POSIX branches; the Windows branch has its own tests below")
class LauncherPosix(unittest.TestCase):
    def setUp(self):
        self.sh = tool("sh")
        self.tmp = tempfile.mkdtemp(prefix="spanharness-launcher-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)

    def tools_only(self, *names):
        """A PATH folder with the named system tools (and nothing else) linked in."""
        for n in names:
            os.symlink(tool(n), os.path.join(self.bin, n))
        return self.bin

    def launch(self, args, path, data=b"", cwd=None, script=LAUNCHER, **env):
        e = {k: v for k, v in os.environ.items() if k not in conf.CLEAN_ENV}
        e["PATH"] = path
        e.update(env)
        return run([self.sh, script] + list(args), data, e, cwd)[0]

    def test_syntax_with_every_posix_shell(self):
        for shell in ("sh", "dash", "bash", "ksh", "zsh"):
            exe = shutil.which(shell)
            if not exe:
                continue
            p = subprocess.run([exe, "-n", LAUNCHER], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(p.returncode, 0, "%s -n: %s" % (shell, text(p.stderr)))

    def test_lint_passes_through_with_exit_code_and_output(self):
        path = os.environ.get("PATH", "")
        p = self.launch(["lint", "--root", REPO], path)
        self.assertEqual((p.returncode, p.stdout), (0, b""), text(p.stdout) + text(p.stderr))
        p = self.launch(["lint", "--root", self.tmp], path)           # no rules there
        self.assertEqual(p.returncode, 1)
        p = self.launch(["report", "--months", "0"], path)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(p.stdout, b"")

    def test_report_passes_through(self):
        box = Box(self)
        out = os.path.join(box.root, "r.md")
        p = self.launch(["report", out, "--lessons-dir", box.lessons], os.environ.get("PATH", ""), CLAUDE_CONFIG_DIR=box.claude, HOME=box.home)
        self.assertEqual(p.returncode, 0, text(p.stderr))
        self.assertTrue(os.path.isfile(out))
        self.assertEqual(os.path.basename(text(p.stdout).strip()), "r.md")

    def test_script_found_from_any_way_of_calling_it(self):
        path = os.environ.get("PATH", "")
        for cwd, script in ((SCRIPTS, "spanharness.sh"), (REPO, os.path.join("scripts", "spanharness.sh")), (self.tmp, LAUNCHER),
                            (os.path.join(REPO, "tests"), os.path.join("..", "scripts", "spanharness.sh"))):
            p = self.launch(["lint", "--root", REPO], path, cwd=cwd, script=script)
            self.assertEqual((p.returncode, p.stdout), (0, b""), "%s from %s: %s" % (script, cwd, text(p.stderr)))

    def test_folder_name_with_spaces(self):
        folder = os.path.join(self.tmp, "a folder", "scripts")
        os.makedirs(folder)
        for n in ("spanharness.sh", "spanharness.py"):
            shutil.copyfile(os.path.join(SCRIPTS, n), os.path.join(folder, n))
        p = self.launch(["lint", "--root", REPO], os.environ.get("PATH", ""), script=os.path.join(folder, "spanharness.sh"))
        self.assertEqual((p.returncode, p.stdout), (0, b""), text(p.stderr))

    def test_python_choice_and_arguments(self):
        path = self.tools_only("uname", "cat")
        log = os.path.join(self.tmp, "args.txt")
        reject = "case \"$1\" in -c) exit 1;; esac\nexit 9\n"
        accept = "case \"$1\" in -c) exit 0;; esac\nprintf '%%s\\n' \"$0\" \"$@\" > \"%s\"\ncat >/dev/null\nexit 7\n" % log
        # python3 is too old: python is used, with -I, the script next to the launcher, and the arguments untouched
        stub(os.path.join(self.bin, "python3"), reject)
        stub(os.path.join(self.bin, "python"), accept)
        p = self.launch(["report", "a b", "--months", "3"], path)
        self.assertEqual(p.returncode, 7, text(p.stderr))
        with open(log) as f:
            seen = f.read().split("\n")
        self.assertEqual(seen[0], os.path.join(self.bin, "python"))
        self.assertEqual(seen[1:6], ["-I", os.path.join(SCRIPTS, "spanharness.py"), "report", "a b", "--months"])
        # python3 is fine: it wins over python
        os.remove(log)
        stub(os.path.join(self.bin, "python3"), accept)
        stub(os.path.join(self.bin, "python"), "exit 8\n")
        p = self.launch(["lint"], path)
        self.assertEqual(p.returncode, 7)
        with open(log) as f:
            self.assertEqual(f.read().split("\n")[0], os.path.join(self.bin, "python3"))

    def test_no_usable_python(self):
        path = self.tools_only("uname", "cat")
        for names in ((), ("python3",), ("python3", "python")):
            for n in names:
                stub(os.path.join(self.bin, n), "case \"$1\" in -c) exit 1;; esac\necho ran >&2\nexit 9\n")
            p = self.launch(["record"], path, b"x" * 2000000)
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, b"", b""), names)
            p = self.launch(["report"], path)
            self.assertEqual(p.returncode, 1, names)
            self.assertEqual(p.stdout, b"")
            err = text(p.stderr)
            self.assertIn("3.8", err)
            self.assertEqual(len(err.strip().splitlines()), 1)

    def test_macos_python_stub_is_not_called(self):
        if not os.path.exists("/usr/bin/python3"):
            self.skipTest("/usr/bin/python3 does not exist")
        box = Box(self)
        stub(os.path.join(self.bin, "uname"), "echo Darwin\n")
        stub(os.path.join(self.bin, "xcode-select"), "exit 1\n")
        path = os.pathsep.join([self.bin, "/usr/bin", "/bin"])
        if shutil.which("python3", path=path) != "/usr/bin/python3":
            self.skipTest("python3 does not resolve to /usr/bin/python3 here")
        p = self.launch(["record"], path, box.agent_input("ag1"), CLAUDE_CONFIG_DIR=box.claude, HOME=box.home)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, b"", b""))
        self.assertFalse(os.path.exists(box.claude), "record ran")
        p = self.launch(["report"], path)
        self.assertEqual((p.returncode, p.stdout), (1, b""))
        self.assertEqual(len(text(p.stderr).strip().splitlines()), 1)
        # Command Line Tools are there: the stub is a real python3 and runs
        stub(os.path.join(self.bin, "xcode-select"), "exit 0\n")
        p = self.launch(["lint", "--root", REPO], path)
        self.assertEqual((p.returncode, p.stdout), (0, b""), text(p.stderr))
        p = self.launch(["record"], path, box.agent_input("ag1"), CLAUDE_CONFIG_DIR=box.claude, HOME=box.home)
        self.assertEqual((p.returncode, p.stdout), (0, b""))
        self.assertEqual([k for k in box.kinds() if k != "harness"], ["agent"])

    def test_windows_branch_with_a_fake_uname(self):
        box = Box(self)
        log = os.path.join(self.tmp, "ps-args.txt")
        stub(os.path.join(self.bin, "uname"), "echo MINGW64_NT-10.0-26100\n")
        stub(os.path.join(self.bin, "powershell.exe"), "printf '%%s\\n' \"$@\" > \"%s\"\nexit 5\n" % log)
        path = os.pathsep.join([self.bin, os.environ.get("PATH", "")])
        p = self.launch(["record"], path, box.agent_input("ag1"), CLAUDE_CONFIG_DIR=box.claude, HOME=box.home)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, b"", b""))
        self.assertFalse(os.path.exists(box.claude), "the shell script recorded on Windows")
        self.assertFalse(os.path.exists(log), "PowerShell was started for record")
        p = self.launch(["lint", "--root", "x y"], path)
        self.assertEqual(p.returncode, 5)
        with open(log) as f:
            self.assertEqual(f.read().split("\n")[:8], ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SCRIPTS + "/spanharness.ps1",
                                                        "lint", "--root", "x y"])


@unittest.skipUnless(WINDOWS, "Windows: the launcher in Git Bash hands over to PowerShell")
class LauncherWindows(unittest.TestCase):
    def bash(self, script_args, box=None):
        exe = find_git_bash()
        if not exe:
            if conf.ci():
                self.fail("Git Bash not found")
            self.skipTest("Git Bash not found")
        box = box or Box(self)
        cmd = 'sh "%s" %s' % (LAUNCHER, script_args)
        return run([exe, "-c", cmd], b'{"hook_event_name":"Stop"}', box.env()), box

    def test_record_does_nothing(self):
        (p, _), box = self.bash("record")
        self.assertEqual((p.returncode, p.stdout), (0, b""), text(p.stderr))
        self.assertFalse(os.path.exists(box.claude))

    def test_lint_goes_to_powershell(self):
        (p, _), _ = self.bash('lint --root "%s"' % REPO.replace("\\", "/"))
        self.assertEqual((p.returncode, p.stdout), (0, b""), text(p.stdout) + text(p.stderr))

    def test_report_goes_to_powershell(self):
        box = Box(self)
        out = os.path.join(box.root, "r.md").replace("\\", "/")
        (p, _), _ = self.bash('report "%s" --lessons-dir "%s"' % (out, box.lessons.replace("\\", "/")), box)
        self.assertEqual(p.returncode, 0, text(p.stderr))
        self.assertTrue(os.path.isfile(out))
        (p, _), _ = self.bash("report --months 0", box)
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
