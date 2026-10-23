# Research: sources and platform facts

## References

- Plugins reference (manifest, component folders, `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`, agent frontmatter limits, validate): https://code.claude.com/docs/en/plugins-reference
- Marketplaces (`marketplace.json`, relative `source`, install and update, local-directory marketplaces): https://code.claude.com/docs/en/plugin-marketplaces and https://code.claude.com/docs/en/plugins/marketplace-reference
- Hooks (shell form vs exec form `args`, `shell` field, Windows behaviour, `async`, exit codes, SubagentStop/Stop input fields): https://code.claude.com/docs/en/hooks
- Subagents (frontmatter fields, `skills` preload, missing skill skipped, namespacing, precedence, `isolation: worktree`, file watcher): https://code.claude.com/docs/en/sub-agents
- Output styles (`keep-coding-instructions`, `force-for-plugin`, `outputStyle` precedence, read at startup): https://code.claude.com/docs/en/output-styles
- Standard library behaviour relied on: Python `decimal.ROUND_HALF_UP` (https://docs.python.org/3/library/decimal.html), .NET `MidpointRounding.AwayFromZero` (https://learn.microsoft.com/dotnet/api/system.midpointrounding), and `JavaScriptSerializer.MaxJsonLength`, which defaults to 2097152 and is what makes `ConvertFrom-Json` in Windows PowerShell 5.1 fail on large input (https://learn.microsoft.com/dotnet/api/system.web.script.serialization.javascriptserializer.maxjsonlength).
- Where spanharness differs from the docs: the docs suggest `${CLAUDE_PLUGIN_DATA}` for persistent data, and spanharness does not use it. `force-for-plugin` is available, and spanharness does not use it.

## Platform facts (Claude Code 2.1.308)

Observed on Linux with Claude Code 2.1.308.

1. `${CLAUDE_PLUGIN_ROOT}` is substituted textually in exec-form `args` and in shell-form `command`, and exported as an env var to the hook process.
2. A handler whose command does not exist is silent in `-p` output. For an async handler it is not even shown in `--debug`; for a sync handler `--debug` shows a spawn error. Other handlers still run with full stdin.
   Async Stop handlers were sometimes `cancelled` at process exit and never ran (1 of 4 runs). Therefore spanharness uses one synchronous shell-form handler per event, with no `async`: `powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "${CLAUDE_PLUGIN_ROOT}/scripts/spanharness.ps1" record; sh "${CLAUDE_PLUGIN_ROOT}/scripts/spanharness.sh" record; exit 0`. `record` must be fast and always exit 0. On Linux `powershell` is missing, so `sh` gets stdin.
3. SubagentStop `agent_type` is `spanharness:<name>` (namespaced). SubagentStop keys: `session_id`, `transcript_path` (the parent's), `cwd`, `scratchpad_dir`, `prompt_id`, `permission_mode`, `agent_id`, `agent_type`, `effort` (object, e.g. `{"level":"low"}`), `hook_event_name`, `stop_hook_active`, `agent_transcript_path` (the subagent's own, `.../<session>/subagents/agent-<id>.jsonl`), `last_assistant_message`, `background_tasks`, `session_crons`. Stop has the same keys minus `agent_id`, `agent_type` and `agent_transcript_path`.
4. The style value is `spanharness:orchestrator`. The bare name `orchestrator` does not select it.
5. Marketplace `source: "./"` works (`validate --strict`, add, install, runtime).
6. A missing preloaded skill (for example `ponytail`): the agent starts and only a WARN appears in the debug log. A user skill at `~/.claude/skills/ponytail` is preloaded.
7. `PowerShell` in `tools:` on Linux: no warning, the agent loads.
8. `${CLAUDE_PLUGIN_ROOT}` is substituted in agent bodies and `SKILL.md`, but not in output-style text. The orchestrator style must not rely on `${CLAUDE_PLUGIN_ROOT}`.
9. `validate --strict` does not check agent frontmatter values (only a missing description) and does not inspect agents or skills unless pointed at `<dir>/agents`. The plugin's own `lint` is the real check.
10. A directory marketplace with `source: "./"` loads the plugin in place (`${CLAUDE_PLUGIN_ROOT}` is the source dir), although `installed_plugins.json` `installPath` shows a cache copy. Apply mode on a local clone therefore works.
11. `validate`, `marketplace add` and `install` work without login (with a sandbox `CLAUDE_CONFIG_DIR`).
12. `validate --strict` needs `author` in `plugin.json` and `description` in `marketplace.json`. README, LICENSE and icon only matter with `--profile directory`.
