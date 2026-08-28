# Provenance

The binaries in this repository derive from Klaus Dormann's GPL-3.0-or-later
6502 interrupt test.

- Official source: `Klaus2m5/6502_65C02_functional_tests`
- Official revision: `7954e2dbb49c469ea286070bf46cdd71aeb29e4b`
- Official source file: `6502_interrupt_test.a65`
- CA65 port source: `nkane/chippy`
- Port revision: `708af9b079b2f5e382684cc059d02afdfe6a6812`
- Port source file: `cpu/testdata/6502_interrupt_test.ca65`

The CA65 port retains Klaus Dormann's copyright and GPL notice. On 2026-08-28,
this repository modified the port by adding a build-time configuration seam
around `D_clear` so the same source can produce NMOS (`D_clear=0`) and CMOS
(`D_clear=1`) images. The linker configuration comes from the pinned port
revision without modification.

The complete GPL version 3 text is in `LICENSE`. The source is offered under
GPL-3.0-or-later, matching the original source notice.
