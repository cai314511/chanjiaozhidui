"""模拟 Linux 合成不可用及设备语音事件，验证真实会话的回退与取消。"""

import pytest
from playwright.sync_api import expect

from tests.test_browser import browser_system, register, route


SPEECH_DEVICE = """() => {
  window.SpeechSynthesisUtterance = class { constructor(text){this.text=text;} };
  const device = new EventTarget();
  device.getVoices = () => [{name:'隔离中文设备',lang:'zh-CN',localService:true}];
  device.cancel = () => { window.cancelledSpeech = true; };
  device.speak = utterance => { window.testUtterance = utterance;
    setTimeout(() => utterance.onstart?.(), 0); };
  Object.defineProperty(window, 'speechSynthesis', {value:device,configurable:true});
}"""


def open_voice(page, base, name, server_ready=False):
    page.route('**/api/voice/status', lambda r: r.fulfill(json={'synthesis_ready': server_ready}))
    page.route('**/api/voice/speak', lambda r: r.fulfill(
        status=503, json={'detail': '本地中文语音合成未完成，请检查中文语音组件：ValueError'}))
    register(page, base, 'student', name)
    if page.viewport_size['width'] < 740:
        page.locator('[data-action=mobile-menu]').click()
    route(page, 'profile')
    page.locator('[data-action=voice-intro]').first.click()


def test_linux_server_uses_device_voice_and_close_cancels_playback(browser_system):
    browser, base = browser_system
    page = browser.new_page()
    page.add_init_script('(' + SPEECH_DEVICE + ')()')
    open_voice(page, base, 'linux-device-speech')
    expect(page.locator('#voice-status')).to_contain_text('正在回答')
    expect(page.locator('.droplet-stage')).to_have_attribute('data-mode', 'speaking')
    assert page.evaluate("testUtterance.lang === 'zh-CN' && testUtterance.text.includes('最近完成')")
    page.evaluate('testUtterance.onend()')
    expect(page.locator('#voice-status')).to_contain_text('轮到你')
    expect(page.locator('#voice-error')).to_be_empty()
    page.locator('#voice-replay').click()
    expect(page.locator('#voice-status')).to_contain_text('正在回答')
    page.locator('#voice-transcript').fill('保留未提交回答')
    page.locator('[data-action=close-modal]').first.click()
    expect(page.locator('#modal')).not_to_be_visible()
    assert page.evaluate('cancelledSpeech === true')
    # 迟到的设备回调不得重新激活已关闭的语音窗口。
    page.evaluate('testUtterance.onend?.()')
    expect(page.locator('#modal')).not_to_be_visible()
    page.close()


@pytest.mark.parametrize('voices', ['[]', "[{name:'云端中文',lang:'zh-CN',localService:false}]"])
def test_missing_local_chinese_voice_keeps_answer_editable(browser_system, voices):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 390, 'height': 844})
    page.add_init_script('(' + SPEECH_DEVICE + ')(); speechSynthesis.getVoices=()=>'+voices)
    open_voice(page, base, 'no-device-speech-' + str(len(voices)))
    expect(page.locator('#voice-error')).to_contain_text('中文语音', timeout=10000)
    expect(page.locator('#voice-error')).not_to_contain_text('ValueError')
    expect(page.locator('#voice-transcript')).to_be_editable()
    expect(page.locator('#voice-send')).to_be_enabled()
    page.locator('#voice-transcript').fill('仍可核对文字回答')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.close()


def test_delayed_voice_load_after_close_does_not_start_speech(browser_system):
    browser, base = browser_system
    page = browser.new_page()
    page.add_init_script('(' + SPEECH_DEVICE + ')(); speechSynthesis.getVoices=()=>[]')
    open_voice(page, base, 'late-device-speech')
    expect(page.locator('#voice-status')).to_contain_text('正在准备语音')
    page.locator('[data-action=close-modal]').first.click()
    page.evaluate("""()=>{
      speechSynthesis.getVoices=()=>[{name:'晚到的中文语音',lang:'zh-CN',localService:true}];
      speechSynthesis.dispatchEvent(new Event('voiceschanged'));
    }""")
    expect(page.locator('#modal')).not_to_be_visible()
    assert page.evaluate('window.testUtterance === undefined')
    page.close()


def test_server_synthesis_failure_falls_back_and_device_error_is_actionable(browser_system):
    browser, base = browser_system
    page = browser.new_page()
    page.add_init_script('(' + SPEECH_DEVICE + ')()')
    open_voice(page, base, 'failed-server-speech', server_ready=True)
    expect(page.locator('#voice-status')).to_contain_text('正在回答')
    page.evaluate("testUtterance.onerror({error:'not-allowed'})")
    expect(page.locator('#voice-status')).to_contain_text('重播问题')
    page.locator('#voice-replay').click()
    expect(page.locator('#voice-status')).to_contain_text('正在回答')
    page.evaluate('testUtterance.onend()')
    expect(page.locator('#voice-error')).to_be_empty()
    page.close()
