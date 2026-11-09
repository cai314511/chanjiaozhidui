from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient

import backend.app as application
from tests.test_api import job_data


def test_saving_weights_preserves_concurrent_pause(tmp_path, monkeypatch):
    app=application.create_app(tmp_path/'formal')
    with TestClient(app) as client:
        client.post('/api/auth/register',json={'username':'parallel-company','password':'long-password-123','name':'企业','role':'employer'})
        spec=job_data()
        created=client.post('/api/jobs',json=spec).json()
        entered,release=Event(),Event()
        original=application.normalized

        def controlled_normalize(weights):
            result=original(weights)
            entered.set()
            assert release.wait(10)
            return result

        monkeypatch.setattr(application,'normalized',controlled_normalize)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(client.put,'/api/jobs/'+created['id']+'/weights',json={'version':1,'weights':{r['skill']:1 for r in spec['requirements']}})
            assert entered.wait(10)
            try:
                assert client.post('/api/recruiting/jobs/'+created['id']+'/status',json={'status':'paused'}).status_code==200
            finally:
                release.set()
            assert future.result(timeout=15).status_code==200
        assert client.get('/api/jobs').json()[0]['status']=='paused'
