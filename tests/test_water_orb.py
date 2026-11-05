import json
from pathlib import Path

from playwright.sync_api import expect

from tests.test_browser import browser_system, register, route


def test_webgl_water_material_states_and_disposal(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    register(page, base, 'student', 'water-student')
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    route(page, 'profile')
    page.locator('[data-action=voice-intro]').first.click()
    expect(page.locator('.droplet-stage')).to_have_attribute('data-render', 'ready', timeout=30000)
    folder = Path(__file__).resolve().parents[1] / 'runtime' / 'water-review'
    folder.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(folder / 'desktop.png'))
    page.locator('[data-action=close-modal]').click()
    expect(page.locator('.water-canvas')).to_have_count(0)
    # 单独检查真实 WebGL 组件状态；这些状态输入不代表真实语音服务调用。
    result = page.evaluate('''async () => {
      const {WaterOrb}=await import('/assets/water-orb.js');
      const host=document.createElement('div');host.style.width='480px';host.style.height='340px';document.body.append(host);
      const orb=new WaterOrb(host);const states=[];
      for(const mode of ['idle','listening','thinking','speaking','error']){
       orb.setMode(mode);orb.setVolume(.4);
       await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
       states.push(host.dataset.mode);
      }
      const material={ior:orb.material.ior,transmission:orb.material.transmission,roughness:orb.material.roughness,metalness:orb.material.metalness};
      const geometry=orb.orb.geometry.attributes.position.count;
      orb.renderer.render(orb.scene,orb.camera);const water=orb.renderer.domElement.toDataURL();
      orb.material.ior=1.;orb.renderer.render(orb.scene,orb.camera);const air=orb.renderer.domElement.toDataURL();
      orb.material.ior=1.333;
      const timings=[];let previous=performance.now();
      for(let i=0;i<30;i++){await new Promise(resolve=>requestAnimationFrame(resolve));const now=performance.now();timings.push(now-previous);previous=now;}
      timings.sort((a,b)=>a-b);
      orb.dispose();const remaining=host.childElementCount;host.remove();
      return {states,material,geometry,remaining,refractionChanged:water!==air,medianFrameMs:timings[15]};
    }''')
    assert result['states'] == ['idle', 'listening', 'thinking', 'speaking', 'error']
    assert result['material'] == {'ior': 1.333, 'transmission': 1, 'roughness': .025, 'metalness': 0}
    assert result['geometry'] > 2000
    assert result['remaining'] == 0
    assert result['refractionChanged']
    (folder / 'render-check.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.locator('[data-action=voice-intro]').first.click()
    expect(page.locator('.droplet-stage')).to_have_attribute('data-render', 'ready', timeout=30000)
    page.screenshot(path=str(folder / 'mobile.png'))
    assert page.locator('.voice-dialog').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
    page.locator('[data-action=close-modal]').click()
    assert errors == [], errors
    page.close()
