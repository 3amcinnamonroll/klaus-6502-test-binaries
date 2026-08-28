# Klaus 6502 test binaries

This repository builds verified 6502-family interrupt and decimal-mode test
binaries. It keeps the test sources and generated binaries separate from
emulator repositories that consume them.

## Build

Install the cc65 toolchain so `ca65` and `ld65` are on `PATH`, then run:

```sh
make build
```

The command stages and verifies all binaries, stores the complete result in a
content-addressed release directory, then atomically updates
`artifacts/current.json`. A failed build leaves the current pointer unchanged.
Artifact commands refuse to run concurrently. This workflow targets macOS and
Linux.

Generated files:

- `artifacts/current.json`
- `artifacts/releases/<id>/6502_65c02_interrupt_test.bin`
- `artifacts/releases/<id>/6502_65c02_65816_decimal_test.bin`
- `artifacts/releases/<id>/manifest.json`
- `artifacts/releases/<id>/SHA256SUMS`

Run `make verify` to check sizes, entry points, interrupt vectors, source pins,
variant identity, and checksums. Run `make clean` to remove generated files.
After a tracked artifact set exists, `make build` followed by
`git diff --exit-code -- artifacts` checks whether the installed toolchain
repeats the tracked result. The cc65 toolchain is not version-pinned here.

The raw images are 64 KiB memory images. The interrupt image starts its 6502
test at `$0400` and its 65C02 test at `$0404`. Each entry records the expected
decimal-flag behavior before entering the shared test. The image uses `$BFFC`
as a feedback port: bit 0 drives level-sensitive IRQ and bit 1 drives
edge-sensitive NMI. Both lines are active high for this configuration. The
RESET vector intentionally remains a failure trap, so a harness must select an
entry point rather than resetting into the test.

The decimal image has six entry points in one binary:

| Entry | CPU behavior | Operand coverage |
| --- | --- | --- |
| `$0200` | 6502 | all byte values |
| `$0204` | 6502 | valid BCD only |
| `$0208` | 65C02 | all byte values |
| `$020C` | 65C02 | valid BCD only |
| `$0210` | 65816 (8-bit accumulator) | all byte values |
| `$0214` | 65816 (8-bit accumulator) | valid BCD only |

It uses `$0010-$0020` as scratch RAM and `$0021` as its mode byte. This avoids
the `$0000-$0001` processor-port registers in 6510 and 8502 systems. The image
uses only instructions shared by the 6502, 65C02, and 65C816. The selected
entry point chooses the expected decimal arithmetic and flag behavior at
runtime. The manifest records the mode-specific success loops and the common
failure loop.

The 6502 modes are intended for NMOS-compatible cores such as the 6502, 6510,
8502, and Atari SALLY. The 65C02 modes cover CMOS-compatible cores. The 65816
modes account for that processor's distinct invalid-BCD subtraction behavior;
run them from a reset-like emulation-mode state. A machine or emulator still
needs writable RAM at the documented workspace and code addresses. The 64 KiB
image is a CPU-harness artifact, not a directly bootable image for every
machine in this list. The NES 2A03 and 2A07 do not implement decimal
arithmetic, so this decimal test is not applicable to them.

See [PROVENANCE.md](PROVENANCE.md) for pinned source origins and the applicable
GPL, MIT, and public-domain licensing.
