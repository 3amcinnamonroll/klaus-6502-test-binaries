# Klaus 6502 test binaries

This repository builds reproducible NMOS and CMOS variants of Klaus Dormann's
6502 interrupt test. It keeps the GPL test source and generated binaries
separate from emulator repositories that consume the test.

## Build

Install the cc65 toolchain so `ca65` and `ld65` are on `PATH`, then run:

```sh
make build
```

The command stages both variants, verifies them, and replaces `artifacts/` only
after the complete build succeeds. A failed build leaves the last complete
artifact set in place.

Generated files:

- `artifacts/6502_interrupt_test_nmos.bin` (`D_clear=0`)
- `artifacts/6502_interrupt_test_cmos.bin` (`D_clear=1`)
- `artifacts/manifest.json`
- `artifacts/SHA256SUMS`

Run `make verify` to check sizes, entry point, interrupt vectors, source pins,
variant identity, and checksums. Run `make clean` to remove generated files.
After a tracked artifact set exists, `make build` followed by
`git diff --exit-code -- artifacts` checks byte-for-byte reproducibility with
the installed toolchain. The manifest records the CA65 and LD65 versions used.

The raw images are 64 KiB memory images. Begin execution at `$0400`. The test
uses `$BFFC` as its feedback port: bit 0 drives IRQ and bit 1 drives NMI. Both
lines are active high for this configuration. The manifest records each
variant's success self-loop so a consumer can distinguish it from failure
traps.

See [PROVENANCE.md](PROVENANCE.md) for pinned source origins and licensing.
