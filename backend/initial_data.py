import hashlib
import json
import secrets
from pathlib import Path

from backend.documents import extract
from backend.schemas import Profile
from backend.store import encode, now, password_hash, uid


SCHOOLS = [
    ('huachen', '华辰财经大学', '金融科技', '北京', ['林知远', '陈以宁', '许嘉禾', '周予安', '沈星澜'],
     ['金融产品研究', '风险数据分析', '金融科技产品经理', '智能投顾研究', '金融业务分析'],
     ['金融学原理', '计量经济学', 'Python金融数据分析', '金融风险管理', '金融产品设计']),
    ('qinglan', '青岚理工大学', '人工智能', '杭州', ['陆景行', '苏若溪', '程明川', '顾清和', '唐语桐'],
     ['AI应用开发', '数据工程', '机器学习工程', 'AI产品经理', '模型评估与测试'],
     ['高等数学', '程序设计基础', '数据库系统', '机器学习', '软件工程实践']),
    ('jiangchuan', '江川应用技术大学', '信息管理与信息系统', '南京', ['赵书言', '温予晴', '方致远', '叶思齐', '江亦辰'],
     ['数据运营', '业务流程分析', '产品运营', '信息系统实施', '用户研究'],
     ['管理学基础', '统计学', '信息系统分析', '数据可视化', '企业项目实践']),
]
SKILLS = ['Python', '数据分析', '产品设计', '沟通协作', 'SQL']
LEVELS = [[3.5,4,3,3.5,3],[3,4,2.5,3,4],[3,3.5,4,4,2.5],[4,3.5,3,3,3.5],[2.5,3,3.5,4,3]]
SCHOOL_OFFSETS = [[-.3,.3,.3,.1,-.2],[.7,.3,-.3,-.1,.5],[-.5,-.1,.4,.5,-.2]]


