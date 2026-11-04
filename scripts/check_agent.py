import json
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from backend.app import create_app


def main():
    client = TestClient(create_app(ROOT / 'runtime' / 'agent-check' / uuid.uuid4().hex))
    client.post('/api/auth/register', json={'username': 'voice-verification', 'password': 'verification-12345',
                                          'name': '隔离验收账号', 'role': 'student'}).raise_for_status()
    session = client.post('/api/interviews', json={'mode': 'profile'}).json()
    spoken = client.post('/api/voice/speak', json={'text': '你好，请介绍你最近完成的一个项目。'})
    spoken.raise_for_status()
    recognition = client.post('/api/voice/transcribe', files={'file': ('question.wav', spoken.content, 'audio/wav')})
    recognition.raise_for_status()
    response = client.post('/api/interviews/' + session['id'] + '/turn', json={
        'revision': session['revision'], 'consent': True,
        'text': '以下是功能验收的虚构项目输入，不是个人经历：课程项目中负责整理访谈，发现同学找实习信息分散，整理了岗位信息表。请就具体行动追问一个问题。'})
    if response.status_code != 200:
        raise RuntimeError(response.text)
    reply = response.json()['messages'][-1]['text']
    audio = client.post('/api/voice/speak', json={'text': reply[:1800]})
    audio.raise_for_status()
    result = client.get('/api/agent/history').json()[0]['result']
    result['voice_verification'] = {'recognition': recognition.json(), 'synthesized_bytes': len(audio.content),
                                    'input_scope': '隔离验收的虚构项目文本，不是实证或真人麦克风验收'}
    folder = ROOT / "outputs"
    folder.mkdir(exist_ok=True)
    path = folder / "agent-verification.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"real_model_call": result["real_model_call"], "model": result["model"], "tools": result["trace"], "elapsed": result["elapsed"], "output": str(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
