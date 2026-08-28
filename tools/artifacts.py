#!/usr/bin/env python3
"""Build and verify the pinned Klaus interrupt-test binary variants."""

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
SOURCE = ROOT / "src" / "6502_interrupt_test.ca65"
LINKER_CONFIG = ROOT / "src" / "interrupt_test.cfg"
ARTIFACTS = ROOT / "artifacts"
RELEASES = ARTIFACTS / "releases"
CURRENT = ARTIFACTS / "current.json"
LOCK = ROOT / ".artifacts.lock"
VARIANTS = {"nmos": 0, "cmos": 1}
SUCCESS_PC = {"nmos": 0x06F5, "cmos": 0x0719}
UPSTREAM_REVISION = "7954e2dbb49c469ea286070bf46cdd71aeb29e4b"
PORT_REVISION = "708af9b079b2f5e382684cc059d02afdfe6a6812"
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
    expected_loop = bytes((0x4C, success_pc & 0xFF, success_pc >> 8))
    if data[success_pc:success_pc + 3] != expected_loop:
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
        "feedback": FEEDBACK,
        "variants": variants,
    }
    (stage / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    sums = "".join(f"{item['sha256']}  {item['file']}\n" for item in variants)
    (stage / "SHA256SUMS").write_text(sums, encoding="ascii")


def verify_release(directory: Path) -> None:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="ascii"))
    expected_fields = {
        "schema": 1,
        "test": "Klaus Dormann 6502 interrupt test",
        "official_upstream_revision": UPSTREAM_REVISION,
        "ca65_port_revision": PORT_REVISION,
        "source_sha256": sha256(SOURCE),
        "linker_config_sha256": sha256(LINKER_CONFIG),
        "feedback": FEEDBACK,
    }
    for field, expected in expected_fields.items():
        if manifest.get(field) != expected:
            raise ValueError(f"manifest {field} is stale")

    actual = []
    for variant, d_clear in VARIANTS.items():
        item = inspect_binary(directory / f"6502_interrupt_test_{variant}.bin", variant)
        item["d_clear"] = d_clear
        actual.append(item)
    if manifest.get("variants") != actual:
        raise ValueError("manifest does not describe the current binaries")
    if actual[0]["sha256"] == actual[1]["sha256"]:
        raise ValueError("NMOS and CMOS builds are unexpectedly identical")

    expected_sums = "".join(f"{item['sha256']}  {item['file']}\n" for item in actual)
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
    print(f"verified 2 variants in {release}")


def verify() -> None:
    with artifact_lock():
        verify_current()


def build() -> None:
    with artifact_lock():
        stage = Path(tempfile.mkdtemp(prefix=".artifacts-stage-", dir=ROOT))
        try:
            variants = [assemble(stage, name, value) for name, value in VARIANTS.items()]
            write_metadata(stage, variants)
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
