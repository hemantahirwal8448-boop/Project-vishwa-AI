from fastapi.testclient import TestClient
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main

client = TestClient(main.app)

def test_health_version():
    r = client.get('/health'); assert r.status_code == 200
    assert r.json()['status'] == 'ok' and r.json()['version'] == '2.8.0'

def test_status_does_not_expose_secret():
    r = client.get('/api/status'); assert r.status_code == 200
    assert 'AI_API_KEY' not in str(r.json()) and 'api_key' not in str(r.json()).lower()

def test_modes():
    ids = {x['id'] for x in client.get('/api/modes').json()}
    assert {'general','study','research','coding','government','business','creative','robotics'} <= ids

def test_demo_is_honest(monkeypatch):
    for k in ('AI_BASE_URL','AI_API_KEY','AI_MODEL'): monkeypatch.delenv(k, raising=False)
    r=client.post('/api/chat',json={'message':'Namaste'})
    assert r.status_code == 200 and r.json()['provider']=='demo'

def test_empty_message_rejected():
    assert client.post('/api/chat',json={'message':''}).status_code == 422

def test_reject_non_pdf():
    r=client.post('/api/document',files={'file':('test.txt',b'hello','text/plain')})
    assert r.status_code == 400

def test_reject_oversized_pdf():
    r=client.post('/api/document',files={'file':('big.pdf',b'%PDF-'+b'x'*(5*1024*1024+1),'application/pdf')})
    assert r.status_code == 413


def test_research_reports_unconfigured(monkeypatch):
    monkeypatch.delenv('SEARCH_API_KEY', raising=False)
    r = client.post('/api/research', json={'query': 'MP government scholarship'})
    assert r.status_code == 200
    assert r.json()['available'] is False

def test_research_requires_query():
    assert client.post('/api/research', json={'query': ''}).status_code == 422


def test_plans_are_transparent_and_no_payments_enabled():
    r = client.get('/api/plans')
    assert r.status_code == 200
    data = r.json()
    assert data['payment_enabled'] is False
    assert data['plans'][0]['price_inr_month'] == 0
    assert data['plans'][1]['price_inr_month'] is None


def test_security_headers_present():
    r = client.get('/health')
    assert r.headers['x-content-type-options'] == 'nosniff'
    assert r.headers['x-frame-options'] == 'DENY'
    assert r.headers['referrer-policy'] == 'strict-origin-when-cross-origin'


def test_research_button_is_in_page():
    r = client.get('/')
    assert r.status_code == 200
    assert 'researchBtn' in r.text and 'Search web' in r.text

def test_unknown_mode_falls_back_to_general(monkeypatch):
    for k in ('AI_BASE_URL','AI_API_KEY','AI_MODEL'): monkeypatch.delenv(k, raising=False)
    r = client.post('/api/chat', json={'message':'Hello', 'mode':'unknown-mode'})
    assert r.status_code == 200
    assert r.json()['mode'] == 'general'


def test_model_check_reports_unconfigured(monkeypatch):
    for k in ('AI_BASE_URL','AI_API_KEY','AI_MODEL'):
        monkeypatch.delenv(k, raising=False)
    r = client.post('/api/model-check')
    assert r.status_code == 200
    assert r.json()['configured'] is False and r.json()['connected'] is False


def test_model_check_does_not_expose_secret(monkeypatch):
    monkeypatch.setenv('AI_BASE_URL', 'https://provider.example/v1')
    monkeypatch.setenv('AI_API_KEY', 'super-secret-test-key')
    monkeypatch.setenv('AI_MODEL', 'test-model')
    r = client.post('/api/model-check')
    assert 'super-secret-test-key' not in r.text


def test_research_results_are_connected_to_chat_ui():
    page = client.get('/').text
    assert 'WEB RESEARCH RESULTS for:' in page
    assert 'will be included as context in your next message' in page


def test_rate_limit_returns_retry_after(monkeypatch):
    import main as app_module
    monkeypatch.setattr(app_module, "_RATE_LIMIT", 1)
    app_module._rate_buckets.clear()
    first = client.post('/api/research', json={'query': 'first request'})
    second = client.post('/api/research', json={'query': 'second request'})
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers['retry-after'] == '60'
    app_module._rate_buckets.clear()


def test_ui_version_matches_app_version():
    page = client.get('/').text
    assert 'MVP · v2.8.0' in page


def test_research_query_max_length_validation():
    r = client.post('/api/research', json={'query': 'x' * 401})
    assert r.status_code == 422


def test_research_query_wrong_type_validation():
    r = client.post('/api/research', json={'query': ['not', 'a', 'string']})
    assert r.status_code == 422


