"""真实 Edge 访问隔离服务，验证主页发布、授权资源和移动布局。"""

import socket
import threading
import time
import uuid
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import pytest
import uvicorn
from PIL import Image
from playwright.sync_api import expect, sync_playwright

from backend.app import create_app
from tests.test_browser import register, route


@pytest.fixture(scope='module')
def student_space_browser():
    root = Path(__file__).resolve().parents[1] / 'runtime' / 'student-space-browser' / uuid.uuid4().hex
    app = create_app(root)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        thread.join(.05)
    assert server.started
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            yield browser, f'http://127.0.0.1:{sock.getsockname()[1]}', root
            browser.close()
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()


def image_bytes():
    output = BytesIO()
    Image.new('RGB', (96, 96), '#2c806b').save(output, format='PNG')
    return output.getvalue()


def record_video(page):
    # 由真实浏览器编码一段可播放的测试视频，不使用伪装后缀的字节。
    return bytes(page.evaluate('''async () => {
        const canvas=document.createElement('canvas');canvas.width=160;canvas.height=100;
        canvas.style.position='fixed';canvas.style.left='0';canvas.style.top='0';
        document.body.append(canvas);
        const ctx=canvas.getContext('2d');ctx.fillRect(0,0,160,100);
        const stream=canvas.captureStream(0),track=stream.getVideoTracks()[0];
        const recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8'}),chunks=[];
        recorder.ondataavailable=event=>{if(event.data.size)chunks.push(event.data)};
        const finished=new Promise(resolve=>recorder.onstop=resolve);
        recorder.start();
        for(let index=0;index<12;index++){
            ctx.fillStyle=index%2?'#2c806b':'#c2a553';ctx.fillRect(0,0,160,100);
            ctx.fillStyle='#ffffff';ctx.fillRect(index*10,30,20,40);track.requestFrame();
            await new Promise(resolve=>setTimeout(resolve,80));
        }
        recorder.stop();await finished;stream.getTracks().forEach(track=>track.stop());
        canvas.remove();
        return Array.from(new Uint8Array(await new Blob(chunks).arrayBuffer()));
    }'''))


def expect_video_ready(page):
    video = page.locator('#modal video')
    source = video.get_attribute('src')
    response = page.request.get(urljoin(page.url, source))
    assert response.status == 200, response.text()
    try:
        page.wait_for_function('()=>document.querySelector("#modal video").readyState>=1', timeout=5000)
        video.evaluate('(element)=>{element.muted=true;return element.play();}')
        page.wait_for_function('()=>document.querySelector("#modal video").currentTime>0', timeout=5000)
        video.evaluate('(element)=>element.pause()')
    except Exception as error:
        details = video.evaluate('(v)=>({error:v.error?.message,code:v.error?.code,ready:v.readyState,network:v.networkState,src:v.currentSrc})')
        raise AssertionError(f'视频未加载：{details}; bytes={len(response.body())}') from error


