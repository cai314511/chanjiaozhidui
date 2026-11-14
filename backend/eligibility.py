"""毕业与学历资格：自报信息和企业材料核验分开处理。"""


def qualification(job, profile, background=None):
    background = background or {}
    checks = []
    for key, label, required in (
        ('graduation_month', '毕业年月', [job.get('graduation_from'), job.get('graduation_to')]),
        ('degree', '学历', job.get('degrees', [])),
        ('academic_status', '学业状态', job.get('academic_statuses', [])),
    ):
        if not any(required):
            continue
        actual = profile.get(key, '')
        fits = (not required[0] or actual >= required[0]) and (not required[1] or actual <= required[1]) if key == 'graduation_month' else actual in required
        status = 'fail' if actual and not fits else 'pass' if actual and background.get(key) is True else 'pending'
        reason = f'{label}不在岗位要求范围' if status == 'fail' else f'{label}已由企业核验' if status == 'pass' else f'{label}为学生自报，待核验' if actual else f'尚未填写{label}'
        checks.append({'key': key, 'label': label, 'status': status, 'required': required, 'actual': actual,
                       'verified': background.get(key) is True, 'reason': reason})
    status = 'excluded' if any(c['status'] == 'fail' for c in checks) else 'pending' if any(c['status'] == 'pending' for c in checks) else 'eligible'
    return {'status': status, 'checks': checks, 'reasons': [c['reason'] for c in checks], 'source': '学生自报；企业逐项核验'}


def validate_job_publish(data):
    """已发布岗位的必要能力都有可复核的评分路径。"""
    from fastapi import HTTPException
    if data.get('status', 'published') != 'published':
        return
    covered = {q['skill'] for q in data.get('questions', []) if q.get('title', '').strip() and q.get('rubric', '').strip()}
    missing = [r['skill'] for r in data.get('requirements', []) if r.get('mandatory') and r['skill'] not in covered]
    if missing:
        raise HTTPException(422, '发布前请为以下能力配置题目和评分标准：' + '、'.join(missing))
