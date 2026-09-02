from __future__ import annotations

import hashlib
import io
import json
import zipfile

from banxico_sie_catalog.installer import install_catalog_release


def test_install_downloads_verifies_and_queries_snapshot(tmp_path, monkeypatch) -> None:
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("catalog.json", "[]")
        archive.writestr("manifest.json", json.dumps({"record_count": 0}))
        archive.writestr("catalog.sqlite", "placeholder")
    archive_bytes = archive_buffer.getvalue()
    release = {
        "tag_name": "v0.1.0",
        "assets": [
            {
                "name": "banxico-sie-catalog-v0.1.0-snapshot.zip",
                "digest": f"sha256:{hashlib.sha256(archive_bytes).hexdigest()}",
                "browser_download_url": "https://example.test/catalog.zip",
            }
        ],
    }
    monkeypatch.setattr(
        "banxico_sie_catalog.installer._request",
        lambda url: json.dumps(release).encode() if "api.github.com" in url else archive_bytes,
    )
    monkeypatch.setattr("banxico_sie_catalog.installer.list_sectors", lambda database: [{}])

    destination = tmp_path / "snapshot"
    result = install_catalog_release("owner/repository", "v0.1.0", destination)

    assert result["sector_count"] == 1
    assert result["record_count"] == 0
    assert (destination / "catalog.sqlite").is_file()
