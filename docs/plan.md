# Requirements

## Circuit wiring role (2026-11-13)

1. Circuit wiring work goes to an agent that runs on `fable`.
2. It is a new role, not an extension of `modeler` or `designer`.
3. Every circuit design that will be wired and powered goes to `deep-reviewer` before it is wired, not only designs that affect purchases.
4. user: the role is for circuit board (PCB) design, not only wiring between modules.
5. user: it goes all the way to files ready to order: schematic → footprints → board layout (placement · routing) → DRC → Gerber · BOM · placement (CPL) files.
6. user: the tool is KiCad (the agent works through its text files and `kicad-cli` / scripts, not the GUI).