def test_oversized_pdf_rejected_with_chunked_reader():
    # Body is over the configured cap; endpoint should return 413.
    payload = b'%PDF-' + b'x' * (5 * 1024 * 1024 + 1)
    r = client.post('/api/document', files={'file': ('large.pdf', payload, 'application/pdf')})
    assert r.status_code == 413


def test_preflight_is_honest_and_does_not_claim_launch_ready(monkeypatch):
    for k in ('AI_BASE_URL','AI_API_KEY','AI_MODEL','SEARCH_API_KEY'):
        monkeypatch.delenv(k, raising=False)
    r = client.get('/api/preflight')
    assert r.status_code == 200
    data = r.json()
    assert data['launch_ready'] is False
    assert data['checks']['payment_processing_enabled'] is False
    assert data['checks']['public_deployment_verified'] is False
    assert set(data['missing_model_settings']) == {'AI_BASE_URL','AI_API_KEY','AI_MODEL'}


def test_preflight_never_returns_api_key_value(monkeypatch):
    monkeypatch.setenv('AI_BASE_URL', 'https://provider.example/v1')
    monkeypatch.setenv('AI_API_KEY', 'never-return-this-secret')
    monkeypatch.setenv('AI_MODEL', 'example-model')
    r = client.get('/api/preflight')
    assert 'never-return-this-secret' not in r.text
    assert 'AI_API_KEY' not in r.json()['missing_model_settings']


def test_model_connection_button_is_in_page():
    page = client.get('/').text
    assert 'modelCheckBtn' in page
    assert 'Test AI connection' in page


def test_model_check_live_success_with_mock(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    monkeypatch.setenv('AI_BASE_URL', 'https://provider.example/v1')
    monkeypatch.setenv('AI_API_KEY', 'test-secret')
    monkeypatch.setenv('AI_MODEL', 'test-model')
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {'choices': [{'message': {'content': 'OK'}}]}
    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            assert url == 'https://provider.example/v1/chat/completions'
            assert kwargs['headers']['Authorization'] == 'Bearer test-secret'
            return FakeResponse()
    monkeypatch.setattr(main.httpx, 'AsyncClient', FakeClient)
    r = client.post('/api/model-check')
    assert r.status_code == 200
    assert r.json()['connected'] is True
    assert r.json()['model'] == 'test-model'
    assert 'test-secret' not in r.text


def test_chat_provider_success_with_mock(monkeypatch):
    monkeypatch.setenv('AI_BASE_URL', 'https://provider.example/v1')
    monkeypatch.setenv('AI_API_KEY', 'test-secret')
    monkeypatch.setenv('AI_MODEL', 'test-model')
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {'choices': [{'message': {'content': 'Namaste!'}}]}
    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            assert url == 'https://provider.example/v1/chat/completions'
            assert kwargs['json']['model'] == 'test-model'
            return FakeResponse()
    monkeypatch.setattr(main.httpx, 'AsyncClient', FakeClient)
    r = client.post('/api/chat', json={'message': 'Namaste', 'mode': 'general'})
    assert r.status_code == 200
    assert r.json()['answer'] == 'Namaste!'
    assert r.json()['provider'] == 'configured-model'
    assert 'test-secret' not in r.text

def test_privacy_endpoint_is_transparent(monkeypatch):
    for k in ('AI_BASE_URL','AI_API_KEY','AI_MODEL','SEARCH_API_KEY'): monkeypatch.delenv(k, raising=False)
    r = client.get('/api/privacy')
    assert r.status_code == 200
    assert r.json()['chat_history_saved_server_side'] is False
    assert r.json()['accounts_enabled'] is False

def test_limits_endpoint_documents_caps():
    r = client.get('/api/limits')
    assert r.status_code == 200
    data = r.json()
    assert data['chat_message_characters'] == 12000
    assert data['pdf_max_bytes'] == 5 * 1024 * 1024
    assert data['history_messages_forwarded_to_model'] <= data['history_messages']

def test_readiness_does_not_claim_external_test(monkeypatch):
    for k in ('AI_BASE_URL','AI_API_KEY','AI_MODEL'): monkeypatch.delenv(k, raising=False)
    r = client.get('/api/ready')
    assert r.status_code == 200
    assert r.json()['ready_for_real_model_requests'] is False
    assert r.json()['external_provider_tested'] is False

def test_response_has_server_request_id():
    r = client.get('/health')
    assert r.status_code == 200
    assert len(r.headers['x-request-id']) == 32

def test_diagnostics_never_claims_launch_ready(monkeypatch):
    for k in ('AI_BASE_URL','AI_API_KEY','AI_MODEL','SEARCH_API_KEY'): monkeypatch.delenv(k, raising=False)
    r = client.get('/api/diagnostics')
    assert r.status_code == 200
    assert r.json()['launch_ready'] is False
    assert r.json()['payments_enabled'] is False
    assert 'never-return-this-secret' not in r.text


def test_provider_rejects_remote_plain_http(monkeypatch):
    monkeypatch.setenv('AI_BASE_URL', 'http://provider.example/v1')
    monkeypatch.setenv('AI_API_KEY', 'test-secret')
    monkeypatch.setenv('AI_MODEL', 'test-model')
    r = client.post('/api/model-check')
    assert r.status_code == 200
    assert r.json()['configured'] is False
    assert r.json()['connected'] is False
    assert 'test-secret' not in r.text

def test_provider_allows_localhost_http(monkeypatch):
    monkeypatch.setenv('AI_BASE_URL', 'http://127.0.0.1:11434/v1')
    monkeypatch.setenv('AI_API_KEY', 'local-test-key')
    monkeypatch.setenv('AI_MODEL', 'local-model')
    config, error = main._provider_config()
    assert error is None
    assert config['base_url'] == 'http://127.0.0.1:11434/v1'

def test_provider_rejects_credentials_in_url(monkeypatch):
    monkeypatch.setenv('AI_BASE_URL', 'https://user:pass@provider.example/v1')
    monkeypatch.setenv('AI_API_KEY', 'test-secret')
    monkeypatch.setenv('AI_MODEL', 'test-model')
    config, error = main._provider_config()
    assert config is None and error == 'invalid_url'

def test_provider_timeout_is_bounded(monkeypatch):
    monkeypatch.setenv('AI_BASE_URL', 'https://provider.example/v1')
    monkeypatch.setenv('AI_API_KEY', 'test-secret')
    monkeypatch.setenv('AI_MODEL', 'test-model')
    monkeypatch.setenv('AI_TIMEOUT_SECONDS', '999')
    config, error = main._provider_config()
    assert error is None and config['timeout'] == 90.0

def test_remote_http_chat_is_rejected_safely(monkeypatch):
    monkeypatch.setenv('AI_BASE_URL', 'http://provider.example/v1')
    monkeypatch.setenv('AI_API_KEY', 'test-secret')
    monkeypatch.setenv('AI_MODEL', 'test-model')
    r = client.post('/api/chat', json={'message': 'hello'})
    assert r.status_code == 503
    assert 'test-secret' not in r.text


def test_database_status_reports_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'vishwa-test.db'))
    r = client.get('/api/database-status')
    assert r.status_code == 200
    assert r.json()['available'] is True
    assert r.json()['chat_history_storage'] is False

