from types import SimpleNamespace

from app.core import database


def test_mongo_client_requires_valid_certificate_and_hostname(monkeypatch):
    observed = {}
    client = object()

    def connect(uri, **kwargs):
        observed.update(uri=uri, **kwargs)
        return client

    monkeypatch.setattr(database, "_client", None)
    monkeypatch.setattr(database, "get_settings", lambda: SimpleNamespace(mongodb_uri="mongodb://localhost:1"))
    monkeypatch.setattr(database, "MongoClient", connect)
    assert database.get_client() is client
    assert database.get_client() is client
    assert observed["tls"] is True
    assert observed["tlsAllowInvalidCertificates"] is False
    assert observed["tlsAllowInvalidHostnames"] is False
