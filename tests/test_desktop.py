from __future__ import annotations

import json

from banxico_sie_catalog.desktop import doctor
from banxico_sie_catalog.secrets import SecureTokenError


def test_doctor_reports_non_secret_installation_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("banxico_sie_catalog.desktop.get_token", lambda: "secret")
    (tmp_path / "snapshot").mkdir()
    (tmp_path / "snapshot" / "catalog.sqlite").write_text("", encoding="utf-8")
    (tmp_path / "state.json").write_text(json.dumps({"release": "v0.1.0"}), encoding="utf-8")

    assert doctor(tmp_path)["token_available"] is True


def test_doctor_handles_an_unavailable_keyring(tmp_path, monkeypatch) -> None:
    def unavailable():
        raise SecureTokenError("unavailable")

    monkeypatch.setattr("banxico_sie_catalog.desktop.get_token", unavailable)
    assert doctor(tmp_path)["keyring_available"] is False
