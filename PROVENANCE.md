# Provenance

## Official opcode tests

The functional and extended-opcode binaries and corresponding sources come
from Klaus Dormann's GPL-3.0-or-later test suite:

- Official source: `Klaus2m5/6502_65C02_functional_tests`
- Official revision: `7954e2dbb49c469ea286070bf46cdd71aeb29e4b`
- Functional source: `bin/source/6502_functional_test.a65`
- Extended-opcode source: `bin/source/65C02_extended_opcodes_test.a65c`

## Interrupt test

Derived from Klaus Dormann's `6502_interrupt_test.a65` and its CA65 port:

- CA65 port source: `nkane/chippy`
- Port revision: `708af9b079b2f5e382684cc059d02afdfe6a6812`
- Port source file: `cpu/testdata/6502_interrupt_test.ca65`

This repository combines the NMOS and CMOS modes into one binary. The Klaus
tests remain GPL-3.0-or-later; the complete license is in `LICENSE`.

## Decimal test

Derived from Bruce Clark's public-domain decimal-mode test and its CA65 port:

- Tutorial and original source: `6502.org/tutorials/decimal_mode.html`
- CA65 port source: `micahcowan/bobbin`
- Port revision: `e331ff2a6a5f7095100ace911edbec5e363fca67`
- Port source file: `test/tests6502/decimal_test_common.inc`

This repository combines the CPU and operand-coverage modes into one binary.
Bobbin's CA65 port is MIT-licensed; its notice is in `LICENSE-Bobbin`.
