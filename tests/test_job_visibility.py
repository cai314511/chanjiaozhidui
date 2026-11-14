import pytest

from tests.test_api import account, job_data, system


@pytest.mark.parametrize('flag', ['closed', 'deleted'])
def test_legacy_inactive_flags_hide_published_jobs_from_students(system, flag):
    employer = account(system, 'employer', 'visibility-company')
    student = account(system, 'student', 'visibility-student')
    job = employer.post('/api/jobs', json=job_data()).json()
    item = system.state.store.get(job['id'], 'job')
    system.state.store.save('job', item['owner'], {**item['data'], flag: True}, item['id'])
    assert all(j['id'] != item['id'] for j in student.get('/api/jobs').json())
    assert any(j['id'] == item['id'] for j in employer.get('/api/jobs').json())
    assert student.post('/api/applications', json={'job_id': item['id'], 'consent': True}).status_code == 409
