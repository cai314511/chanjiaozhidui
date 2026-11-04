import io
import wave
from pathlib import Path

from backend.voice import status, synthesize, transcribe


def test_real_local_chinese_synthesis_and_recognition():
    root = Path(__file__).resolve().parents[1] / 'runtime' / 'voice-verification'
    root.mkdir(parents=True, exist_ok=True)
    assert status()['recognition_ready']
    audio = synthesize('你好，请介绍你最近完成的一个项目。', root)
    with wave.open(io.BytesIO(audio)) as stream:
        assert stream.getnframes() > stream.getframerate()
    result = transcribe(audio)
    assert result['local']
    assert '项目' in result['text'], result
    assert result['duration'] > 1


def test_local_silence_returns_no_fabricated_text():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(bytes(32000))
    assert transcribe(buffer.getvalue())['text'] == ''
