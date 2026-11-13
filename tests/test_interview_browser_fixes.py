"""隔离账号、投递与引导状态；真实 UI 确认预设证据及双端合成音轨。"""
import json
import socket
import threading
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
import uvicorn
from playwright.sync_api import sync_playwright, expect
from backend.app import create_app
from tests.test_api import job_data
from tests.test_browser import route

OUT=ROOT/'runtime'/'system-audit-20261113'/'employer'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    app=create_app(OUT/('human-data-'+str(time.time_ns())),enable_demo=False)
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    deadline=time.monotonic()+15
    while not server.started and time.monotonic()<deadline:thread.join(.05)
    base=f'http://127.0.0.1:{port}'
    report={'preconditions':'账号、岗位与授权投递由正式 API 设置；会话创建、双方进入与接通按钮由真实 Edge UI 操作；音频设备为 Chromium fake devices。','attempts':[]}
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True,args=['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
            pages=[]
            for role in ['employer','student']:
                ctx=browser.new_context(viewport={'width':1440,'height':900},permissions=['microphone'])
                ctx.add_init_script("window.auditPeers=[]; const NativePeer=window.RTCPeerConnection; window.RTCPeerConnection=class extends NativePeer{constructor(...args){super(...args);window.auditPeers.push(this)}}")
                p=ctx.new_page();pages.append(p)
                assert p.request.post(base+'/api/auth/register',data={'username':'human-audit-'+role,'name':'隔离'+role,'role':role,'password':'human-audit-1234'}).status==200
            emp,stu=pages
            assert stu.request.put(base+'/api/me/exploration',data={'seen':True,'answers':{},'text':''}).status==200
            spec=job_data()
            spec['questions']=[{'id':'preset-project','title':'讲述产品验证项目','skill':'产品设计','rubric':'实际行动'}]
            job=emp.request.post(base+'/api/jobs',data=spec).json()
            application=stu.request.post(base+'/api/applications',data={'job_id':job['id'],'consent':True}).json()
            stu.goto(base);route(stu,'applications')
            stu.locator('[data-action=interview]').click();stu.locator('[data-action=start-interview][data-id=preset]').click()
            stu.locator('#voice-transcript').fill('我完成访谈和原型验证')
            stu.locator('#voice-send').click()
            expect(stu.locator('#preset-review')).to_be_visible()
            stu.screenshot(path=str(OUT/'16-preset-review-desktop.png'),full_page=True)
            assert stu.request.get(base+'/api/applications').json()[0]['answers']=={}
            stu.locator('#preset-review [data-question]').fill('核对后：完成访谈并验证关键流程')
            stu.locator('#preset-confirm').check()
            stu.locator('#preset-review [type=submit]').click()
            expect(stu.locator('#preset-submit-status')).to_have_text('已提交企业复核')
            stu.set_viewport_size({'width':390,'height':844})
            stu.screenshot(path=str(OUT/'16-preset-review-mobile.png'),full_page=True)
            assert stu.evaluate('document.documentElement.scrollWidth<=innerWidth')
            stu.set_viewport_size({'width':1440,'height':900})
            answers=emp.request.get(base+'/api/applications').json()[0]['answers']
            assert answers=={'preset-project':'核对后：完成访谈并验证关键流程'}
            report['preset']={'explicit_confirmation':True,'answers':answers}
            stu.locator('[data-action=close-modal]').first.click()
            for attempt in ['student_offer_then_employer','near_simultaneous']:
                events=[]
                handlers=[]
                for label,p in [('student',stu),('employer',emp)]:
                    def collect(response, label=label):
                        if response.url.endswith('/signal'):
                            detail=response.json().get('detail') if response.status>=400 else None
                            request=response.request.post_data_json
                            events.append({'actor':label,'kind':request['kind'],'status':response.status,'detail':detail})
                    p.on('response',collect)
                    handlers.append((p,collect))
                    p.goto(base);route(p,'applications')
                stu.locator('[data-action=interview]').click();stu.locator('[data-action=start-interview][data-id=human]').click()
                expect(stu.locator('#human-connect')).to_be_visible()
                session=next(s for s in stu.request.get(base+'/api/interviews').json() if s['mode']=='human')
                emp.locator('[data-action=candidate-detail]').click();emp.locator('[data-action=interview]').click()
                emp.locator('[data-action=join-interview][data-id="'+session['id']+'"]').click()
                expect(emp.locator('#human-connect')).to_be_visible()
                stu.locator('#human-connect').click()
                if attempt=='student_offer_then_employer':
                    deadline=time.monotonic()+8
                    while time.monotonic()<deadline:
                        latest=stu.request.get(base+'/api/interviews/'+session['id']).json()
                        if latest.get('call_id') and any(s['kind']=='offer' for s in latest['signals']):break
                        stu.wait_for_timeout(50)
                emp.locator('#human-connect').click()
                expect(stu.locator('#voice-status')).to_have_text('真人音频已接通',timeout=15000)
                expect(emp.locator('#voice-status')).to_have_text('真人音频已接通',timeout=15000)
                stu.wait_for_timeout(1800)
                states=[]
                for label,p in [('student',stu),('employer',emp)]:
                    stats=p.evaluate("""async()=>Promise.all(window.auditPeers.map(async p=>({connection:p.connectionState,stats:[...await p.getStats()].map(([,x])=>x).filter(x=>x.type==='inbound-rtp'&&x.kind==='audio').map(x=>({bytesReceived:x.bytesReceived,packetsReceived:x.packetsReceived}))})))""")
                    states.append({'actor':label,'status':p.locator('#voice-status').inner_text(),'error':p.locator('#voice-error').inner_text(),'peers':stats})
                    p.screenshot(path=str(OUT/f'16-fixed-human-{attempt}-{label}.png'),full_page=True)
                report['attempts'].append({'ordering':attempt,'events':list(events),'states':states})
                print(json.dumps(report['attempts'][-1],ensure_ascii=False),flush=True)
                (OUT/'interview-fix-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                assert all(event['status']==200 for event in events),events
                for entry in states:
                    assert entry['status']=='真人音频已接通' and not entry['error'],entry
                    assert any(peer['connection']=='connected' and any(stat['bytesReceived']>0 and stat['packetsReceived']>0 for stat in peer['stats']) for peer in entry['peers']),entry
                for p,handler in handlers:
                    p.remove_listener('response',handler)
                for p in [stu,emp]:
                    p.locator('[data-action=close-modal]').first.click()
            browser.close()
    finally:
        server.should_exit=True;thread.join(10);sock.close()


def test_preset_confirmation_and_real_dual_browser_audio():
    main()


if __name__=='__main__':main()
