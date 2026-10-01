"""Verified, deterministic bundle export and legacy bundle import."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from tcad_agent.bundles.reader import BundleIntegrityError, BundleReader
from tcad_agent.domain.models import StrictModel


class BundleExportRecord(StrictModel):
    destination: Path
    sha256: str
    bytes: int
    run_id: str


class BundleArchiveService:
    """Write a portable archive only after validating the immutable source bundle."""

    def __init__(self, reader: BundleReader | None = None) -> None:
        self.reader = reader or BundleReader()

    def export(self, bundle_root: Path, destination: Path) -> BundleExportRecord:
        verified = self.reader.read(bundle_root)
        target = destination.expanduser().resolve(strict=False)
        if target.exists():
            raise FileExistsError(f"export destination already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as archive:
                for source in sorted(
                    item for item in verified.root.rglob("*") if item.is_file()
                ):
                    if source.is_symlink():
                        raise BundleIntegrityError(
                            "bundle exports do not permit symbolic-link artifacts"
                        )
                    relative = source.relative_to(verified.root).as_posix()
                    info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, source.read_bytes(), compresslevel=9)
            raw = temporary.read_bytes()
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return BundleExportRecord(
            destination=target,
            sha256=hashlib.sha256(raw).hexdigest(),
            bytes=len(raw),
            run_id=verified.manifest.run_id,
        )


class LegacyBundleImporter:
    """Copy a verified legacy run into managed storage without deleting its source."""

    def __init__(self, managed_root: Path, reader: BundleReader | None = None) -> None:
        self.managed_root = managed_root.expanduser().resolve(strict=False)
        self.reader = reader or BundleReader()

    def import_directory(self, source: Path) -> Path:
        verified = self.reader.read(source)
        run_id = verified.manifest.run_id
        if Path(run_id).name != run_id or any(separator in run_id for separator in ("/", "\\")):
            raise BundleIntegrityError("bundle run identifier is not path-safe")
        self.managed_root.mkdir(parents=True, exist_ok=True)
        destination = (self.managed_root / run_id).resolve(strict=False)
        if not destination.is_relative_to(self.managed_root):
            raise BundleIntegrityError("bundle import destination escapes managed storage")
        if destination.exists():
            raise FileExistsError(f"managed bundle already exists: {run_id}")
        staging = self.managed_root / f".{run_id}.importing"
        if staging.exists():
            raise FileExistsError(f"bundle import is already in progress: {run_id}")
        try:
            shutil.copytree(verified.root, staging, symlinks=True)
            for candidate in staging.rglob("*"):
                if candidate.is_symlink():
                    raise BundleIntegrityError(
                        "legacy bundle imports do not permit symbolic links"
                    )
            self.reader.read(staging)
            os.replace(staging, destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return destination
