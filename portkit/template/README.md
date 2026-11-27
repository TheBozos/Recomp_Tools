<img src="docs/branding/@PREFIX@_banner.png" alt="@TITLE@, native PC port by The Bozos" width="100%">

<div align="center">

# @PROJECT@

**A native PC port of *@TITLE@* (@REGION@, `@SERIAL@`), made by statically recompiling the game's PlayStation 2 code to C++. Windows first; Linux later.**<br>
Built on [BozoEngine](https://github.com/TheBozos/BozoEngine), The Bozos' own toolchain: the game's EE code recompiled to C++, every library and kernel call it makes answered by native code. No PS2 hardware model at any level: no GS, VU, VIF/GIF, DMA, IOP or SPU2.

![Platform](https://img.shields.io/badge/platform-Windows%20(Linux%20later)-1b8cff)
![Compiler](https://img.shields.io/badge/compiler-GCC%20%7C%20Clang-1b8cff)
![Based on](https://img.shields.io/badge/based%20on-BozoEngine-17a35b)
![Status](https://img.shields.io/badge/status-starting-e0a100)

</div>

> [!IMPORTANT]
> No game files are included: no ELF, IRX modules, archives, audio streams, or code generated from them.
> You need **your own copy** of the @REGION_LONG@ release, PS2 ID **`@SERIAL@`**. The port is built against that
> disc's executable:
>
> | File | SHA-1 |
> |---|---|
> | `@ELFNAME@` | `@SHA1@` |

## Status

| Milestone | |
|---|:---:|
| Disc layout, executable sections and IOP modules mapped | ⏳ |
| Whole program recompiled by bozo-recomp | ⏳ |
| Library symbol map for the executable | ⏳ |
| Port build (`@PREFIX@-headless`, `@EXE_NAME@`) linked against BozoEngine | ⏳ |
| Boot, memory-card check, logos | ⏳ |
| Title screen and menus | ⏳ |
| Gameplay | ⏳ |
| Save states, memory-card saves | ⏳ |
| Linux build | ⏳ |

## Building

You need your own disc image. On Windows, from an MSYS2 UCRT64 shell with GCC, CMake and Ninja:

```bash
git clone --recurse-submodules https://github.com/TheBozos/@PROJECT@.git
cd @PROJECT@
scripts/extract_iso.sh "/path/to/your/disc.iso"   # the disc's files into game/ (checks the executable's SHA-1)
scripts/build_runtime.sh                           # builds @PREFIX@-headless and @EXE_NAME@
scripts/run.sh --frames 600                        # the headless runner
```

See [docs/RECOMP_NOTES.md](docs/RECOMP_NOTES.md) for how the port is made and what each stage found.

## Credits

Made by The Bozos (boubou666, Arzaroth) on [BozoEngine](https://github.com/TheBozos/BozoEngine). *@TITLE@* belongs to its
publisher and developer; this project contains none of their files.

## License

MIT, for the files in this repository (see [LICENSE](LICENSE)). The game is not included.
