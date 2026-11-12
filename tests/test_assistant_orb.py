"""独立验证 Agent 外观的真实 WebGL 折射、状态响应和资源释放。"""

from pathlib import Path

from playwright.sync_api import expect

from tests.test_browser import browser_system, register


def test_assistant_orb_refraction_states_motion_and_disposal(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1100, 'height': 800})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(base)
    page.evaluate('''async () => {
        const {WaterOrb}=await import('/assets/water-orb.js');
        const host=document.createElement('div');host.id='assistant-orb-check';
        host.style.cssText='position:fixed;inset:70px auto auto 300px;width:420px;height:420px;background:#edf0e8;z-index:999';
        document.body.append(host);window.testAssistantOrb=new WaterOrb(host,{appearance:'assistant'});
    }''')
    host = page.locator('#assistant-orb-check')
    expect(host).to_have_attribute('data-render', 'ready', timeout=30000)
    result = page.evaluate('''async () => {
        const orb=window.testAssistantOrb;
        const frames=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        orb.setMode('listening');orb.setVolume(1);await new Promise(resolve=>setTimeout(resolve,300));
        const responding=orb.uniforms.waterEnergy.value>0;
        orb.renderer.render(orb.scene,orb.camera);const water=orb.renderer.domElement.toDataURL();
        orb.material.ior=1;orb.renderer.render(orb.scene,orb.camera);const air=orb.renderer.domElement.toDataURL();orb.material.ior=1.333;
        orb.setMode('error');await frames();const stopped=orb.elapsed;
        orb.setVolume(1);await new Promise(resolve=>setTimeout(resolve,120));
        const errorStopped=orb.elapsed===stopped&&orb.uniforms.waterEnergy.value===0&&orb.uniforms.waterActivity.value===0;
        orb.setMode('thinking');await new Promise(resolve=>setTimeout(resolve,120));
        const resumed=orb.elapsed>stopped;
        orb.setMode('idle');await frames();
        return {responding,refractionChanged:water!==air,errorStopped,resumed,transmission:orb.material.transmission,ior:orb.material.ior};
    }''')
    assert result == {'responding': True, 'refractionChanged': True, 'errorStopped': True,
                      'resumed': True, 'transmission': 1, 'ior': 1.333}
    folder = Path(__file__).resolve().parents[1] / 'runtime' / 'assistant-orb-review'
    folder.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(folder / 'assistant-desktop.png'))
    page.emulate_media(reduced_motion='reduce')
    reduced = page.evaluate('''async () => {
        const orb=window.testAssistantOrb;await new Promise(resolve=>setTimeout(resolve,100));
        const stopped=orb.elapsed;let renders=0;const render=orb.renderer.render.bind(orb.renderer);
        orb.renderer.render=(...args)=>{renders++;return render(...args)};
        await new Promise(resolve=>setTimeout(resolve,130));
        return {paused:orb.elapsed===stopped,renders};
    }''')
    assert reduced == {'paused': True, 'renders': 0}
    page.set_viewport_size({'width': 390, 'height': 844})
    host.evaluate("(host)=>{host.style.left='0';host.style.width='390px';host.style.height='390px'}")
    expect(host.locator('canvas')).to_have_count(1)
    assert host.locator('canvas').bounding_box()['width'] <= 390
    page.screenshot(path=str(folder / 'assistant-mobile.png'))
    disposed = page.evaluate('''() => {
        const orb=window.testAssistantOrb;orb.dispose();orb.dispose();
        return {disposed:orb.disposed,remaining:orb.host.childElementCount};
    }''')
    assert disposed == {'disposed': True, 'remaining': 0}
    assert errors == [], errors
    page.close()


def test_assistant_glass_in_actual_panel_dimensions(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1280, 'height': 960})
    register(page, base, 'student', 'orb-appearance-check')
    page.locator('#agent-toggle').click()
    stage = page.locator('.agent-orb-stage')
    expect(stage).to_have_attribute('data-render', 'ready', timeout=30000)
    folder = Path(__file__).resolve().parents[1] / 'runtime' / 'assistant-orb-review'
    folder.mkdir(parents=True, exist_ok=True)
    page.locator('#agent-drawer').screenshot(path=str(folder / 'assistant-panel-desktop.png'))
    stage.screenshot(path=str(folder / 'assistant-stage-desktop.png'))
    # 水滴置于标题栏，给对话和始终可见的输入区留出空间。
    assert 24 <= stage.bounding_box()['width'] <= 56
    expect(page.locator('.drawer-head .agent-orb-stage')).to_have_count(1)
    for selector in ['#agent-form textarea', '#agent-form .agent-speech', '#agent-form [type=submit]']:
        box = page.locator(selector).bounding_box()
        assert box['y'] >= 0 and box['y'] + box['height'] <= 960
    page.set_viewport_size({'width': 390, 'height': 844})
    page.locator('#agent-drawer').screenshot(path=str(folder / 'assistant-panel-mobile.png'))
    assert stage.bounding_box()['width'] <= 390
    for selector in ['#agent-form textarea', '#agent-form .agent-speech', '#agent-form [type=submit]']:
        box = page.locator(selector).bounding_box()
        assert box['y'] >= 0 and box['y'] + box['height'] <= 844
    page.locator('[data-action=close-agent]').click()
    expect(stage.locator('canvas')).to_have_count(0)
    page.close()
