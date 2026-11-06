from fastapi.testclient import TestClient

from backend.app import create_app
from tests.test_api import job_data


def test_enterprise_registers_multiple_tracks_and_posts_other_industry(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response = client.post('/api/auth/register', json={'username': 'multi-company', 'password': 'test-password-123',
            'name': '隔离新能源企业', 'role': 'employer', 'company_tracks': ['新能源汽车', '新能源']})
        assert response.status_code == 200
        assert client.get('/api/company/profile').json()['tracks'] == ['新能源汽车', '新能源']
        result = client.post('/api/jobs', json={**job_data(), 'industry': '新能源汽车'})
        assert result.status_code == 200
        assert result.json()['industry'] == '新能源汽车'
