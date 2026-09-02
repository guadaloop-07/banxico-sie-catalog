"""Install and validate immutable catalog snapshots from GitHub releases."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .catalog import CatalogError, list_sectors

DEFAULT_REPOSITORY = "guadaloop-07/banxico-sie-catalog"
REQUIRED_SNAPSHOT_FILES = frozenset({"catalog.json", "catalog.sqlite", "manifest.json"})


class CatalogInstallError(Exception):
    """Raised when a release snapshot cannot be safely installed."""


def _request(url: str) -> bytes:
    request = Request(url, headers={"Accept": "application/vnd.github+json"})
    try:
        with urlopen(request, timeout=60) as response:  # noqa: S310 - release URL is constructed locally
            return response.read()
    except (HTTPError, URLError, OSError) as error:
        raise CatalogInstallError(f"Could not download catalog release: {error}") from error


def _release_asset(repository: str, release: str) -> tuple[str, str, str]:
    api_url = f"https://api.github.com/repos/{repository}/releases/tags/{release}"
    try:
        payload = json.loads(_request(api_url))
    except json.JSONDecodeError as error:
        raise CatalogInstallError("GitHub returned an invalid release response") from error
    if not isinstance(payload, dict) or payload.get("tag_name") != release:
        raise CatalogInstallError(f"Release {release!r} was not found in {repository}")
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise CatalogInstallError(f"Release {release!r} has no downloadable assets")
    snapshot_assets = [
        asset
        for asset in assets
        if isinstance(asset, dict)
        and isinstance(asset.get("name"), str)
        and asset["name"].endswith("-snapshot.zip")
    ]
    if len(snapshot_assets) != 1:
        raise CatalogInstallError(
            f"Release {release!r} must contain exactly one *-snapshot.zip asset"
        )
    asset = snapshot_assets[0]
    digest = asset.get("digest")
    download_url = asset.get("browser_download_url")
    name = asset["name"]
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise CatalogInstallError(f"Release asset {name!r} has no SHA-256 checksum")
    if not isinstance(download_url, str):
        raise CatalogInstallError(f"Release asset {name!r} has no download URL")
    return name, download_url, digest.removeprefix("sha256:")


def _extract_snapshot(archive: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = [item for item in bundle.infolist() if not item.is_dir()]
            files = {
                item.filename
                for item in members
                if not Path(item.filename).is_absolute() and ".." not in Path(item.filename).parts
            }
            root_files = {Path(item).name for item in files if len(Path(item).parts) == 1}
            if not REQUIRED_SNAPSHOT_FILES <= root_files:
                missing = ", ".join(sorted(REQUIRED_SNAPSHOT_FILES - root_files))
                raise CatalogInstallError(f"Snapshot archive is missing required files: {missing}")
            if len(files) != len(members):
                raise CatalogInstallError("Snapshot archive contains an unsafe path")
            bundle.extractall(destination)
    except zipfile.BadZipFile as error:
        raise CatalogInstallError("Downloaded release asset is not a valid ZIP archive") from error


def install_catalog_release(repository: str, release: str, output_dir: Path) -> dict[str, object]:
    """Download, checksum-verify, validate, and install a release snapshot once."""
    if output_dir.exists():
        raise CatalogInstallError(f"Destination already exists: {output_dir}")
    asset_name, download_url, expected_digest = _release_asset(repository, release)
    parent = output_dir.parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="banxico-sie-catalog-", dir=parent) as temporary:
        staging = Path(temporary)
        archive = staging / asset_name
        archive.write_bytes(_request(download_url))
        with archive.open("rb") as file:
            actual_digest = hashlib.file_digest(file, "sha256").hexdigest()
        if actual_digest != expected_digest:
            raise CatalogInstallError(
                f"Checksum mismatch for {asset_name}: expected {expected_digest}, "
                f"got {actual_digest}"
            )
        snapshot = staging / "snapshot"
        snapshot.mkdir()
        _extract_snapshot(archive, snapshot)
        try:
            sectors = list_sectors(snapshot / "catalog.sqlite")
        except CatalogError as error:
            raise CatalogInstallError(f"MCP catalog query failed: {error}") from error
        try:
            manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CatalogInstallError("Snapshot manifest is not valid JSON") from error
        if not isinstance(manifest, dict):
            raise CatalogInstallError("Snapshot manifest must contain an object")
        shutil.move(str(snapshot), output_dir)
    return {
        "release": release,
        "repository": repository,
        "destination": str(output_dir),
        "checksum": f"sha256:{actual_digest}",
        "sector_count": len(sectors),
        "record_count": manifest.get("record_count"),
    }
