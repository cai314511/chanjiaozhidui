import base64
import hashlib
import hmac

from fastapi.testclient import TestClient

from tests.test_api import account, system
from tests.test_interview_flow_fixes import setup_room


def test_room_connectivity_requires_authorization_and_issues_short_lived_turn(system, monkeypatch):
    employer, student, _, application, room = setup_room(system, 'human')
    path = '/api/interviews/' + room['id'] + '/connectivity'
    monkeypatch.setenv('INTERVIEW_STUN_URLS', 'stun:stun.example.org:3478')
    monkeypatch.setenv('INTERVIEW_TURN_URLS', 'turn:relay.example.org:3478?transport=udp,turns:relay.example.org:5349')
    monkeypatch.setenv('INTERVIEW_TURN_SECRET', 'isolated-test-turn-secret')
    assert TestClient(system).get(path).status_code == 401
    outsider = account(system, 'employer', 'rtc-outsider')
    assert outsider.get(path).status_code == 403
    data = employer.get(path).json()
    assert data['relay_configured']
    assert len(data['iceServers']) == 2
    turn = data['iceServers'][1]
    assert turn['credential'] == base64.b64encode(hmac.new(
        b'isolated-test-turn-secret', turn['username'].encode(), hashlib.sha1).digest()).decode()
    assert 'secret' not in data
    assert data['expires_in'] == 600
    student.post('/api/applications/' + application['id'] + '/withdraw')
    assert employer.get(path).status_code == 403


def test_unconfigured_or_invalid_connectivity_is_explicit(system, monkeypatch):
    _, student, _, _, room = setup_room(system, 'human')
    path = '/api/interviews/' + room['id'] + '/connectivity'
    for key in ('INTERVIEW_STUN_URLS', 'INTERVIEW_TURN_URLS', 'INTERVIEW_TURN_SECRET'):
        monkeypatch.delenv(key, raising=False)
    data = student.get(path).json()
    assert data['iceServers'] == [] and not data['relay_configured']
    monkeypatch.setenv('INTERVIEW_TURN_URLS', 'https://not-a-turn-server.example')
    assert student.get(path).status_code == 503
