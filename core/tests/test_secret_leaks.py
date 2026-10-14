"""Régressions : les erreurs fournisseur ne doivent jamais révéler une clé."""
import json

from tontolo import secrets
from tontolo.providers.openai_compat import classify_error


def test_json_provider_error_redacts_message_and_metadata():
    key = 'sk-proj-FAUSSECLE0123456789abcdefghijklmnopqrstuvwxyz'
    body = json.dumps({'error': {'message': f'Rejected {key}',
                                 'metadata': {'raw': f'upstream {key}'}}})
    assert key not in str(classify_error(401, body, {}))


def test_registered_arbitrary_key_is_redacted(monkeypatch):
    key = 'FAUSSE.CLE.PERSONNELLE.0123456789'
    monkeypatch.setattr(secrets, '_memory', {'custom': key})
    assert key not in secrets.redact(f'Rejected {key}')
    assert key not in str(classify_error(401, json.dumps({'error': {'message': key}}), {}))


def test_logging_redacts_arguments_and_tracebacks(monkeypatch, caplog):
    import logging

    key = 'FAUSSE.CLE.JOURNAL.0123456789'
    monkeypatch.setattr(secrets, '_memory', {'custom': key})
    original = logging.getLogRecordFactory()
    try:
        secrets.install_log_redaction()
        try:
            raise ValueError(key)
        except ValueError:
            logging.getLogger('third.party').exception('Rejected %s', key)
        assert key not in caplog.text
        assert 'ValueError' in caplog.text
        assert 'Rejected' in caplog.text
    finally:
        logging.setLogRecordFactory(original)


def test_redaction_precedes_metadata_truncation(monkeypatch):
    key = 'FAUSSE.CLE.' + 'Z' * 250
    monkeypatch.setattr(secrets, '_memory', {'custom': key})
    body = json.dumps({'error': {'message': 'Rejected', 'metadata': {'raw': key}}})
    assert 'Z' * 20 not in str(classify_error(401, body, {}))


def test_no_http_read_or_export_endpoint_returns_a_key(
        settings, catalog_service, fake, monkeypatch) -> None:
    """Une clé enregistrée n'apparaît dans aucune lecture ni aucun export du cœur."""
    from fastapi.testclient import TestClient

    from tontolo.catalog.service import CatalogService
    from tontolo.providers.registry import ProviderRegistry
    from tontolo.server.app import create_app

    async def fake_load(self):
        self.catalog = catalog_service.catalog
        return self.catalog

    monkeypatch.setattr(CatalogService, "load", fake_load)
    key = "sk-or-v1-FAUSSECLEEXPORT0123456789abcdef"
    monkeypatch.setattr(secrets, "_memory", {"openrouter": key})
    app = create_app(settings, registry=ProviderRegistry(lambda p: fake), refresh=False)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        for path in ("/tontolo/providers", "/tontolo/settings", "/tontolo/metrics",
                     "/tontolo/answers", "/tontolo/memory", "/tontolo/spend",
                     "/tontolo/cloud/export", "/tontolo/activity", "/tontolo/sync",
                     "/tontolo/mcp", "/tontolo/capabilities"):
            r = c.get(path)
            assert key not in r.text, path
