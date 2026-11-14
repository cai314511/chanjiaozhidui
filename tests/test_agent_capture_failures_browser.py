"""明确隔离麦克风拒绝、转写服务失败，不代表真实声学识别验收。"""

import pytest
from playwright.sync_api import expect

from tests.test_browser import browser_system, register


@pytest.mark.parametrize('role', ['student', 'employer', 'university'])
def test_capture_denial_and_transcription_failure_leave_question_editable(browser_system, role):
    browser, base = browser_system
    page = browser.new_page()
    register(page, base, role, 'capture-errors-' + role)
    page.locator('#agent-toggle').click()
    page.evaluate("()=>{navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('denied','NotAllowedError')}}")
    page.locator('.agent-speech').click()
    expect(page.locator('#agent-orb-status')).to_contain_text('麦克风权限未开启')
    expect(page.locator('#agent-form textarea')).to_be_editable()
    expect(page.locator('#agent-form [type=submit]')).to_be_enabled()
    page.evaluate("""()=>{
      const Recorder=window.MediaRecorder;
      window.MediaRecorder=class extends Recorder{constructor(...args){super(...args);
        this.addEventListener('dataavailable',event=>{if(event.data.size)window.testRecordedChunk=true});
      }};
      navigator.mediaDevices.getUserMedia=async()=>{
      const context=new AudioContext(), oscillator=context.createOscillator(), out=context.createMediaStreamDestination();
      oscillator.connect(out);oscillator.start();await context.resume();window.testMicTracks=out.stream.getTracks();return out.stream;
    }}""")
    failed_requests = []
    def fail_transcription(route):
        failed_requests.append(route.request.url)
        route.fulfill(status=503, json={'detail': '隔离转写服务失败'})
    page.route('**/api/voice/transcribe', fail_transcription)
    page.locator('.agent-speech').click()
    expect(page.locator('#agent-orb-status')).to_have_text('正在倾听')
    # 正振幅不等于已识别到语音；有声且已有编码片段后才触发本用例的503故障。
    page.wait_for_function('()=>window.testRecordedChunk===true && Number(document.querySelector(".agent-orb-stage").dataset.volume)>0.2')
    page.locator('.agent-speech').click()
    expect(page.locator('.agent-orb-stage')).to_have_attribute('data-mode', 'error')
    expect(page.locator('#agent-orb-status')).to_have_text('隔离转写服务失败')
    assert failed_requests, '本用例必须实际调用模拟的转写失败接口'
    expect(page.locator('#agent-form textarea')).to_be_editable()
    expect(page.locator('.agent-speech')).to_be_enabled()
    assert page.evaluate('testMicTracks.every(track=>track.readyState==="ended")')
    page.close()