def test_student_home_upload_publish_three_roles_following_and_withdraw(student_space_browser):
    browser, base, root = student_space_browser
    errors = []
    employer = browser.new_page(viewport={'width': 1440, 'height': 1000})
    register(employer, base, 'employer', 'space-browser-company')
    job = employer.request.post(base + '/api/jobs', data={
        'title': '隔离真实发布岗位', 'industry': '农业', 'city': '北京',
        'salary_min': 9000, 'salary_max': 12000, 'capacity': 2,
        'description': '隔离浏览器验收岗位', 'requirements': [{'skill': '数据分析'}],
    })
    assert job.status == 200, job.text()
    company = employer.request.get(base + '/api/company/profile').json()
    company['tracks'] = list(dict.fromkeys([*company['tracks'], 'AI/产品']))
    assert employer.request.put(base + '/api/company/profile', data=company).status == 200

    student = browser.new_page(viewport={'width': 1440, 'height': 1000})
    student.on('pageerror', lambda error: errors.append(str(error)))
    register(student, base, 'student', 'space-browser-student')
    private = student.request.post(base + '/api/documents', multipart={
        'file': {'name': '未选私有.txt', 'mimeType': 'text/plain', 'buffer': '未选私有正文'.encode()},
    })
    assert private.status == 200
    private_id = private.json()['id']
    route(student, 'my-space')
    form = student.locator('#my-space-form')
    for name, value in {
        'display_name': '隔离学生主页', 'headline': '关心农业与数据的产品探索者',
        'bio': '这是隔离浏览器验收中的真实填写。', 'school': '隔离测试大学',
        'major': '经济学', 'education': '本科二年级', 'background': '完成一个校园调研项目。',
        'interests': '农业，产品设计', 'strengths': '数据分析，访谈',
        'link_title': '项目网站', 'link_url': 'https://example.com/project',
    }.items():
        form.locator(f'[name="{name}"]').fill(value)
    student.locator('#space-avatar-upload').set_input_files({
        'name': '头像.png', 'mimeType': 'image/png', 'buffer': image_bytes(),
    })
    expect(student.locator('#space-avatar-preview img')).to_be_visible()
    student.wait_for_function('()=>document.querySelector("#space-avatar-preview img").naturalWidth>0')
    student.locator('#space-document-upload').set_input_files({
        'name': '公开简历.txt', 'mimeType': 'text/plain', 'buffer': '公开简历正文：校园产品调研'.encode(),
    })
    expect(form.locator('#space-documents')).to_contain_text('公开简历.txt')
    video = record_video(student)
    assert len(video) > 100
    student.locator('#space-portfolio-upload').set_input_files({
        'name': '项目演示.webm', 'mimeType': 'video/webm', 'buffer': video,
    })
    expect(form.locator('#space-portfolio')).to_contain_text('项目演示.webm')
    expect(form.locator(f'[name=document_ids][value="{private_id}"]')).not_to_be_checked()
    form.locator('[type=submit]').click()
    expect(student.locator('#space-message')).to_contain_text('草稿已保存')
    assert employer.request.get(base + '/api/students').json() == []
    assert employer.request.get(base + '/api/documents/' + private_id).status == 403
    student.locator('[data-action=space-preview]').click()
    expect(student.locator('#modal')).to_contain_text('主页草稿预览')
    expect(student.locator('#modal')).to_contain_text('公开简历.txt')
    expect(student.locator('#modal')).not_to_contain_text('未选私有.txt')
    expect(student.locator('#modal video')).to_have_count(1)
    expect_video_ready(student)
    student.locator('[data-action=close-modal]').click()
    student.locator('[data-action=space-publish]').click()
    expect(student.locator('#space-public-status')).to_contain_text('已发布')
    public = student.request.get(base + '/api/me/page').json()['published']
    assert public['links'][0]['url'] == 'https://example.com/project'
    assert public['document_ids'] != [private_id]
    assert len(public['documents']) == 1
    assert len(public['portfolio']) == 1

    university = browser.new_page(viewport={'width': 1440, 'height': 1000})
    register(university, base, 'university', 'space-browser-school')
    for viewer in (student, employer, university):
        viewer.on('pageerror', lambda error: errors.append(str(error)))
        route(viewer, 'students')
        expect(viewer.locator('.student-directory')).to_contain_text('隔离学生主页')
        viewer.locator('[data-action=student-page]').click()
        expect(viewer.locator('#modal')).to_contain_text('完成一个校园调研项目')
        expect(viewer.locator('#modal')).not_to_contain_text('未选私有.txt')
        assert viewer.locator('#modal a').get_attribute('rel') == 'noopener noreferrer'
        expect_video_ready(viewer)
        assert viewer.locator('#modal img').evaluate('(image)=>image.naturalWidth>0')
        viewer.locator('[data-action=space-public-document]').click()
        expect(viewer.locator('#modal')).to_contain_text('公开简历正文：校园产品调研')
        viewer.locator('[data-action=close-modal]').click()
        assert viewer.request.get(base + '/api/documents/' + private_id).status in ({200} if viewer == student else {403})
        viewer.set_viewport_size({'width': 390, 'height': 844})
        assert viewer.evaluate('document.documentElement.scrollWidth<=innerWidth')
        viewer.locator('[data-action=student-page]').click()
        assert viewer.locator('#modal').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
        viewer.locator('[data-action=close-modal]').click()
        viewer.set_viewport_size({'width': 1440, 'height': 1000})

    route(student, 'home')
    search = student.locator('#discovery-form')
    search.locator('[name=q]').fill(company['name'])
    search.locator('[type=submit]').click()
    expect(student.locator('[data-action=favorite-company]')).to_have_count(1)
    student.locator('[data-action=favorite-company]').click()
    expect(student.locator('#toast')).to_contain_text('已加入我的企业收藏')
    search.locator('[name=q]').fill('')
    search.locator('[name=track]').select_option('AI/产品')
    search.locator('[type=submit]').click()
    student.locator('[data-action=favorite-track]').click()
    expect(student.locator('#toast')).to_contain_text('已加入我的赛道收藏')
    route(student, 'my-space')
    expect(student.locator('#space-favorites')).to_contain_text(company['name'])
    expect(student.locator('#space-favorites')).to_contain_text('AI/产品')
    expect(student.locator('#space-feed')).to_contain_text('隔离真实发布岗位')
    expect(student.locator('#space-feed')).to_contain_text('9,000–12,000 元/月')
    student.screenshot(path=str(root / 'my-space-desktop.png'), full_page=True)
    student.set_viewport_size({'width': 390, 'height': 844})
    assert student.evaluate('document.documentElement.scrollWidth<=innerWidth')
    student.screenshot(path=str(root / 'my-space-mobile.png'), full_page=True)
    student.locator('.space-follow').filter(has_text=company['name']).locator('[data-action=space-unfollow]').click()
    expect(student.locator('#space-favorites')).not_to_contain_text(company['name'])
    expect(student.locator('#space-feed')).not_to_contain_text('隔离真实发布岗位')
    student.locator('.space-follow').filter(has_text='AI/产品').locator('[data-action=space-unfollow]').click()
    expect(student.locator('#space-favorites')).not_to_contain_text('AI/产品')
    assert student.request.get(base + '/api/me/favorites').json() == []
    student.locator('[data-action=space-withdraw]').click()
    expect(student.locator('#space-public-status')).to_contain_text('尚未发布')
    for viewer in (employer, university):
        assert viewer.request.get(base + '/api/students').json() == []
        assert viewer.request.get(base + '/api/students/' + public['id']).status == 404
        assert viewer.request.get(base + public['documents'][0]['url']).status == 403
        assert viewer.request.get(base + public['portfolio'][0]['url']).status == 403
        assert viewer.request.get(base + public['avatar_url']).status == 404
    assert student.request.get(base + '/api/me/page').json()['draft']['display_name'] == '隔离学生主页'
    assert errors == [], errors
    for viewer in (student, employer, university):
        viewer.close()
