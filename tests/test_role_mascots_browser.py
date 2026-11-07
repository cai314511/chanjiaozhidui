"""角色素材与动效使用真实实现；仅测试资料写入隔离浏览器数据库。"""
from pathlib import Path
from datetime import datetime, timezone

import pytest
from playwright.sync_api import expect

from tests.test_browser import browser_system, register, route


@pytest.mark.parametrize('role', ['student', 'employer', 'university'])
def test_role_mascot_home_cycle_entry_and_cleanup(browser_system, role):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    instant = datetime(2026, 11, 7, 10, tzinfo=timezone.utc)
    page.clock.install(time=instant)
    page.clock.pause_at(instant)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    register(page, base, role, 'mascot-' + role)
    entry = page.locator('#agent-toggle')
    expect(entry).to_have_attribute('data-mascot-role', role)
    expect(entry).to_have_attribute('data-mascot-ready', 'true')
    stage = page.locator('.role-mascot-stage')
    expect(stage).to_have_count(1)
    expect(stage).to_have_attribute('data-mascot-role', role)
    expect(stage).to_have_attribute('data-pose', '1')
    page.clock.run_for(3200)
    expect(stage).to_have_attribute('data-pose', '2')
    assert stage.locator('.mascot-pose').count() == 2
    # 在叠化过程中，两层均可见，外层运动连续且不重新挂载。
    layers = stage.locator('.mascot-pose').evaluate_all(
        '(nodes)=>nodes.map(node=>Number(getComputedStyle(node).opacity))')
    assert all(0 < opacity < 1 for opacity in layers), layers
    page.clock.run_for(2700)
    expect(stage).to_have_attribute('data-pose', '2')
    page.clock.run_for(200)
    expect(stage).to_have_attribute('data-pose', '3')
    page.clock.run_for(21100)
    expect(stage).to_have_attribute('data-pose', '1')
    # 明确隔离的可见性事件模拟，验证隐藏期间不会累积轮播。
    page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))")
    expect(stage).to_have_attribute('data-motion', 'paused')
    page.clock.run_for(10000)
    expect(stage).to_have_attribute('data-pose', '1')
    page.evaluate("delete document.hidden;document.dispatchEvent(new Event('visibilitychange'))")
    expect(stage).to_have_attribute('data-motion', 'running')
    page.clock.resume()
    entry.click()
    expect(page.locator('#agent-drawer')).to_be_visible()
    expect(page.locator('.agent-orb-stage')).to_have_attribute('data-render', 'ready', timeout=30000)
    entry.click()
    folder = Path(__file__).resolve().parents[1] / 'runtime' / 'role-mascot-review'
    folder.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(folder / f'{role}-desktop.png'), animations='disabled')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.clock.run_for(1000)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert stage.bounding_box()['width'] <= 390
    assert entry.bounding_box()['x'] + entry.bounding_box()['width'] <= 390
    page.screenshot(path=str(folder / f'{role}-mobile.png'), animations='disabled')
    # 导航销毁旧角色后不再推进其姿态。
    page.evaluate('window.previousMascot=document.querySelector(".role-mascot-stage")')
    page.locator('[data-action=mobile-menu]').click()
    route(page, 'documents')
    expect(stage).to_have_count(0)
    old_pose = page.evaluate('window.previousMascot.dataset.pose')
    page.clock.run_for(6000)
    assert page.evaluate('window.previousMascot.dataset.pose') == old_pose
    # 同一页签切换身份，旧角色及旧的异步图片回调不得带入新身份。
    page.locator('[data-action=mobile-menu]').click()
    page.locator('[data-action=logout]').click()
    expect(entry).to_have_attribute('data-mascot-audience', 'guest')
    expect(entry).to_have_attribute('data-mascot-ready', 'true')
    assert not errors, errors
    page.close()