def test_feedback_requires_explicit_consent(monkeypatch, tmp_path):
    monkeypatch.setenv('ENABLE_FEEDBACK_STORAGE', 'true')
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'vishwa-test.db'))
    r = client.post('/api/feedback', json={'category':'idea','message':'Add Hindi voice','consent_to_store':False})
    assert r.status_code == 400

def test_feedback_stores_only_with_consent(monkeypatch, tmp_path):
    monkeypatch.setenv('ENABLE_FEEDBACK_STORAGE', 'true')
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'vishwa-test.db'))
    r = client.post('/api/feedback', json={'category':'idea','message':'Add Hindi voice','consent_to_store':True})
    assert r.status_code == 200 and r.json()['stored'] is True
    assert 'Add Hindi voice' not in r.text

def test_feedback_rejects_secret_like_text(monkeypatch, tmp_path):
    monkeypatch.setenv('ENABLE_FEEDBACK_STORAGE', 'true')
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'vishwa-test.db'))
    r = client.post('/api/feedback', json={'category':'bug','message':'api_key=secret-value','consent_to_store':True})
    assert r.status_code == 400
    assert 'secret-value' not in r.text

def test_privacy_discloses_feedback_storage(monkeypatch):
    monkeypatch.delenv('ENABLE_FEEDBACK_STORAGE', raising=False)
    data = client.get('/api/privacy').json()
    assert data['feedback_storage_enabled'] is False
    assert data['feedback_requires_explicit_consent'] is True


def test_privacy_database_availability_reflects_real_storage(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'privacy-test.db'))
    r = client.get('/api/privacy')
    assert r.status_code == 200
    assert r.json()['sqlite_feedback_storage_available'] is True
    assert r.json()['chat_history_saved_server_side'] is False
    assert r.json()['accounts_enabled'] is False


