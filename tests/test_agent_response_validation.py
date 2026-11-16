"""格式故障由明确的模型响应替身注入，不代表真实服务结果。"""
import pytest
from backend import agent


def install_responses(monkeypatch, contents):
    calls = []

    class Response:
        status_code = 200

        def __init__(self, content):
            self.content = content

        def json(self):
            return {'choices': [{'message': {'content': self.content}}]}

    class Client:
        def __init__(self, **options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **options):
            calls.append(options['json'])
            return Response(contents[len(calls) - 1])

    monkeypatch.setattr(agent, 'configuration', lambda: {'key': 'isolated', 'model': 'isolated', 'base': 'https://isolated.invalid'})
    monkeypatch.setattr(agent.httpx, 'Client', Client)
    return calls


def test_malformed_final_response_has_one_explicit_format_repair(monkeypatch):
    calls = install_responses(monkeypatch, ['not-json', '{"message":"格式已修正，仍需补充岗位资料","draft":null}'])
    result = agent.run_agent('整理岗位', {'role': 'employer', 'mode': 'job'})
    assert result['message'].startswith('格式已修正')
    assert result['draft'] is None
    assert result['format_repaired'] is True
    assert len(calls) == 2


def test_second_invalid_response_remains_failure_without_fake_draft(monkeypatch):
    calls = install_responses(monkeypatch, ['not-json', '{"message":null}'])
    with pytest.raises(agent.AgentError, match='校验'):
        agent.run_agent('整理岗位', {'role': 'employer', 'mode': 'job'})
    assert len(calls) == 2
