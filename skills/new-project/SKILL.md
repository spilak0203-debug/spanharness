---
name: new-project
description: Use when starting a new project in an empty folder, or when the user proposes creating a new project. Settles the requirements by asking questions before any code or design and saves them as docs/plan.md, then goes research → design → implementation.
---

# Starting a new project

Settle the requirements before getting into code or design.

1. Restate the requirements the user described roughly in one or two lines and show them.
2. Ask about what you don't know. Three or four questions at a time, most important first. For questions with choices, give options along with a recommendation (AskUserQuestion).
   - What to cover: purpose and users · must-have features and ones that can be dropped · where it runs (desktop · web · phone) · technology and tools · data storage · external services and accounts · look and feel · public or not · the criteria for calling it done.
3. If the user says "do as you like", decide yourself and leave a one-line reason. If they dictate a tool or an approach, follow it as is.
4. When answers come in, ask again about any new questions. Repeat 2-3 until no question is left. A place filled in by guesswork also counts as a question.
5. When everything is settled, show it on one page: what was decided · what you decided on their behalf · what won't be done · the criteria for calling it done. If the user OKs it, save it as `docs/plan.md`. In the document write only the decisions and the reasons, not who decided.
6. Move on to design. Research first (`docs/research.md`), and for a large design, hand `spanharness:architect` `docs/plan.md` and `docs/research.md` and have it do the plan only. Show the design to the user, and hand off implementation after getting an OK.
7. Once the build · test method is decided, write it in the project folder's CLAUDE.md. If it is a git repository, put `CLAUDE.md` in `.git/info/exclude` so it isn't tracked. If a parent folder has a CLAUDE.md, add one line to its table of contents.
