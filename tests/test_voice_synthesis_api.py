"""用隔离平台能力复现 Linux 缺少 SAPI，保留实际接口与鉴权。"""
import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend import voice
from tests.test_api import account, system


def test_linux_reports_device_speech_without_generic_value_error(system, monkeypatch):
    monkeypatch.setattr(voice, 'os', SimpleNamespace(name='posix', getenv=os.getenv))
    client = account(system, 'student', 'linux-speech-api')
    assert client.get('/api/voice/status').json()['synthesis_ready'] is False
    response = client.post('/api/voice/speak', json={'text': '你好'})
    assert response.status_code == 503
    assert '浏览器设备' in response.json()['detail']
    assert 'ValueError' not in response.json()['detail']
    assert TestClient(system).post('/api/voice/speak', json={'text': '你好'}).status_code == 401


def test_blank_speech_is_invalid_input(system):
    client = account(system, 'student', 'blank-speech-api')
    response = client.post('/api/voice/speak', json={'text': '   '})
    assert response.status_code == 422
    assert '文字长度' in response.json()['detail']
