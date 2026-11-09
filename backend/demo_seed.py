"""独立体验空间的可重复初始化；所有人物、业务记录均为独立编写。"""
import gzip
import json
from pathlib import Path

from backend.documents import extract
from backend.initial_data import initialize, SKILLS
from backend.schemas import Job
from backend.store import encode, now


REFERENCE = Path(__file__).resolve().parents[1] / 'data/demo-reference/reference.json.gz'


def seed_workspace(store):
    initialize(store)
    with store.connect() as db:
        accounts = {r['username']: dict(r) for r in db.execute('SELECT * FROM users')}
        main = {role: accounts[name]['id'] for role, name in
                [('student', 'huachen.s1'), ('employer', 'enterprise'), ('university', 'huachen')]}
        db.executemany('UPDATE users SET name=? WHERE id=?', [('蔡雨轩', ident) for ident in main.values()])
    stamp = now()
    company = '星澜数智科技'
    store.save('company_profile', main['employer'], {'name': company, 'tracks': ['人工智能', '金融科技', '数字内容'],
               'city': '北京', 'description': '面向金融研究和数字内容团队，提供智能体产品、数据分析和AI视频工作流服务。中央财经大学产教协作项目组。'}, 'demo-company')
    profiles = store.list('profile')
    for i, item in enumerate(profiles):
        profile = item['data']
        if item['owner'] == main['student']:
            profile.update(school_name='中央财经大学', major='经济学',
                           career='希望从事AI产品、投研智能体和AI视频工作流相关岗位。',
                           experience='AI视频产品实习：梳理多角色短视频制作流程，设计素材管理、脚本评审与效果复盘功能。\n投研AI智能体产品实习：完成行业研报检索、引用核查和研究工作流的产品原型。')
        profile['school_id'] = main['university']
        profile['school_code'] = accounts['huachen']['school_code']
        profile['school_name'] = '中央财经大学'
        store.save('profile', item['owner'], profile, item['id'])
        store.save('market_exploration',item['owner'],{'seen':True,'answers':{'environment':['金融与商业'],'interests':['技术与创造'],'tasks':['分析数据和规律']},'text':'关注AI产品、投研智能体和数字内容工作流。'},'exploration-'+item['owner'])
        store.save('market_favorite',item['owner'],{'type':'track','target_id':'金融科技','name':'金融科技'},'track-favorite-'+item['owner'])
        with store.connect() as db:
            user = db.execute('SELECT name FROM users WHERE id=?', (item['owner'],)).fetchone()
        name = user['name']
        resume = '# ' + name + '\n\n中央财经大学｜' + profile['major'] + '｜本科\n\n' + profile['experience'] + '\n\n职业目标：' + profile['career']
        for previous in store.list('document',item['owner']):
            text='# '+name+'｜项目经历\n\n'+profile['experience']
            store.save('document',item['owner'],extract(name+'项目经历.md',text.encode()),previous['id'])
            (store.root/'files'/previous['id']).write_text(text,encoding='utf-8')
        document_id = 'resume-' + item['owner']
        store.save('document', item['owner'], extract(name + '个人简历.md', resume.encode()), document_id)
        (store.root / 'files' / document_id).write_text(resume, encoding='utf-8')
        works = []
        for k, (title, content) in enumerate([
            ('AI视频工作流产品方案', '目标：为内容团队连接选题、脚本、分镜、素材和复盘。\n核心设计：任务拆解、角色分工、版本比较、人工审核。\n交付：产品需求说明、工作流配置、指标看板。'),
            ('投研智能体产品设计', '目标：把产业资料检索、证据摘录与报告整理连接起来。\n核心设计：引用溯源、资料权限、研究任务编排、结果复核。\n交付：交互原型、检索评价表、异常处理流程。'),
        ]):
            ident = f'work-{i}-{k}'
            body = (title + '\n\n' + content).encode()
            store.save('portfolio', item['owner'], {'name': title+'.txt', 'mime': 'text/plain', 'size': len(body)}, ident)
            (store.root / 'portfolio').mkdir(exist_ok=True)
            (store.root / 'portfolio' / ident).write_bytes(body)
            works.append(ident)
        if item['owner']==main['student']:
            for slug,title in [('video-workflow','AI视频工作流产品方案图'),('research-agent','投研智能体产品方案图')]:
                asset=Path(__file__).resolve().parents[1]/'web/demo-portfolio'/(slug+'.png')
                if asset.is_file():
                    ident='portfolio-'+slug
                    content=asset.read_bytes()
                    store.save('portfolio',item['owner'],{'name':title+'.png','mime':'image/png','bytes':len(content)},ident)
                    (store.root/'portfolio'/ident).write_bytes(content)
                    works.append(ident)
        page = {'display_name': name, 'school': '中央财经大学', 'major': profile['major'], 'education': '本科在读',
                'headline': ['AI产品与金融研究', '数据分析与产品设计', '智能体应用与工程实践'][i % 3],
                'bio': profile['career'], 'background': profile['experience'], 'interests': ['人工智能', '金融科技', '数字内容'],
                'strengths': ['Python', '数据分析', '产品设计'], 'links': [], 'document_ids': [document_id], 'portfolio_ids': works}
        store.save('student_page', item['owner'], {'draft': page, 'published': {**page, 'published_at': stamp}}, 'student_page:'+item['owner'])
    titles = ['AI产品经理', '投研智能体产品实习生', 'AI视频工作流工程师', '金融数据分析师', 'Python应用开发', '用户研究实习生', '产品运营专员', '机器学习工程师']
    for i, title in enumerate(titles):
        data = Job(title=title, industry='金融科技' if i % 2 else '人工智能', city='北京' if i % 3 else '上海',
                   salary_min=6000+i*1500, salary_max=10000+i*2000, capacity=3+i % 4,
                   work_mode='混合', description='参与智能体与数据产品建设，负责需求梳理、方案设计和项目交付。\n与研究、设计和研发团队协作，关注可追溯证据与用户体验。',
                   training_cost=2000, mentor_hours=12,
                   requirements=[{'skill': skill, 'target': 3+(i+j) % 3*.5, 'weight': 1+j, 'category': '专业能力'} for j, skill in enumerate(SKILLS)],
                   questions=[{'id': 'scenario', 'title': '如何设计一个可核对引用来源的研究助手？', 'skill': '产品设计', 'rubric': '说明用户任务、数据来源、异常处理与验证方法。', 'kind': 'scenario'}]).model_dump()
        data.update(company=company, version=1, status='published' if i<5 else ['paused','draft','closed'][i-5])
        store.save('job', main['employer'], data, 'demo-job-'+str(i))
        text='# '+title+'\n\n'+data['description']+'\n\n工作城市：'+data['city']+'\n\n能力要求：'+'、'.join(SKILLS)
        ident='jd-'+str(i)
        store.save('document',main['employer'],extract(title+'岗位说明.md',text.encode()),ident)
        (store.root/'files'/ident).write_text(text,encoding='utf-8')
        with store.connect() as db:
            db.execute('INSERT INTO job_versions VALUES(?,?,?,?)', ('demo-job-'+str(i), 1, encode(data), stamp))
    for i, item in enumerate(profiles):
        for j in range(3):
            job_id = 'demo-job-'+str((i+j) % 5)
            docs = ['resume-'+item['owner']]
            review = {'abilities': item['data']['abilities'], 'background': {}, 'reviewed_at': stamp} if i % 3 else None
            store.save('application', item['owner'], {'job_id': job_id, 'consent': True, 'document_ids': docs,
                       'portfolio_ids': [f'work-{i}-0'], 'withdrawn': False, 'student_chosen': True,
                       'employer_chosen': i % 4 == 0, 'answers': {'scenario': '先定义研究任务，再约束资料来源，生成后逐条检查引用和关键数据。'},
                       'audio_ids': [], 'review': review, 'stage': ['new','reviewing','interview','offer'][i % 4]}, f'application-{i}-{j}')
    school = store.list('university_profile', main['university'])[0]
    for document in store.list('document',main['university']):
        previous=document['data']
        name=previous['name'].replace('华辰财经大学','中央财经大学')
        body='\n'.join(b['text'] for b in previous.get('blocks',[])).replace('华辰财经大学','中央财经大学')
        if name.endswith('.json'):
            data=extract(name+'.txt',body.encode());data['name']=name
        else:data=extract(name,body.encode())
        store.save('document',main['university'],data,document['id'])
        (store.root/'files'/document['id']).write_text(body,encoding='utf-8')
    program = school['data']['program']
    courses = []
    for i, c in enumerate(program['courses']):
        tags = [SKILLS[i % len(SKILLS)], SKILLS[(i+1) % len(SKILLS)]]
        courses.append({'code': c['id'], 'name': c['name'], 'credits': c['credits'], 'hours': c['hours'], 'skills': tags})
    store.save('university_profile', main['university'], school['data'], school['id'])
    store.save('university_course_catalog', main['university'], {'courses': courses, 'sources': [{'name':'中央财经大学课程目录.csv','kind':'courses','imported_at':stamp}]}, 'demo-courses')
    seed_plans(store,main,school['data'])
    import hashlib
    for item in profiles:
        sid=item['owner']
        ident='conversation-'+hashlib.sha256((main['employer']+':'+sid).encode()).hexdigest()
        store.save('conversation',main['employer'],{'participants':[main['employer'],sid]},ident)
        store.save('direct_message',ident,{'sender':main['employer'],'text':'你好，我们看过你的项目经历，希望进一步交流智能体产品岗位。'})
        store.save('direct_message',ident,{'sender':sid,'text':'感谢关注，我可以介绍AI视频工作流和投研助手项目的设计过程。'})
        if sid==main['student']:
            favorite='candidate-star-'+hashlib.sha256((main['employer']+':'+sid).encode()).hexdigest()
            store.save('candidate_favorite',main['employer'],{'student_id':sid},favorite)
    # 仅复制公开比赛资料的白名单聚合；不复制正式账号、学生资料、文件或会话。
    from backend.reference_data import import_reference
    import_reference(store)
    store.save('demo_manifest', 'system', {'version': 1, 'origin': 'synthetic_authored', 'main': main}, 'demo-manifest')
    return main


