#!/usr/bin/env python3
"""Build and verify the pinned 6502-family test binaries."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Iterator
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent.parent
INTERRUPT_SOURCE = ROOT / "src" / "6502_interrupt_test.ca65"
INTERRUPT_CONFIG = ROOT / "src" / "interrupt_test.cfg"
DECIMAL_SOURCE = ROOT / "src" / "6502_decimal_test.ca65"
DECIMAL_CONFIG = ROOT / "src" / "decimal_test.cfg"
BIN = ROOT / "bin"
KLAUS_SOURCE = BIN / "source"
BIN_BACKUP = ROOT / ".bin-backup"
LOCK = ROOT / ".artifacts.lock"
UPSTREAM_REVISION = "7954e2dbb49c469ea286070bf46cdd71aeb29e4b"
PORT_REVISION = "708af9b079b2f5e382684cc059d02afdfe6a6812"
DECIMAL_PORT_REVISION = "e331ff2a6a5f7095100ace911edbec5e363fca67"
INTERRUPT_LABELS = {
    "TEST_MODE": 0x0010,
    "TEST_6502": 0x0400,
    "TEST_65C02": 0x0404,
    "SUCCESS_65C02": 0x0737,
    "SUCCESS_6502": 0x073A,
}
DECIMAL_LABELS = {
    "ERROR": 0x001B,
    "TEST_MODE": 0x0021,
    "TEST_6502_ALL": 0x0200,
    "TEST_6502_VALID": 0x0204,
    "TEST_65C02_ALL": 0x0208,
    "TEST_65C02_VALID": 0x020C,
    "TEST_65816_ALL": 0x0210,
    "TEST_65816_VALID": 0x0214,
    "FAILURE": 0x029B,
    "SUCCESS_6502_ALL": 0x029E,
    "SUCCESS_6502_VALID": 0x02A1,
    "SUCCESS_65C02_ALL": 0x02A4,
    "SUCCESS_65C02_VALID": 0x02A7,
    "SUCCESS_65816_ALL": 0x02AA,
    "SUCCESS_65816_VALID": 0x02AD,
}
FEEDBACK = {
    "port": "0xBFFC",
    "irq": {"bit": 0, "asserted": 1, "sampling": "level"},
    "nmi": {"bit": 1, "asserted": 1, "sampling": "rising-edge"},
}
OFFICIAL_BINARIES = (
    (
        "functional",
        "6502_functional_test.bin",
        0x0400,
        0x3469,
        "fa12bfc761e6f9057e4cc01a665a7b800ff01ae91f598af1e39a1201d01953fd",
        "6502_functional_test.a65",
        "f2665bd02288866c2b210b908e3f387926b4c9f0e0af5ad5513c474361ad1265",
    ),
    (
        "extended_65c02",
        "65C02_extended_opcodes_test.bin",
        0x0400,
        0x24F1,
        "10a2a07fa240666fa610c46accebe8d42b1000feef3aae619da15a8d152869b2",
        "65C02_extended_opcodes_test.a65c",
        "72b1f57dc8f22f418ac2e23fc57c43821da84060679a7fcc3302071aa2f76736",
    ),
)


def recover_publications() -> None:
    if BIN_BACKUP.exists():
        if BIN.exists():
            shutil.rmtree(BIN_BACKUP)
        else:
            os.replace(BIN_BACKUP, BIN)


@contextmanager
def artifact_lock() -> Iterator[None]:
    with LOCK.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SystemExit("error: another artifact build, verify, or clean is running") from error
        recover_publications()
        yield


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_interrupt_binary(path: Path, labels: dict[str, int]) -> dict:
    data = path.read_bytes()
    if len(data) != 65536:
        raise ValueError(f"{path.name}: expected 65536 bytes, found {len(data)}")
    nmi_vector = int.from_bytes(data[0xFFFA:0xFFFC], "little")
    reset_vector = int.from_bytes(data[0xFFFC:0xFFFE], "little")
    irq_vector = int.from_bytes(data[0xFFFE:0x10000], "little")
    for label, address in (("NMI", nmi_vector), ("RESET", reset_vector), ("IRQ", irq_vector)):
        if not 0x0400 <= address < 0x8000:
            raise ValueError(f"{path.name}: {label} vector ${address:04X} is outside test code")

    modes = []
    for identifier, cpu, entry_label, success_label in (
        ("6502", "6502", "TEST_6502", "SUCCESS_6502"),
        ("65c02", "65c02", "TEST_65C02", "SUCCESS_65C02"),
    ):
        entry_point = labels[entry_label]
        success_pc = labels[success_label]
        expected_loop = bytes((0x4C, success_pc & 0xFF, success_pc >> 8))
        if data[success_pc:success_pc + 3] != expected_loop:
            raise ValueError(f"{path.name}: missing {identifier} success loop")
        modes.append({
            "id": identifier,
            "cpu": cpu,
            "entry_point": f"0x{entry_point:04X}",
            "success_pc": f"0x{success_pc:04X}",
        })
    return {
        "file": path.name,
        "bytes": len(data),
        "sha256": sha256(path),
        "mode_address": f"0x{labels['TEST_MODE']:04X}",
        "nmi_vector": f"0x{nmi_vector:04X}",
        "reset_vector": f"0x{reset_vector:04X}",
        "irq_vector": f"0x{irq_vector:04X}",
        "modes": modes,
    }


def assemble_interrupt(stage: Path) -> dict:
    object_path = stage / "interrupt.o"
    labels_path = stage / "interrupt.lbl"
    binary_path = stage / "6502_65c02_interrupt_test.bin"
    subprocess.run(["ca65", str(INTERRUPT_SOURCE), "-o", str(object_path)], check=True)
    subprocess.run(
        [
            "ld65",
            str(object_path),
            "-o",
            str(binary_path),
            "-C",
            str(INTERRUPT_CONFIG),
            "-Ln",
            str(labels_path),
        ],
        check=True,
    )
    labels = read_labels(labels_path)
    if labels != INTERRUPT_LABELS:
        raise ValueError("interrupt-test labels differ from the published interface")
    result = inspect_interrupt_binary(binary_path, labels)
    object_path.unlink()
    labels_path.unlink()
    return result


def read_labels(path: Path) -> dict[str, int]:
    labels = {}
    for line in path.read_text(encoding="ascii").splitlines():
        _, address, name = line.split()
        labels[name.removeprefix(".")] = int(address, 16)
    return labels


def inspect_decimal_binary(path: Path, labels: dict[str, int]) -> dict:
    data = path.read_bytes()
    if len(data) != 65536:
        raise ValueError(f"{path.name}: expected 65536 bytes, found {len(data)}")

    modes = []
    for identifier, cpu, coverage, entry_label, success_label in (
        ("6502-all", "6502", "all-byte-values", "TEST_6502_ALL", "SUCCESS_6502_ALL"),
        ("6502-valid", "6502", "valid-bcd-only", "TEST_6502_VALID", "SUCCESS_6502_VALID"),
        ("65c02-all", "65c02", "all-byte-values", "TEST_65C02_ALL", "SUCCESS_65C02_ALL"),
        ("65c02-valid", "65c02", "valid-bcd-only", "TEST_65C02_VALID", "SUCCESS_65C02_VALID"),
        ("65816-all", "65816", "all-byte-values", "TEST_65816_ALL", "SUCCESS_65816_ALL"),
        ("65816-valid", "65816", "valid-bcd-only", "TEST_65816_VALID", "SUCCESS_65816_VALID"),
    ):
        entry_point = labels[entry_label]
        success_pc = labels[success_label]
        expected_loop = bytes((0x4C, success_pc & 0xFF, success_pc >> 8))
        if data[success_pc:success_pc + 3] != expected_loop:
            raise ValueError(f"{path.name}: missing {identifier} success loop")
        modes.append({
            "id": identifier,
            "cpu": cpu,
            "coverage": coverage,
            "entry_point": f"0x{entry_point:04X}",
            "success_pc": f"0x{success_pc:04X}",
        })

    reset_vector = int.from_bytes(data[0xFFFC:0xFFFE], "little")
    if reset_vector != labels["TEST_6502_ALL"]:
        raise ValueError(f"{path.name}: reset vector does not select 6502-all")
    return {
        "file": path.name,
        "bytes": len(data),
        "sha256": sha256(path),
        "workspace": {"start": "0x0010", "bytes": 17},
        "mode_address": f"0x{labels['TEST_MODE']:04X}",
        "error_address": f"0x{labels['ERROR']:04X}",
        "failure_pc": f"0x{labels['FAILURE']:04X}",
        "modes": modes,
    }


def assemble_decimal(stage: Path) -> dict:
    object_path = stage / "decimal.o"
    labels_path = stage / "decimal.lbl"
    binary_path = stage / "6502_65c02_65816_decimal_test.bin"
    subprocess.run(["ca65", str(DECIMAL_SOURCE), "-o", str(object_path)], check=True)
    subprocess.run(
        [
            "ld65",
            str(object_path),
            "-o",
            str(binary_path),
            "-C",
            str(DECIMAL_CONFIG),
            "-Ln",
            str(labels_path),
        ],
        check=True,
    )
    labels = read_labels(labels_path)
    if labels != DECIMAL_LABELS:
        raise ValueError("decimal-test labels differ from the published interface")
    result = inspect_decimal_binary(binary_path, labels)
    object_path.unlink()
    labels_path.unlink()
    return result


def inspect_official_binary(
    path: Path, entry_point: int, success_pc: int, expected_sha256: str
) -> dict:
    if path.stat().st_size != 65536:
        raise ValueError(f"{path.name}: expected 65536 bytes")
    data = path.read_bytes()
    expected_loop = bytes((0x4C, success_pc & 0xFF, success_pc >> 8))
    if data[success_pc:success_pc + 3] != expected_loop:
        raise ValueError(f"{path.name}: missing success loop")
    actual_sha256 = sha256(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(f"{path.name}: checksum differs from the pinned official binary")
    return {
        "file": path.name,
        "bytes": 65536,
        "sha256": actual_sha256,
        "entry_point": f"0x{entry_point:04X}",
        "success_pc": f"0x{success_pc:04X}",
    }


def official_source(filename: str, expected_sha256: str, source_directory: Path) -> dict:
    path = source_directory / filename
    if sha256(path) != expected_sha256:
        raise ValueError(f"{filename}: checksum differs from the pinned official source")
    return {"file": f"bin/source/{filename}", "sha256": expected_sha256}


def write_metadata(
    stage: Path, interrupt: dict, decimal: dict, source_directory: Path
) -> None:
    official = [
        inspect_official_binary(stage / name, entry_point, success_pc, binary_sha256)
        for _, name, entry_point, success_pc, binary_sha256, _, _ in OFFICIAL_BINARIES
    ]
    sources = [
        official_source(source_name, source_sha256, source_directory)
        for _, _, _, _, _, source_name, source_sha256 in OFFICIAL_BINARIES
    ]
    manifest = {
        "schema": 3,
        "official_upstream_revision": UPSTREAM_REVISION,
        "tests": {
            "functional": {"source": sources[0], "artifact": official[0]},
            "extended_65c02": {"source": sources[1], "artifact": official[1]},
            "interrupt": {
                "ca65_port_revision": PORT_REVISION,
                "source_sha256": sha256(INTERRUPT_SOURCE),
                "linker_config_sha256": sha256(INTERRUPT_CONFIG),
                "feedback": FEEDBACK,
                "artifact": interrupt,
            },
            "decimal": {
                "source_author": "Bruce Clark",
                "source_license": "public-domain",
                "ca65_port_revision": DECIMAL_PORT_REVISION,
                "source_sha256": sha256(DECIMAL_SOURCE),
                "linker_config_sha256": sha256(DECIMAL_CONFIG),
                "artifact": decimal,
            },
        },
    }
    (stage / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    items = [*official, interrupt, decimal]
    sums = "".join(f"{item['sha256']}  {item['file']}\n" for item in items)
    (stage / "SHA256SUMS").write_text(sums, encoding="ascii")


def verify_release(directory: Path, source_directory: Path = KLAUS_SOURCE) -> None:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="ascii"))
    expected_fields = {
        "schema": 3,
        "official_upstream_revision": UPSTREAM_REVISION,
    }
    for field, expected in expected_fields.items():
        if manifest.get(field) != expected:
            raise ValueError(f"manifest {field} is stale")

    official = []
    for key, name, entry_point, success_pc, binary_sha256, source_name, source_sha256 in OFFICIAL_BINARIES:
        entry = manifest.get("tests", {}).get(key, {})
        source = official_source(source_name, source_sha256, source_directory)
        if entry.get("source") != source:
            raise ValueError(f"{key} source metadata is stale")
        artifact = inspect_official_binary(
            directory / name, entry_point, success_pc, binary_sha256
        )
        if entry.get("artifact") != artifact:
            raise ValueError(f"{key} manifest does not describe the current binary")
        official.append(artifact)

    interrupt_manifest = manifest.get("tests", {}).get("interrupt", {})
    expected_interrupt = {
        "ca65_port_revision": PORT_REVISION,
        "source_sha256": sha256(INTERRUPT_SOURCE),
        "linker_config_sha256": sha256(INTERRUPT_CONFIG),
        "feedback": FEEDBACK,
    }
    for field, expected in expected_interrupt.items():
        if interrupt_manifest.get(field) != expected:
            raise ValueError(f"interrupt manifest {field} is stale")
    interrupt = inspect_interrupt_binary(
        directory / "6502_65c02_interrupt_test.bin", INTERRUPT_LABELS
    )
    if interrupt_manifest.get("artifact") != interrupt:
        raise ValueError("interrupt manifest does not describe the current binary")

    decimal_manifest = manifest.get("tests", {}).get("decimal", {})
    expected_decimal = {
        "source_author": "Bruce Clark",
        "source_license": "public-domain",
        "ca65_port_revision": DECIMAL_PORT_REVISION,
        "source_sha256": sha256(DECIMAL_SOURCE),
        "linker_config_sha256": sha256(DECIMAL_CONFIG),
    }
    for field, expected in expected_decimal.items():
        if decimal_manifest.get(field) != expected:
            raise ValueError(f"decimal manifest {field} is stale")
    decimal = inspect_decimal_binary(directory / "6502_65c02_65816_decimal_test.bin", DECIMAL_LABELS)
    if decimal_manifest.get("artifact") != decimal:
        raise ValueError("decimal manifest does not describe the current binary")

    items = [*official, interrupt, decimal]
    expected_sums = "".join(f"{item['sha256']}  {item['file']}\n" for item in items)
    if (directory / "SHA256SUMS").read_text(encoding="ascii") != expected_sums:
        raise ValueError("SHA256SUMS is stale")


def verify() -> None:
    with artifact_lock():
        verify_release(BIN)
        print(f"verified 4 binaries in {BIN}")


def publish_directory(stage: Path, destination: Path, backup: Path) -> None:
    if backup.exists():
        if destination.exists():
            shutil.rmtree(backup)
        else:
            os.replace(backup, destination)
    if destination.exists():
        os.replace(destination, backup)
    try:
        os.replace(stage, destination)
    except BaseException:
        if backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def build_with_official(official_directory: Path) -> None:
    stage = Path(tempfile.mkdtemp(prefix=".bin-stage-", dir=ROOT))
    try:
        for _, name, _, _, _, _, _ in OFFICIAL_BINARIES:
            source = official_directory / name
            if not source.exists():
                raise ValueError(f"{source} is missing; run 'make update'")
            shutil.copyfile(source, stage / name)
        source_directory = official_directory / "source"
        shutil.copytree(source_directory, stage / "source")
        interrupt = assemble_interrupt(stage)
        decimal = assemble_decimal(stage)
        write_metadata(stage, interrupt, decimal, source_directory)
        verify_release(stage, source_directory)
        publish_directory(stage, BIN, BIN_BACKUP)
        verify_release(BIN, source_directory)
        print(f"built 4 binaries in {BIN}")
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def build() -> None:
    with artifact_lock():
        build_with_official(BIN)


def update() -> None:
    with artifact_lock():
        stage = Path(tempfile.mkdtemp(prefix=".update-stage-", dir=ROOT))
        try:
            source_directory = stage / "source"
            source_directory.mkdir()
            for _, name, entry_point, success_pc, binary_sha256, source_name, source_sha256 in OFFICIAL_BINARIES:
                url = (
                    "https://raw.githubusercontent.com/"
                    f"Klaus2m5/6502_65C02_functional_tests/{UPSTREAM_REVISION}/bin_files/{name}"
                )
                with urlopen(url) as response, (stage / name).open("wb") as output:
                    shutil.copyfileobj(response, output)
                inspect_official_binary(
                    stage / name, entry_point, success_pc, binary_sha256
                )
                source_url = (
                    "https://raw.githubusercontent.com/"
                    f"Klaus2m5/6502_65C02_functional_tests/{UPSTREAM_REVISION}/{source_name}"
                )
                with urlopen(source_url) as response, (source_directory / source_name).open("wb") as output:
                    shutil.copyfileobj(response, output)
                official_source(source_name, source_sha256, source_directory)
            build_with_official(stage)
        finally:
            shutil.rmtree(stage, ignore_errors=True)


def clean() -> None:
    with artifact_lock():
        for pattern in (
            ".bin-stage-*",
            ".update-stage-*",
            ".bin-backup",
        ):
            for stage in ROOT.glob(pattern):
                if stage.is_dir():
                    shutil.rmtree(stage)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "update", "verify", "clean"))
    args = parser.parse_args()
    if args.action == "build":
        build()
    elif args.action == "update":
        update()
    elif args.action == "verify":
        verify()
    else:
        clean()


if __name__ == "__main__":
    main()