def test_mascot_reduced_motion_and_failed_asset_remain_usable(browser_system):
    browser, base = browser_system
    page = browser.new_page(reduced_motion='reduce')
    page.clock.install()
    register(page, base, 'student', 'mascot-reduced')
    stage = page.locator('.role-mascot-stage')
    expect(stage).to_have_attribute('data-motion', 'reduced')
    page.clock.run_for(10000)
    expect(stage).to_have_attribute('data-pose', '1')
    assert stage.evaluate('(el)=>el.getAnimations({subtree:true}).length') == 0
    page.close()
    failed = browser.new_page()
    failed.route('**/assets/mascots/student.png', lambda request: request.abort())
    register(failed, base, 'student', 'mascot-failed')
    expect(failed.locator('#agent-toggle')).to_have_attribute('data-mascot-ready', 'false')
    expect(failed.locator('#agent-toggle')).to_have_text('✦')
    failed.locator('#agent-toggle').click()
    expect(failed.locator('#agent-drawer')).to_be_visible()
    expect(failed.locator('.role-mascot-stage')).to_have_count(0)
    failed.close()


def test_guest_mascots_random_pool_blends_and_login_identity(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    instant = datetime(2026, 11, 7, 10, tzinfo=timezone.utc)
    page.clock.install(time=instant)
    page.clock.pause_at(instant)
    # 仅固定随机采样，角色素材、轮播与业务接口仍使用真实实现。
    page.add_init_script('''let sample=0;const values=[0,.48,.96,.24,.72,.12,.84];
        Math.random=()=>values[sample++%values.length];''')
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(base)
    entry = page.locator('#agent-toggle')
    stage = page.locator('.discovery-hero .role-mascot-stage')
    expect(entry).to_have_attribute('data-mascot-audience', 'guest')
    expect(stage).to_have_count(1)
    expect(stage).to_have_attribute('data-mascot-audience', 'guest')
    expect(entry).to_have_attribute('data-mascot-ready', 'true')
    seen = set()
    previous = None
    for index in range(10):
        pair = (stage.get_attribute('data-mascot-role'), stage.get_attribute('data-pose'))
        assert pair[0] in {'student', 'employer', 'university'}
        assert 1 <= int(pair[1]) <= 9
        assert pair != previous
        seen.add(pair[0])
        previous = pair
        assert entry.locator('.mascot-cell-0').count() == 2
        page.clock.run_for(3000)
    assert len(seen) == 3
    page.clock.run_for(200)
    for target in [entry, stage]:
        opacity = target.locator('.mascot-pose').evaluate_all('(els)=>els.map(el=>Number(el.style.opacity))')
        assert all(0 < value < 1 for value in opacity), opacity
        assert sum(opacity) == pytest.approx(1)
    page.clock.resume()
    folder = Path(__file__).resolve().parents[1] / 'runtime/role-mascot-review'
    folder.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(folder / 'guest-desktop.png'), animations='disabled')
    for width in [1024, 768, 390]:
        page.set_viewport_size({'width': width, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        hero_text = page.locator('.discovery-hero h1').bounding_box()
        mascot = stage.bounding_box()
        assert mascot['x'] >= hero_text['x'] + hero_text['width'] or mascot['y'] + mascot['height'] <= hero_text['y']
    page.screenshot(path=str(folder / 'guest-mobile.png'), animations='disabled')
    entry.click()
    expect(page.locator('#toast')).to_contain_text('登录')
    assert page.locator('#agent-drawer').is_hidden()
    # 注册完成后应使用本端形象，访客轮播不得继续覆盖身份。
    page.set_viewport_size({'width': 1440, 'height': 1000})
    register(page, base, 'employer', 'guest-to-employer')
    expect(entry).to_have_attribute('data-mascot-audience', 'employer')
    expect(entry).to_have_attribute('data-mascot-role', 'employer')
    page.clock.run_for(9000)
    expect(entry).to_have_attribute('data-mascot-role', 'employer')
    expect(page.locator('.role-mascot-stage')).to_have_attribute('data-mascot-role', 'employer')
    assert not errors, errors
    page.close()


def test_guest_reduced_motion_and_partial_missing_atlas(browser_system):
    browser, base = browser_system
    page = browser.new_page(reduced_motion='reduce')
    page.clock.install()
    page.route('**/assets/mascots/student.png', lambda route: route.abort())
    page.goto(base)
    stage = page.locator('.role-mascot-stage')
    expect(stage).to_have_attribute('data-motion', 'reduced')
    before = stage.get_attribute('data-mascot-role')
    assert before in {'employer', 'university'}
    page.clock.run_for(12000)
    expect(stage).to_have_attribute('data-mascot-role', before)
    assert stage.evaluate('(el)=>el.getAnimations({subtree:true}).length') == 0
    expect(page.locator('#agent-toggle')).to_have_attribute('data-mascot-ready', 'true')
    page.close()
