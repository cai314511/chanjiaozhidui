"""Agent 状态与释放验收；外网模型、麦克风与转写使用明确隔离的测试替身。"""

import pytest
from pathlib import Path
from playwright.sync_api import expect

from tests.test_browser import browser_system, register


@pytest.mark.parametrize('role', ['student', 'employer', 'university'])
def test_agent_states_and_close_release(browser_system, role):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1280, 'height': 960})
    pending = []
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/api/agent/run', lambda route: pending.append(route))
    register(page, base, role, 'orb-' + role)
    page.locator('#agent-toggle').click()
    stage = page.locator('.agent-orb-stage')
    expect(stage).to_have_attribute('data-mode', 'idle')
    expect(stage).to_have_attribute('data-render', 'ready')
    page.locator('#agent-form textarea').fill('隔离验收：说明培养与职业方向')
    page.locator('#agent-form [type=submit]').click()
    expect(stage).to_have_attribute('data-mode', 'thinking')
    expect(page.locator('#agent-orb-status')).to_have_text('正在思考')
    assert len(pending) == 1
    pending.pop().fulfill(json={'message': '隔离回复', 'trace': [], 'model': '测试替身', 'elapsed': .1, 'draft': None})
    expect(stage).to_have_attribute('data-mode', 'idle')
    expect(page.locator('#agent-messages')).to_contain_text('隔离回复')
    page.locator('#agent-form textarea').fill('隔离错误请求')
    page.locator('#agent-form [type=submit]').click()
    expect(stage).to_have_attribute('data-mode', 'thinking')
    assert len(pending) == 1
    pending.pop().fulfill(status=503, json={'detail': '隔离服务暂不可用'})
    expect(stage).to_have_attribute('data-mode', 'error')
    expect(page.locator('#agent-messages')).to_contain_text('隔离服务暂不可用')
    page.evaluate("""()=>{const original=window.fetch;window.fetch=(url,options={})=>{
      if(String(url)==='/api/agent/run')return new Promise((resolve,reject)=>{
        window.agentPending=true;options.signal.addEventListener('abort',()=>{
          window.agentAborted=true;reject(new DOMException('closed','AbortError'));
        },{once:true});
      });return original(url,options);
    }}""")
    page.locator('#agent-form textarea').fill('关闭面板应取消等待')
    page.locator('#agent-form [type=submit]').click()
    page.wait_for_function('()=>window.agentPending')
    page.locator('#agent-toggle').click()
    expect(page.locator('#agent-drawer')).to_be_hidden()
    assert page.evaluate('window.agentAborted === true')
    expect(stage.locator('canvas')).to_have_count(0)
    page.locator('#agent-toggle').click()
    expect(page.locator('.agent-orb-stage')).to_have_attribute('data-render', 'ready')
    folder = Path(__file__).resolve().parents[1] / 'runtime' / 'agent-panel-review'
    folder.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(folder / (role + '-desktop.png')))
    page.set_viewport_size({'width': 390, 'height': 844})
    drawer = page.locator('#agent-drawer').bounding_box()
    assert drawer['x'] >= 0 and drawer['x'] + drawer['width'] <= 391
    assert drawer['y'] >= 0 and drawer['height'] <= 844
    page.screenshot(path=str(folder / (role + '-mobile.png')))
    page.locator('[data-action=close-agent]').click()
    assert not errors
    page.close()


