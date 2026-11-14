"""报告快照的输入版本；读取时比较，不更新历史测算。"""
import hashlib
import json


def fingerprint(value):
    content = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def workspace_input_fingerprint(data):
    """仅为实际培养输入做摘要，排除导航、计算结果和记录关联。"""
    excluded = {'step', 'id', 'version', 'result', 'optimization_id', 'ai_suggestions', 'teaching_suggestions'}
    inputs = {key: value for key, value in data.items() if key not in excluded}
    if isinstance(inputs.get('advanced'), dict):
        inputs['advanced'] = {key: value for key, value in inputs['advanced'].items()
                              if key not in {'case_id', 'run_id', 'enabled'}}
    return fingerprint(inputs)


def report_source_versions(store, owner, case, provenance):
    program = case.get('program', {})
    catalogs = store.list('university_course_catalog', owner)
    profiles = store.list('university_profile', owner)
    versions = {
        'courses': fingerprint(program.get('courses', [])),
        'actions': fingerprint(case.get('actions', [])),
        'resources': fingerprint(program.get('constraints', {})),
        'program': fingerprint({k: v for k, v in program.items() if k not in {'courses', 'constraints'}}),
        'demand': fingerprint({'recruitment_id': case.get('recruitment_id'),
                               'employment_id': case.get('employment_id'),
                               'evidence': [{'id': p.get('dataset_id'), 'sha256': p.get('sha256')}
                                            for p in provenance]}),
        'catalog': fingerprint(catalogs[0]['data'] if catalogs else None),
        'profile': fingerprint(profiles[0]['data'] if profiles else None),
        'assumptions': fingerprint({k: v for k, v in case.items() if k not in {'program', 'actions'}}),
    }
    if case.get('workspace_id'):
        versions['workspace'] = {'id': case['workspace_id'], 'input_hash': case.get('workspace_input_hash')}
    return versions


def check_report_versions(store, owner, saved):
    data = saved['data']
    if saved['kind'] == 'optimization':
        workspace_id = data.get('workspace_id')
        workspace = store.get(workspace_id, 'university_workspace') if workspace_id else None
        if workspace and workspace['owner'] == owner:
            previous = data.get('workspace_version')
            current = workspace['data'].get('version')
            if data.get('workspace_input_hash'):
                previous = data['workspace_input_hash']
                current = workspace_input_fingerprint(workspace['data'])
            changes = ([{'id': 'workspace', 'label': '培养方案工作区', 'before': previous, 'current': current}]
                       if previous != current else [])
            catalogs = store.list('university_course_catalog', owner)
            catalog = fingerprint(catalogs[0]['data'] if catalogs else None)
            original_catalog = data.get('source_versions', {}).get('catalog')
            if original_catalog and original_catalog != catalog:
                changes.append({'id': 'catalog', 'label': '全校课程库', 'before': original_catalog, 'current': catalog})
            return {'stale': bool(changes), 'changes': changes, 'unknown': [],
                    'token': fingerprint({'workspace': workspace_id, 'version': current, 'catalog': catalog})}
        return {'stale': False, 'changes': [], 'unknown': ['该历史优化未记录工作区版本'], 'token': None}
    case = data.get('case', {})
    current_case = store.get(data.get('case_id'), 'decision_case') if data.get('case_id') else None
    if current_case and current_case['owner'] != owner:
        current_case = None
    current_case = current_case['data'] if current_case else case
    provenance = []
    saved_sources = {source.get('dataset_id'): source for source in data.get('provenance', [])}
    ids = [current_case.get('recruitment_id'), current_case.get('employment_id'), *current_case.get('policy_ids', [])]
    for ident in filter(None, ids):
        item = store.get(ident, 'research_dataset')
        source = saved_sources.get(ident)
        if item and item['owner'] == owner:
            provenance.append({'dataset_id': ident, 'sha256': item['data']['sha256']})
        elif source:
            provenance.append(source)
    current = report_source_versions(store, owner, current_case, provenance)
    if case.get('workspace_id'):
        workspace = store.get(case['workspace_id'], 'university_workspace')
        current['workspace'] = {'id': case['workspace_id'],
                                'input_hash': workspace_input_fingerprint(workspace['data'])
                                if workspace and workspace['owner'] == owner else None}
    previous = data.get('source_versions')
    unknown = []
    if not previous:
        previous = report_source_versions(store, owner, case, data.get('provenance', []))
        previous.pop('catalog', None)
        previous.pop('profile', None)
        unknown = ['历史测算未记录课程库和本校配置版本；保留原始测算快照']
    labels = {'courses': '专业课程', 'actions': '培养项目与课程动作', 'resources': '预算与教学资源',
              'demand': '岗位需求证据', 'catalog': '全校课程库', 'profile': '本校培养配置',
              'program': '专业目标与能力基线', 'assumptions': '情景假设', 'workspace': '培养方案工作区输入'}
    changes = [{'id': key, 'label': labels[key], 'before': value, 'current': current.get(key)}
               for key, value in previous.items() if key in labels and value != current.get(key)]
    return {'stale': bool(changes), 'changes': changes, 'unknown': unknown, 'token': fingerprint(current)}
