# Requirements

## Circuit wiring role (2026-11-13)

1. Circuit wiring work goes to an agent that runs on `fable`.
2. It is a new role, not an extension of `modeler` or `designer`.
3. Every circuit design that will be wired and powered goes to `deep-reviewer` before it is wired, not only designs that affect purchases.
4. user: the role is for circuit board (PCB) design, not only wiring between modules.
5. user: it goes all the way to files ready to order: schematic → footprints → board layout (placement · routing) → DRC → Gerber · BOM · placement (CPL) files.
6. user: the tool is KiCad (the agent works through its text files and `kicad-cli` / scripts, not the GUI).

## Comments and review (2026-11-13)

1. user: coder comments must not steer the reviewer; review should rest on the code.
2. Comments are not banned: coder writes only the why the code cannot show, in one line, and no comments that restate what the code does.
3. user: compare the change against the current roles with an A/B run before trusting it.
4. A/B 2026-11-13 (reviewer, 5 tasks × 3 runs): adding "treat comments and the author's report as claims to check" to reviewer was inconclusive (B won 2 of 5 tasks, A won none; both arms caught every planted misleading-comment defect). The sentence was reverted; reviewer's checklist already flags a comment that differs from the code.
5. user: reviewer does not write comments; it stays read-only. Wrong or missing comments are reported as findings and coder fixes them.
