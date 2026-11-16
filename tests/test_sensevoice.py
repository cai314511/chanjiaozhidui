"""配置与故障分支使用隔离文件/推理替身；真实权重另做实际转写验收。"""
import io
import wave

import numpy as np
import pytest

from backend import voice


def local_model(tmp_path, monkeypatch):
    for name in ('model.pt', 'config.yaml', 'configuration.json', 'tokens.json',
                 'chn_jpn_yue_eng_ko_spectok.bpe.model', 'am.mvn'):
        (tmp_path / name).write_text('isolated test fixture')
    monkeypatch.setenv('CHZ_ASR_MODEL', str(tmp_path))
    return tmp_path


def test_sensevoice_config_resolves_from_project_and_has_accurate_status(tmp_path, monkeypatch):
    path = local_model(tmp_path, monkeypatch)
    monkeypatch.setattr(voice, '_model', None)
    assert voice.model_spec() == ('sensevoice', path)
    state = voice.status()
    assert state['recognition_ready']
    assert 'SenseVoiceSmall' in state['recognition']
    assert state['recognition_loaded'] is False


def test_incomplete_explicit_model_does_not_silently_use_whisper(tmp_path, monkeypatch):
    monkeypatch.setenv('CHZ_ASR_MODEL', str(tmp_path))
    assert voice.status()['recognition_ready'] is False
    assert voice.status()['recognition_error']
    with pytest.raises(ValueError, match='模型'):
        voice.model_spec()


def test_legacy_whisper_directory_remains_supported(tmp_path, monkeypatch):
    monkeypatch.delenv('CHZ_ASR_MODEL', raising=False)
    monkeypatch.setenv('CHZ_WHISPER_MODEL', str(tmp_path))
    for name in ('model.bin', 'config.json', 'tokenizer.json'):
        (tmp_path / name).write_text('isolated test fixture')
    assert voice.model_spec() == ('whisper', tmp_path)


def test_sensevoice_chunking_strips_metadata_and_uses_fresh_cache():
    class IsolatedModel:
        def __init__(self):
            self.calls = []

        def generate(self, **kwargs):
            self.calls.append(kwargs)
            return [{'text': '<|zh|><|NEUTRAL|><|Speech|>你好，世界。<|withitn|>'}]

    model = IsolatedModel()
    text = voice._sensevoice_text(model, np.ones(65 * 16000, dtype=np.float32))
    assert '<|' not in text
    assert text.count('你好') == 3
    assert [len(call['input']) for call in model.calls] == [30 * 16000, 30 * 16000, 5 * 16000]
    assert len({id(call['cache']) for call in model.calls}) == 3


def test_invalid_model_response_is_not_false_success():
    class IsolatedInvalidModel:
        def generate(self, **kwargs):
            return [{'wrong': 'not a transcription'}]

    with pytest.raises(voice.VoiceUnavailable):
        voice._sensevoice_text(IsolatedInvalidModel(), np.ones(16000, dtype=np.float32))


def test_model_initialization_failure_becomes_service_error(tmp_path, monkeypatch):
    local_model(tmp_path, monkeypatch)
    monkeypatch.setattr(voice, '_model', None)

    def failed_loader(engine, path):
        raise RuntimeError('isolated simulated model failure')

    monkeypatch.setattr(voice, '_load_model', failed_loader)
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes((np.sin(np.arange(16000) * .1) * 12000).astype('<i2').tobytes())
    with pytest.raises(voice.VoiceUnavailable):
        voice.transcribe(buffer.getvalue())


def test_model_relative_path_is_resolved_against_project(tmp_path, monkeypatch):
    model = tmp_path / 'models' / '本地语音'
    model.mkdir(parents=True)
    local_model(model, monkeypatch)
    monkeypatch.setattr(voice, 'ROOT', tmp_path)
    monkeypatch.setenv('CHZ_ASR_MODEL', 'models/本地语音')
    monkeypatch.chdir(tmp_path.parent)
    assert voice.model_spec() == ('sensevoice', model)


def test_inference_error_returns_503_and_rejects_unauthenticated_audio(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app import create_app

    def unavailable(content):
        raise voice.VoiceUnavailable('隔离模拟本地模型不可用')

    monkeypatch.setattr(voice, 'transcribe', unavailable)
    with TestClient(create_app(tmp_path / 'service-failure')) as client:
        files = {'file': ('audio.wav', b'isolated-invalid-audio', 'audio/wav')}
        assert client.post('/api/voice/transcribe', files=files).status_code == 401
        assert client.post('/api/auth/register', json={
            'username': 'sensevoice-failure', 'password': 'isolated-voice-1234',
            'name': '隔离测试', 'role': 'student'}).status_code == 200
        response = client.post('/api/voice/transcribe', files=files)
        assert response.status_code == 503
        assert '本地模型不可用' in response.json()['detail']