def seed_plans(store, main, school):
    from backend.matching import optimize_courses
    from backend.competition_schemas import DecisionCase
    from backend.decision import run_decision
    from backend.governance import clean_records
    import hashlib
    gaps={'Python':1.2,'产品设计':1,'数据分析':.8}
    weights={k:1 for k in gaps}
    courses=[{'id':'practice-'+str(i),'name':name,'cost':cost,'credits':2,'teacher_hours':24,
              'lab_hours':12,'study_hours':32,'months':2,'gains':{k:(.7 if j==i else .2) for j,k in enumerate(gaps)}}
             for i,(name,cost) in enumerate([('智能体产品实训',1200),('AI视频工作流实践',1500),('金融数据分析专题',1000)])]
    for owner in [main['student'],main['university']]:
        limits={'cost':5000,'credits':8,'teacher_hours':100,'lab_hours':60,'study_hours':120,'months':4}
        own_courses=[dict(c) for c in courses]
        if owner==main['student']:
            profile=store.list('profile',owner)[0]['data']
            limits.update(cost=profile['resources']['budget'],study_hours=profile['resources']['study_hours'],months=profile['resources']['months'],credits=0,teacher_hours=0,lab_hours=0)
            for course in own_courses:course.update(credits=0,teacher_hours=0,lab_hours=0)
        result=optimize_courses(gaps,weights,own_courses,limits)
        store.save('learning_plan' if owner==main['student'] else 'optimization',owner,{'input':{'gaps':gaps,'weights':weights,'courses':own_courses,'limits':limits},'result':result},'plan-'+owner)
    source={'title':'校企岗位与课程协同研究','url':'','reference':'校企实践项目岗位与课程方案','collected_at':now()[:10],
            'method':'internal_aggregate','license_basis':'当前空间内编写的岗位与课程方案，仅用于流程体验',
            'research_permitted':True,'contains_personal_data':False,'redaction_reviewed':True,
            'split':'development','scope':'当前空间内校企合作培养方案的情景测算',
            'declaration':'岗位与培养过程的情景输入，由操作人确认后用于测算','origin':'synthetic_authored'}
    store.save('research_source',main['university'],source,'demo-research-source')
    categories=[d['job_category'] for d in school['program']['directions']]
    recruitment=[{'record_id':'rec-'+str(i),'title':cat,'industry':'金融科技','category':cat,'region':'北京',
                  'month':now()[:7],'salary_min':8000,'salary_max':15000,'verified_headcount':30,
                  'headcount_evidence':'当前情景设定的校企合作年度计划名额',
                  'skills':[{'name':skill,'level':4,'weight':1} for skill in SKILLS]} for i,cat in enumerate(categories)]
    employment=[{'program_code':school['program']['code'],'year':2025,'graduates':90,'employed':78,
                 'related_employed':63,'average_salary':8500,'salary_sample':60}]
    provenance=[]
    for ident,kind,records in [('demo-recruitment','recruitment',recruitment),('demo-employment','employment',employment)]:
        records,processing=clean_records(kind,records)
        digest=hashlib.sha256(encode(records).encode()).hexdigest()
        data={'source_id':'demo-research-source','kind':kind,'records':records,'split':'development',
              'processing':processing,'sha256':digest,'original_sha256':digest,'source_snapshot':source,
              'immutable':True,'record_fingerprints':[]}
        store.save('research_dataset',main['university'],data,ident)
        provenance.append({'dataset_id':ident,'sha256':digest,'source':source,'processing':processing})
    case=DecisionCase(title='经济与金融科技专业培养方案协同优化',recruitment_id='demo-recruitment',employment_id='demo-employment',
                      program=school['program'],actions=school['actions'],admissions={'min_seats':60,'max_seats':120},
                      scenarios=[{'name':name,'demand_growth':growth,'salary_growth':growth,'skill_gain_factor':factor,'probability':prob}
                                 for name,growth,factor,prob in [('乐观',.05,1.1,.2),('基准',0,1,.6),('悲观',-.05,.7,.2)]],
                      assumptions='课程能力增益及年度合作计划为情景假设，实施后按课程考核和毕业跟踪更新。',
                      market_scope_confirmed=True,annual_demand_confirmed=True,skill_employment_elasticity=.2).model_dump()
    store.save('decision_case',main['university'],case,'demo-decision-case')
    result=run_decision(case,recruitment,employment)
    store.save('decision_run',main['university'],{'case_id':'demo-decision-case','case':case,'result':result,
               'provenance':provenance,'policy_use':'按课程考核与招聘计划进行情景测算'},'demo-decision-run')