def test_feedback_storage_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv('ENABLE_FEEDBACK_STORAGE', raising=False)
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'disabled.db'))
    r = client.post('/api/feedback', json={'category':'idea','message':'Add Hindi voice','consent_to_store':True})
    assert r.status_code == 503
    assert 'disabled' in r.json()['detail'].lower()

def test_database_status_distinguishes_available_from_enabled(monkeypatch, tmp_path):
    monkeypatch.delenv('ENABLE_FEEDBACK_STORAGE', raising=False)
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'status.db'))
    data = client.get('/api/database-status').json()
    assert data['available'] is True
    assert data['feedback_storage'] is False


def test_database_url_selects_postgresql_without_leaking_dsn(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:secret@db.example.test:5432/vishwa')
    monkeypatch.delenv('ENABLE_FEEDBACK_STORAGE', raising=False)
    class FakeCursor:
        def fetchone(self): return (1,)
    class FakeConnection:
        def execute(self, query, params=None): return FakeCursor()
        def commit(self): pass
        def close(self): pass
    import types
    fake_psycopg = types.SimpleNamespace(connect=lambda *a, **k: FakeConnection())
    monkeypatch.setitem(sys.modules, 'psycopg', fake_psycopg)
    data = client.get('/api/database-status').json()
    assert data['available'] is True
    assert data['engine'] == 'postgresql'
    assert 'secret' not in str(data)
    assert 'db.example.test' not in str(data)


def test_postgresql_feedback_uses_parameterized_insert_and_consent(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:secret@db.example.test:5432/vishwa')
    monkeypatch.setenv('ENABLE_FEEDBACK_STORAGE', 'true')
    calls = []
    class FakeCursor:
        def fetchone(self): return (17,)
    class FakeConnection:
        def execute(self, query, params=None):
            calls.append((query, params))
            return FakeCursor()
        def commit(self): pass
        def close(self): pass
    import types
    monkeypatch.setitem(sys.modules, 'psycopg', types.SimpleNamespace(connect=lambda *a, **k: FakeConnection()))
    response = client.post('/api/feedback', json={'category':'idea','message':'Add Hindi voice','consent_to_store':True})
    assert response.status_code == 200
    assert response.json()['feedback_id'] == 17
    assert any('RETURNING id' in query and params[1] == 'Add Hindi voice' for query, params in calls if params)
    assert 'postgresql://user:secret@' not in response.text


def test_sqlite_feedback_is_committed_and_readable(monkeypatch, tmp_path):
    db_path = tmp_path / 'feedback-commit.db'
    monkeypatch.setenv('DATABASE_PATH', str(db_path))
    monkeypatch.setenv('ENABLE_FEEDBACK_STORAGE', 'true')
    response = client.post('/api/feedback', json={'category':'idea','message':'Please add voice mode','consent_to_store':True})
    assert response.status_code == 200
    import sqlite3
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute('SELECT category, message FROM feedback').fetchall()
    assert rows == [('idea', 'Please add voice mode')]


def test_chat_live_success_with_mock(monkeypatch):
    monkeypatch.setenv('AI_BASE_URL', 'https://provider.example/v1')
    monkeypatch.setenv('AI_API_KEY', 'private-test-key')
    monkeypatch.setenv('AI_MODEL', 'test-model')

    class FakeResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {'choices': [{'message': {'content': 'Namaste!'}}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            assert url == 'https://provider.example/v1/chat/completions'
            assert kwargs['headers']['Authorization'] == 'Bearer private-test-key'
            return FakeResponse()

    monkeypatch.setattr(main.httpx, 'AsyncClient', FakeClient)
    r = client.post('/api/chat', json={'message': 'Namaste', 'mode': 'general'})
    assert r.status_code == 200
    assert r.json()['answer'] == 'Namaste!'
    assert r.json()['provider'] == 'configured-model'
    assert 'private-test-key' not in r.text


def test_chat_provider_failure_does_not_leak_credentials(monkeypatch):
    import httpx
    monkeypatch.setenv('AI_BASE_URL', 'https://provider.example/v1')
    monkeypatch.setenv('AI_API_KEY', 'do-not-leak-this-key')
    monkeypatch.setenv('AI_MODEL', 'test-model')

    class FakeResponse:
        def raise_for_status(self):
            request = httpx.Request('POST', 'https://provider.example/v1/chat/completions')
            response = httpx.Response(401, request=request, text='do-not-leak-this-key')
            raise httpx.HTTPStatusError('provider error', request=request, response=response)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(main.httpx, 'AsyncClient', FakeClient)
    r = client.post('/api/chat', json={'message': 'Hello'})
    assert r.status_code == 502
    assert 'do-not-leak-this-key' not in r.text
    assert 'provider error' not in r.text