def initialize(store):
    marker = store.list('initialization')
    if marker:
        return {'created': False, 'students': 15, 'universities': 3}
    credentials = []
    documents = []
    entities = []
    users = []
    stamp = now()

    def account(username, name, role):
        ident, salt, password = uid(), secrets.token_hex(16), secrets.token_urlsafe(15)
        code = secrets.token_urlsafe(10) if role == 'university' else ''
        users.append((ident, username, name, role, salt, password_hash(password, salt), code, stamp))
        credentials.append({'username': username, 'password': password, 'name': name, 'role': role})
        return ident, code

    def save(kind, owner, data):
        ident = uid()
        entities.append((ident, kind, owner, encode(data), stamp, stamp))
        return ident

    def document(owner, name, text):
        content = text.encode('utf-8')
        if name.endswith('.json'):
            json.loads(text)
            data = extract(name+'.txt', content)
            data['name'] = name
        else:
            data = extract(name, content)
        ident = save('document', owner, data)
        documents.append((ident, content))

    account('admin', '系统管理员', 'admin')
    account('enterprise', '企业工作空间', 'employer')
    for school_index, (slug, school, major, city, names, careers, titles) in enumerate(SCHOOLS):
        university, code = account(slug, school, 'university')
        courses = []
        for index, title in enumerate(titles):
            courses.append({'id': f'{slug}-c{index+1}', 'name': title, 'credits': 4, 'hours': 64,
                            'category': 'general' if index == 0 else 'professional', 'protected': index == 0,
                            'teacher_hours': 64, 'lab_hours': 0 if index < 2 else 24,
                            'prerequisites': [f'{slug}-c2'] if index > 2 else []})
        directions = [{'id': f'{slug}-d{i+1}', 'name': career+'方向', 'job_category': career, 'capacity': 30,
                       'min_grade': 70+i*3, 'course_ids': [courses[2+i]['id']]} for i, career in enumerate(careers[:3])]
        program = {'code': slug, 'name': major+'专业核心课程培养方案', 'region': city, 'current_seats': 90,
                   'completion_rate': .96, 'pipeline_graduates': [85, 88, 86],
                   'current_direction_counts': {career: 30 for career in careers[:3]},
                   'skills': {skill: {'level': round(sum(level[i] for level in LEVELS)/5+SCHOOL_OFFSETS[school_index][i], 2), 'sample_count': 5,
                                      'evidence': '本校学生项目与课程能力自述汇总，待完成统一考核'} for i, skill in enumerate(SKILLS)},
                   'courses': courses, 'constraints': {'credits_min': 20, 'credits_max': 28, 'hours_min': 320, 'hours_max': 448,
                   'general_credits_min': 4, 'professional_credits_min': 16, 'teacher_hours_max': 480, 'lab_hours_max': 180, 'budget': 120000},
                   'directions': directions,
                   'groups': [{'id': f'{slug}-g{i+1}', 'count': 5, 'grade': 72+i*4,
                               'preferences': [d['id'] for d in directions[i:]+directions[:i]]} for i in range(3)],
                   'split_timing': '大二学年结束后，结合本人意愿与先修课程完成情况分流'}
        actions = [{'id': slug+'-practice', 'kind': 'add', 'reason': '增加跨课程项目，提高综合应用与团队协作能力',
                    'remove_ids': [], 'add_courses': [{'id': slug+'-c6', 'name': major+'综合实践', 'credits': 3, 'hours': 48,
                    'category': 'professional', 'protected': False, 'teacher_hours': 48, 'lab_hours': 36, 'prerequisites': [courses[2]['id']]}],
                    'cost': 36000, 'skill_delta': {'数据分析': .4, '沟通协作': .3},
                    'evidence': '依据项目目标提出的能力增益测算假设，实施后通过项目考核复核'}]
        from backend.competition_schemas import Program, Action
        Program.model_validate(program)
        for action in actions:
            Action.model_validate(action)
        save('university_profile', university, {'program': program, 'actions': actions})
        document(university, school+'培养方案配置.json', json.dumps({'program': program, 'actions': actions}, ensure_ascii=False, indent=2))
        document(university, school+'培养方案.md', '# '+school+'\n\n'+major+'专业\n\n'+
                 '\n'.join(f"- {c['name']}：{c['credits']}学分，{c['hours']}学时；先修：{'、'.join(c['prerequisites']) or '无'}" for c in courses)+
                 '\n\n师资课时上限480，实验室课时上限180，调整预算120000元。\n'+program['split_timing'])
        for index, name in enumerate(names):
            student, _ = account(f'{slug}.s{index+1}', name, 'student')
            project = f'{major}{["用户需求调研", "数据分析", "产品原型", "流程优化", "效果评估"][index]}项目'
            experience = (f'2025.09—2026.06｜{project}\n担任'+['项目负责人','数据分析成员','产品设计成员','流程研究成员','调研与测试成员'][index]+
                          '，完成问题定义、资料整理、方案比较与项目报告。\n'+
                          ['组织6次小组讨论，负责访谈提纲与需求优先级；形成12页方案报告。',
                           '清洗课程项目数据，使用Python与SQL完成分组统计，检查缺失值与重复记录。',
                           '绘制核心业务流程与交互原型，整理用户反馈，完成两次原型修订。',
                           '梳理业务流程中的交接节点，编写操作说明和异常处理清单。',
                           '制定测试任务与评价指标，记录使用问题并汇总改进建议。'][index])
            career = f'希望从事{careers[index]}，关注'+('金融业务与数据应用。' if school_index == 0 else '人工智能应用的可靠性与产品体验。' if school_index == 1 else '业务流程效率与用户体验。')
            profile = Profile(major=major, school_name=school, school_code=code, language='英语六级' if index % 2 == 0 else '英语四级',
                              career=career, experience=experience,
                              abilities={skill: {'level': round(LEVELS[index][i]+SCHOOL_OFFSETS[school_index][i], 2), 'evidence': f'{project}：课程项目自述，待测评复核'} for i, skill in enumerate(SKILLS)},
                              preferences={'salary_target': 10000+index*1000+school_index*500, 'cities': [city, '上海'] if city != '上海' else [city],
                                           'industries': ['金融科技'] if school_index == 0 else ['AI产品'] if school_index == 1 else ['AI产品','金融科技'],
                                           'work_modes': ['混合'] if index % 2 else ['现场','混合'], 'goals': [SKILLS[index], '数据分析'],
                                           'salary_hard': index == 1, 'city_hard': index == 3},
                              resources={'budget': 3000+index*1500, 'study_hours': 80+index*20, 'months': 4+index}).model_dump()
            profile['school_id'] = university
            save('profile', student, profile)
            resume = (f'# {name}｜个人简历\n\n## 教育背景\n{school}｜{major}｜本科｜2023.09—2027.06\n'+
                      f'核心课程：{"、".join(titles)}。语言：{profile["language"]}。\n\n## 职业目标\n{career}\n\n## 项目经历\n{experience}\n\n'+
                      f'## 实践经历\n2026.07—2026.08｜校内产教实践团队\n参与{careers[index]}专题任务，协助需求整理、资料核查和成果汇报。\n\n'+
                      '## 能力与工具\n'+ '\n'.join(f'- {skill}：{profile["abilities"][skill]["level"]}/5，依据为课程与项目自述，待复核。' for skill in SKILLS)+
                      f'\n\n## 个人安排\n意向城市：{"、".join(profile["preferences"]["cities"])}。目标月薪：{profile["preferences"]["salary_target"]}元。\n'+
                      f'可用于学习的预算{profile["resources"]["budget"]}元，预计投入{profile["resources"]["study_hours"]}课时，期限{profile["resources"]["months"]}个月。')
            document(student, name+'个人简历.md', resume)
    folder = store.root / 'files'
    folder.mkdir(exist_ok=True)
    for ident, content in documents:
        (folder / ident).write_bytes(content)
    # 来源只作为本地管理记录，不能据此声称真实个人、真实学校或实证效果。
    save('initialization', 'system', {'version': 1, 'origin': 'synthetic_authored', 'students': 15, 'universities': 3})
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM entities WHERE kind='initialization'").fetchone():
            raise ValueError('初始化已完成，请重新读取')
        for item in users:
            if db.execute('SELECT 1 FROM users WHERE username=?', (item[1],)).fetchone():
                raise ValueError('初始化账号名称已存在：'+item[1])
        db.executemany('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)', users)
        db.executemany('INSERT INTO entities VALUES(?,?,?,?,?,?)', entities)
    credential_file = store.root / 'account-access.json'
    credential_file.write_text(json.dumps(credentials, ensure_ascii=False, indent=2), encoding='utf-8')
    store.audit('system', 'initialize_workspaces', 'version-1')
    return {'created': True, 'students': 15, 'universities': 3, 'access_file': str(credential_file)}
