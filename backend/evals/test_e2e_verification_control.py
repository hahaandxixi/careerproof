import asyncio
import json

import httpx
import pytest

from evals.e2e_verification import CONTROL_NAME, SyntheticVerificationProvider, read_control


@pytest.mark.parametrize('value', [
    {'mode': 'external'}, {'mode': 'delay', 'delaySeconds': 16},
    {'mode': 'delay', 'delaySeconds': -1}, {'mode': 'delay', 'delaySeconds': True},
    {'mode': 'known', 'delaySeconds': 1}, {'mode': 'known', 'url': 'https://example.com'},
    [], {'mode': 'delay', 'delaySeconds': float('nan')},
])
def test_invalid_control_fails_closed(tmp_path, value):
    path = tmp_path / CONTROL_NAME
    path.write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ValueError):
        read_control(path)


def test_missing_control_preserves_known_and_malformed_is_not_fallback(tmp_path):
    path = tmp_path / CONTROL_NAME
    assert read_control(path) == {'mode': 'known', 'delaySeconds': 0}
    path.write_text('{', encoding='utf-8')
    with pytest.raises(ValueError):
        read_control(path)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,expected_status,usage_present', [
    ('known', 200, True), ('unknown', 200, False), ('failure', 503, False),
])
async def test_control_only_changes_local_mock_response(
    tmp_path, mode, expected_status, usage_present,
):
    path = tmp_path / CONTROL_NAME
    path.write_text(json.dumps({'mode': mode}), encoding='utf-8')
    provider = SyntheticVerificationProvider(path)
    assert isinstance(provider._transport, httpx.MockTransport)
    async with httpx.AsyncClient(transport=provider._transport) as client:
        response = await client.post('https://api.deepseek.com/chat/completions', json={
            'messages': [{'content': json.dumps({'fixedReportRequirements': []})}],
        })
    assert response.status_code == expected_status
    assert ('usage' in response.json()) is usage_present


@pytest.mark.asyncio
async def test_delay_is_bounded_and_snapshot_does_not_change_in_flight(tmp_path, monkeypatch):
    path = tmp_path / CONTROL_NAME
    path.write_text(json.dumps({'mode': 'delay', 'delaySeconds': 15}), encoding='utf-8')
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        path.write_text(json.dumps({'mode': 'failure'}), encoding='utf-8')

    monkeypatch.setattr(asyncio, 'sleep', fake_sleep)
    provider = SyntheticVerificationProvider(path)
    async with httpx.AsyncClient(transport=provider._transport) as client:
        response = await client.post('https://api.deepseek.com/chat/completions', json={
            'messages': [{'content': json.dumps({'fixedReportRequirements': []})}],
        })
    assert sleeps == [15]
    assert response.status_code == 200
    assert response.json()['usage']['total_tokens'] == 180


def test_linked_control_is_rejected_without_reading_target(tmp_path, monkeypatch):
    path = tmp_path / CONTROL_NAME
    monkeypatch.setattr(type(path), 'is_symlink', lambda self: True)
    with pytest.raises(ValueError, match='linked'):
        read_control(path)


def test_oversized_control_is_rejected(tmp_path):
    path = tmp_path / CONTROL_NAME
    path.write_text(' ' * 1025, encoding='utf-8')
    with pytest.raises(ValueError, match='file'):
        read_control(path)


def test_invalid_control_prevents_factory_override(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services import application_verification as verification
    from evals import e2e_verification as adapter

    original_identity = verification._identity
    original_provider = verification.get_ai_provider
    monkeypatch.setenv('E2E_SYNTHETIC_VERIFICATION_RUN', 'control-test')
    monkeypatch.setattr(settings, 'storage_base_dir', tmp_path)
    # Environment validation is independently covered by the original test file.
    monkeypatch.setattr(adapter, 'validate_environment', lambda *args: None)
    (tmp_path / CONTROL_NAME).write_text('{', encoding='utf-8')
    with pytest.raises(ValueError):
        adapter.create_app()
    assert verification._identity is original_identity
    assert verification.get_ai_provider is original_provider


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,present', [('known', True), ('unknown', False)])
async def test_actual_provider_marks_usage_presence(tmp_path, monkeypatch, mode, present):
    async def forbidden_network(*args, **kwargs):
        raise AssertionError('Control attempted external transport')

    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden_network)
    path = tmp_path / CONTROL_NAME
    path.write_text(json.dumps({'mode': mode}), encoding='utf-8')
    provider = SyntheticVerificationProvider(path)
    await provider.generate_bounded_json(
        system='Synthetic verification only',
        data={'fixedReportRequirements': []}, max_tokens=3000,
    )
    assert len(provider.usage_records) == 1
    assert provider.usage_records[0].usage_present is present
