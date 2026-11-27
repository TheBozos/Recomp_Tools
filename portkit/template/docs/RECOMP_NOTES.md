# @PROJECT@: notes

How the port of *@TITLE@* (@REGION@, `@SERIAL@`) is made, stage by stage, and what each stage found. Written as the work goes.

## The disc

- Serial `@SERIAL@`, executable `@ELFNAME@`, SHA-1 `@SHA1@`.
- Layout, modules, the executable's sections and what is stripped: _to fill in_.

## Stages

1. Extract the disc (`scripts/extract_iso.sh`), check the executable.
2. Symbol map (`scripts/symbols.sh <reference.elf>...`): library names matched from other games' executables, then read by hand.
3. Recompile with bozo-recomp; unresolved jumps and code inside data are listed and handled.
4. Runtime: answer each kernel and library call the game makes; first frame, then the title, menus, gameplay.
5. Native drawing and sound, movies, save states, memory cards.
