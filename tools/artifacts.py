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


ROOT = Path(__file__).resolve().parent.parent
INTERRUPT_SOURCE = ROOT / "src" / "6502_interrupt_test.ca65"
INTERRUPT_CONFIG = ROOT / "src" / "interrupt_test.cfg"
DECIMAL_SOURCE = ROOT / "src" / "6502_decimal_test.ca65"
DECIMAL_CONFIG = ROOT / "src" / "decimal_test.cfg"
ARTIFACTS = ROOT / "artifacts"
RELEASES = ARTIFACTS / "releases"
CURRENT = ARTIFACTS / "current.json"
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


@contextmanager
def artifact_lock() -> Iterator[None]:
    with LOCK.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SystemExit("error: another artifact build, verify, or clean is running") from error
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


def write_metadata(stage: Path, interrupt: dict, decimal: dict) -> None:
    manifest = {
        "schema": 2,
        "official_upstream_revision": UPSTREAM_REVISION,
        "tests": {
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
    items = [interrupt, decimal]
    sums = "".join(f"{item['sha256']}  {item['file']}\n" for item in items)
    (stage / "SHA256SUMS").write_text(sums, encoding="ascii")


def verify_release(directory: Path) -> None:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="ascii"))
    expected_fields = {
        "schema": 2,
        "official_upstream_revision": UPSTREAM_REVISION,
    }
    for field, expected in expected_fields.items():
        if manifest.get(field) != expected:
            raise ValueError(f"manifest {field} is stale")

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

    items = [interrupt, decimal]
    expected_sums = "".join(f"{item['sha256']}  {item['file']}\n" for item in items)
    if (directory / "SHA256SUMS").read_text(encoding="ascii") != expected_sums:
        raise ValueError("SHA256SUMS is stale")


def current_release() -> Path:
    pointer = json.loads(CURRENT.read_text(encoding="ascii"))
    if pointer.get("schema") != 1:
        raise ValueError("current artifact pointer schema is unsupported")
    relative = Path(pointer["release"])
    if relative.is_absolute() or relative.parts[:1] != ("releases",) or ".." in relative.parts:
        raise ValueError("current artifact pointer is invalid")
    release = ARTIFACTS / relative
    manifest_sha256 = sha256(release / "manifest.json")
    if relative.name != manifest_sha256:
        raise ValueError("current release directory is not content-addressed")
    if pointer["manifest_sha256"] != manifest_sha256:
        raise ValueError("current artifact pointer checksum is stale")
    return release


def verify_current() -> None:
    release = current_release()
    verify_release(release)
    print(f"verified 2 binaries in {release}")


def verify() -> None:
    with artifact_lock():
        verify_current()


def build() -> None:
    with artifact_lock():
        stage = Path(tempfile.mkdtemp(prefix=".artifacts-stage-", dir=ROOT))
        try:
            interrupt = assemble_interrupt(stage)
            decimal = assemble_decimal(stage)
            write_metadata(stage, interrupt, decimal)
            verify_release(stage)

            release_id = sha256(stage / "manifest.json")
            release = RELEASES / release_id
            RELEASES.mkdir(parents=True, exist_ok=True)
            if release.exists():
                verify_release(release)
                shutil.rmtree(stage)
            else:
                stage.rename(release)

            pointer = {
                "schema": 1,
                "release": f"releases/{release_id}",
                "manifest_sha256": sha256(release / "manifest.json"),
            }
            descriptor = tempfile.NamedTemporaryFile(
                mode="w", encoding="ascii", dir=ARTIFACTS, prefix=".current-", delete=False
            )
            pointer_stage = Path(descriptor.name)
            try:
                with descriptor:
                    json.dump(pointer, descriptor, indent=2, sort_keys=True)
                    descriptor.write("\n")
                    descriptor.flush()
                    os.fsync(descriptor.fileno())
                os.replace(pointer_stage, CURRENT)
            finally:
                pointer_stage.unlink(missing_ok=True)
            verify_current()
        finally:
            if stage.exists():
                shutil.rmtree(stage)


def clean() -> None:
    with artifact_lock():
        if ARTIFACTS.exists():
            shutil.rmtree(ARTIFACTS)
        for stage in ROOT.glob(".artifacts-stage-*"):
            if stage.is_dir():
                shutil.rmtree(stage)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "verify", "clean"))
    args = parser.parse_args()
    if args.action == "build":
        build()
    elif args.action == "verify":
        verify()
    else:
        clean()


if __name__ == "__main__":
    main()
