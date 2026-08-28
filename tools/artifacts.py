#!/usr/bin/env python3
"""Build and verify the pinned Klaus interrupt-test binary variants."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "6502_interrupt_test.ca65"
LINKER_CONFIG = ROOT / "src" / "interrupt_test.cfg"
ARTIFACTS = ROOT / "artifacts"
VARIANTS = {"nmos": 0, "cmos": 1}
SUCCESS_PC = {"nmos": 0x06F5, "cmos": 0x0719}
UPSTREAM_REVISION = "7954e2dbb49c469ea286070bf46cdd71aeb29e4b"
PORT_REVISION = "708af9b079b2f5e382684cc059d02afdfe6a6812"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command_version(command: str) -> str:
    result = subprocess.run(
        [command, "--version"], check=True, capture_output=True, text=True
    )
    return (result.stdout or result.stderr).strip()


def inspect_binary(path: Path, variant: str) -> dict[str, int | str]:
    data = path.read_bytes()
    if len(data) != 65536:
        raise ValueError(f"{path.name}: expected 65536 bytes, found {len(data)}")
    if data[0x0400] != 0xD8:  # CLD at the configured entry point.
        raise ValueError(f"{path.name}: missing CLD at $0400")
    nmi_vector = int.from_bytes(data[0xFFFA:0xFFFC], "little")
    irq_vector = int.from_bytes(data[0xFFFE:0x10000], "little")
    for label, address in (("NMI", nmi_vector), ("IRQ", irq_vector)):
        if not 0x0400 <= address < 0x8000:
            raise ValueError(f"{path.name}: {label} vector ${address:04X} is outside test code")
    success_pc = SUCCESS_PC[variant]
    if data[success_pc:success_pc + 3] != bytes((0x4C, success_pc & 0xFF, success_pc >> 8)):
        raise ValueError(f"{path.name}: missing success self-loop at ${success_pc:04X}")
    return {
        "file": path.name,
        "bytes": len(data),
        "sha256": sha256(path),
        "entry_point": "0x0400",
        "nmi_vector": f"0x{nmi_vector:04X}",
        "irq_vector": f"0x{irq_vector:04X}",
        "success_pc": f"0x{success_pc:04X}",
    }


def assemble(stage: Path, variant: str, d_clear: int) -> dict[str, int | str]:
    object_path = stage / f"{variant}.o"
    binary_path = stage / f"6502_interrupt_test_{variant}.bin"
    subprocess.run(
        [
            "ca65",
            "-D",
            f"D_clear={d_clear}",
            str(SOURCE),
            "-o",
            str(object_path),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ld65",
            str(object_path),
            "-o",
            str(binary_path),
            "-C",
            str(LINKER_CONFIG),
        ],
        check=True,
    )
    object_path.unlink()
    result = inspect_binary(binary_path, variant)
    result["d_clear"] = d_clear
    return result


def write_metadata(stage: Path, variants: list[dict[str, int | str]]) -> None:
    manifest = {
        "schema": 1,
        "test": "Klaus Dormann 6502 interrupt test",
        "official_upstream_revision": UPSTREAM_REVISION,
        "ca65_port_revision": PORT_REVISION,
        "source_sha256": sha256(SOURCE),
        "linker_config_sha256": sha256(LINKER_CONFIG),
        "ca65": command_version("ca65"),
        "ld65": command_version("ld65"),
        "variants": variants,
    }
    (stage / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    checksum_lines = [
        f"{item['sha256']}  {item['file']}" for item in variants
    ]
    (stage / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="ascii")


def verify(directory: Path = ARTIFACTS) -> None:
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    if manifest["official_upstream_revision"] != UPSTREAM_REVISION:
        raise ValueError("manifest official upstream revision does not match the build pin")
    if manifest["ca65_port_revision"] != PORT_REVISION:
        raise ValueError("manifest CA65 port revision does not match the build pin")
    if manifest["source_sha256"] != sha256(SOURCE):
        raise ValueError("manifest source checksum is stale")
    if manifest["linker_config_sha256"] != sha256(LINKER_CONFIG):
        raise ValueError("manifest linker-config checksum is stale")

    actual = []
    for variant, d_clear in VARIANTS.items():
        item = inspect_binary(directory / f"6502_interrupt_test_{variant}.bin", variant)
        item["d_clear"] = d_clear
        actual.append(item)
    if manifest["variants"] != actual:
        raise ValueError("manifest does not describe the current binaries")
    if actual[0]["sha256"] == actual[1]["sha256"]:
        raise ValueError("NMOS and CMOS builds are unexpectedly identical")

    expected_sums = "".join(f"{item['sha256']}  {item['file']}\n" for item in actual)
    if (directory / "SHA256SUMS").read_text(encoding="ascii") != expected_sums:
        raise ValueError("SHA256SUMS is stale")
    print(f"verified {len(actual)} variants in {directory}")


def build() -> None:
    stage = Path(tempfile.mkdtemp(prefix=".artifacts-", dir=ROOT))
    previous = ROOT / "artifacts.previous"
    try:
        variants = [assemble(stage, name, value) for name, value in VARIANTS.items()]
        write_metadata(stage, variants)
        verify(stage)
        if previous.exists():
            shutil.rmtree(previous)
        if ARTIFACTS.exists():
            ARTIFACTS.rename(previous)
        stage.rename(ARTIFACTS)
        if previous.exists():
            shutil.rmtree(previous)
    except BaseException:
        if not ARTIFACTS.exists() and previous.exists():
            previous.rename(ARTIFACTS)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def clean() -> None:
    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS)
    previous = ROOT / "artifacts.previous"
    if previous.exists():
        shutil.rmtree(previous)
    for stage in ROOT.glob(".artifacts-*"):
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
