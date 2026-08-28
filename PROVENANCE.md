# Provenance

The interrupt binaries in this repository derive from Klaus Dormann's
GPL-3.0-or-later 6502 interrupt test.

- Official source: `Klaus2m5/6502_65C02_functional_tests`
- Official revision: `7954e2dbb49c469ea286070bf46cdd71aeb29e4b`
- Official source file: `6502_interrupt_test.a65`
- CA65 port source: `nkane/chippy`
- Port revision: `708af9b079b2f5e382684cc059d02afdfe6a6812`
- Port source file: `cpu/testdata/6502_interrupt_test.ca65`

The CA65 port retains Klaus Dormann's copyright and GPL notice. On 2026-08-28,
this repository modified the port by adding runtime entry points for NMOS and
CMOS decimal-flag behavior. Both paths now share one image. The linker
configuration comes from the pinned port revision without modification.

The complete GPL version 3 text is in `LICENSE`. The source is offered under
GPL-3.0-or-later, matching the original source notice.

The decimal binary derives from Bruce Clark's public-domain decimal-mode test.

- Tutorial and original source: `6502.org/tutorials/decimal_mode.html`
- CA65 port source: `micahcowan/bobbin`
- Port revision: `e331ff2a6a5f7095100ace911edbec5e363fca67`
- Port source file: `test/tests6502/decimal_test_common.inc`

The CA65 port is covered by Bobbin's MIT license and copyright notice, included
in `LICENSE-Bobbin`. Bruce Clark's underlying decimal-test source is public
domain.

On 2026-08-28, this repository modified the CA65 port to combine the 6502,
65C02, and 65816 predictions and valid-only and all-byte operand sets into one
runtime-selectable image. It also moved scratch storage from `$0000-$0010` to
`$0010-$0020`, added a mode byte at `$0021`, and added distinct success loops.
The source retains Bruce Clark's public-domain notice.
