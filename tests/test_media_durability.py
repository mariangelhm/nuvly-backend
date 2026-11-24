from types import SimpleNamespace

import pytest

from app.modules.media import service


@pytest.mark.parametrize("root,durable", [(None, False), ("relative/path", True), (None, True)])
def test_production_refuses_unconfigured_durable_storage(monkeypatch, root, durable):
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(app_env="production", media_storage_root=root, media_storage_durable=durable),
    )
    with pytest.raises(RuntimeError, match="durable volume"):
        service.ensure_static_directories()


def test_media_survives_a_new_application_directory(monkeypatch, tmp_path):
    root = tmp_path / "mounted-volume"
    settings = SimpleNamespace(app_env="production", media_storage_root=str(root), media_storage_durable=True)
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "STATIC_DIR", tmp_path / "deployment-one")
    service.ensure_static_directories()
    asset = service.ensure_upload_directory("customer_website") / "asset.png"
    asset.write_bytes(b"synthetic-image-canary")
    monkeypatch.setattr(service, "STATIC_DIR", tmp_path / "deployment-two")
    service.ensure_static_directories()
    assert (service.ensure_upload_directory("customer_website") / "asset.png").read_bytes() == b"synthetic-image-canary"
