# Klaus 6502 test binaries

This repository builds 64 KiB interrupt and decimal-mode test images for
6502-family CPU harnesses.

## Build

Install cc65, then run:

```sh
make build
make verify
```

Run `make update` to import the two official opcode binaries from the pinned
Klaus revision and rebuild all four files in `bin/`.
`make clean` removes abandoned temporary state without deleting `bin/`.

Consumers should select an artifact, entry point, and success address from
`bin/manifest.json`. Pin the repository revision and verify the recorded
SHA-256.

## Interrupt test

`6502_65c02_interrupt_test.bin` starts its 6502 test at `$0400` and its
65C02 test at `$0404`. Its active-high feedback port is `$BFFC`: bit 0 drives
level-sensitive IRQ and bit 1 drives edge-sensitive NMI. Select an entry point;
the RESET vector leads to failure.

## Decimal test

`6502_65c02_65816_decimal_test.bin` has six entry points:

| Entry | CPU behavior | Operand coverage |
| --- | --- | --- |
| `$0200` | 6502 | all byte values |
| `$0204` | 6502 | valid BCD only |
| `$0208` | 65C02 | all byte values |
| `$020C` | 65C02 | valid BCD only |
| `$0210` | 65816 (8-bit accumulator) | all byte values |
| `$0214` | 65816 (8-bit accumulator) | valid BCD only |

The test uses `$0010-$0020` as scratch RAM and `$0021` as its mode byte. Run
the 65816 modes from a reset-like emulation-mode state. The test does not apply
to the NES 2A03 or 2A07, which do not implement decimal arithmetic.

See [PROVENANCE.md](PROVENANCE.md) for pinned source origins and the applicable
GPL, MIT, and public-domain licensing.
