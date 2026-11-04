import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from tests.test_competition_api import source_data
from tests.test_decision import decision_input


def test_real_cli_normalizes_and_reproduces_decision():
    root = Path(__file__).resolve().parents[1]
    folder = root/'runtime'/'cli'/uuid.uuid4().hex
    folder.mkdir(parents=True)
    case, jobs, employment = decision_input()
    for name, value in [('source', source_data()), ('case', case), ('jobs', jobs), ('employment', employment)]:
        (folder/(name+'.json')).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def execute(arguments):
        result = subprocess.run([sys.executable, str(root/'scripts'/'research.py'), *map(str, arguments)],
                                cwd=root, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        assert result.returncode == 0, result.stderr

    for kind, name in [('recruitment', 'jobs'), ('employment', 'employment')]:
        execute(['normalize', '--source', folder/'source.json', '--kind', kind, '--input', folder/(name+'.json'), '--output', folder/(name+'-clean.json')])
    execute(['analyze', '--case', folder/'case.json', '--recruitment', folder/'jobs-clean.json',
             '--employment', folder/'employment-clean.json', '--output', folder/'result'])
    result = json.loads((folder/'result'/'result.json').read_text(encoding='utf-8'))
    assert result['result']['best']['action_ids'] == ['a']
    assert '培养调整方案' in (folder/'result'/'report.md').read_text(encoding='utf-8')