@pytest.mark.parametrize('role', ['student', 'employer', 'university'])
def test_agent_voice_confirmation_and_webgl_fallback(browser_system, role):
    browser, base = browser_system
    page = browser.new_page(reduced_motion='reduce')
    page.add_init_script("""navigator.mediaDevices.getUserMedia=async()=>{
      const context=new AudioContext(), source=context.createOscillator(), gain=context.createGain();
      gain.gain.value=.08; const output=context.createMediaStreamDestination();
      source.connect(gain);gain.connect(output);source.start();
      window.testMicTracks=output.stream.getTracks();return output.stream;
    };""")
    page.route('**/api/voice/transcribe', lambda route: route.fulfill(json={'text': '隔离转写，可编辑'}))
    requests = []
    page.route('**/api/agent/run', lambda route: (requests.append(route.request.post_data_json), route.fulfill(json={
        'message': '已收到确认文本', 'trace': [], 'model': '测试替身', 'elapsed': .1, 'draft': None})))
    register(page, base, role, 'orb-voice-' + role)
    page.locator('#agent-toggle').click()
    speech = page.locator('#agent-form .agent-speech')
    speech.click()
    expect(page.locator('#agent-orb-status')).to_have_text('正在倾听')
    page.wait_for_function("()=>window.testMicTracks && document.querySelector('.agent-orb-stage').dataset.volume > 0")
    speech.click()
    expect(page.locator('#agent-form textarea')).to_have_value('隔离转写，可编辑')
    assert not requests
    page.locator('#agent-form textarea').fill('用户已修改的确认文本')
    page.locator('#agent-form [type=submit]').click()
    expect(page.locator('#agent-messages')).to_contain_text('已收到确认文本')
    assert requests[0]['message'] == '用户已修改的确认文本'
    assert page.evaluate('testMicTracks.every(track=>track.readyState==="ended")')
    speech.click()
    expect(page.locator('#agent-orb-status')).to_have_text('正在倾听')
    page.locator('[data-action=close-agent]').click()
    assert page.evaluate('testMicTracks.every(track=>track.readyState==="ended")')
    page.locator('#agent-toggle').click()
    expect(page.locator('.agent-orb-stage')).to_have_attribute('data-render', 'ready')
    speech.click()
    expect(page.locator('#agent-orb-status')).to_have_text('正在倾听')
    page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))")
    assert page.evaluate('testMicTracks.every(track=>track.readyState==="ended")')
    page.evaluate("delete document.hidden;document.dispatchEvent(new Event('visibilitychange'))")
    # 真实 WebGL context 丢失时保留输入，提供静态玻璃降级。
    page.locator('.agent-orb-stage canvas').evaluate("canvas=>canvas.dispatchEvent(new Event('webglcontextlost',{cancelable:true}))")
    expect(page.locator('.agent-orb-stage')).to_have_attribute('data-render', 'fallback')
    expect(page.locator('.agent-orb-fallback')).to_be_visible()
    expect(page.locator('#agent-form textarea')).to_be_editable()
    page.evaluate("window.dispatchEvent(new Event('identity-reset'))")
    expect(page.locator('#agent-drawer')).to_be_hidden()
    page.close()
    fallback = browser.new_page()
    fallback.add_init_script("const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){return type.includes('webgl')?null:original.call(this,type,...args)}")
    register(fallback, base, role, 'orb-fallback-' + role)
    fallback.locator('#agent-toggle').click()
    expect(fallback.locator('.agent-orb-stage')).to_have_attribute('data-render', 'fallback')
    expect(fallback.locator('#agent-form textarea')).to_be_editable()
    fallback.close()


def test_stop_during_audio_initialization_releases_capture(browser_system):
    browser, base = browser_system
    page = browser.new_page()
    page.add_init_script("""const NativeAudioContext=window.AudioContext;
      navigator.mediaDevices.getUserMedia=async()=>{
        const ctx=new NativeAudioContext(), oscillator=ctx.createOscillator(), out=ctx.createMediaStreamDestination();
        oscillator.connect(out);oscillator.start();window.testMicTracks=out.stream.getTracks();return out.stream;
      };
      window.AudioContext=class extends NativeAudioContext{
        resume(){return new Promise(resolve=>window.releaseResume=resolve)}
      };""")
    register(page, base, 'student', 'orb-initializing')
    page.locator('#agent-toggle').click()
    speech = page.locator('.agent-speech')
    speech.click()
    page.wait_for_function('()=>typeof window.releaseResume === "function"')
    speech.click()
    page.wait_for_function('()=>testMicTracks.every(track=>track.readyState==="ended")', timeout=2000)
    page.evaluate('releaseResume()')
    expect(page.locator('.agent-orb-stage')).not_to_have_attribute('data-mode', 'listening')
    page.locator('[data-action=close-agent]').click()
    assert page.evaluate('testMicTracks.every(track=>track.readyState==="ended")')
    page.close()
