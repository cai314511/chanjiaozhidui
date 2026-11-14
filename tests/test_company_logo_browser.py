"""已核验品牌走正式注册、检索与本地图像端点；缺图故障单独模拟。"""

from pathlib import Path

from playwright.sync_api import expect

from tests.test_browser import browser_system, route


def test_portrait_logo_stays_inside_company_mark_at_both_widths(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    name = 'Bureau Veritas 必维工业与设施事业部必维质量技术服务（上海）有限公司'
    assert page.request.post(base + '/api/auth/register', data={
        'username': 'portrait-logo-test', 'password': 'isolated-logo-1234',
        'name': name, 'role': 'employer', 'company_tracks': ['检测认证'],
    }).status == 200
    page.goto(base)
    route(page, 'company')
    card = page.locator('.discovery-company').filter(has=page.locator('h4', has_text=name))
    image = card.locator('.company-symbol img')
    for width in [1440, 390]:
        page.set_viewport_size({'width': width, 'height': 900})
        image.scroll_into_view_if_needed()
        image.evaluate('(img)=>img.decode()')
        assert image.evaluate('(img)=>{const a=img.getBoundingClientRect(),b=img.parentElement.getBoundingClientRect();return a.top>=b.top&&a.left>=b.left&&a.bottom<=b.bottom&&a.right<=b.right}')
    page.close()


def test_local_logo_in_company_list_detail_and_image_failure(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1380, 'height': 1000})
    response = page.request.post(base + '/api/auth/register', data={
        'username': 'logo-browser', 'password': 'isolated-logo-1234',
        'name': '7-ELEVEn', 'role': 'employer', 'company_tracks': ['零售消费'],
    })
    assert response.status == 200
    page.goto(base)
    route(page,'company')
    card = page.locator('.discovery-company').filter(has=page.locator('h4', has_text='7-ELEVEn'))
    image = card.locator('.company-symbol img')
    expect(image).to_be_visible()
    image.evaluate('img=>img.decode()')
    assert image.evaluate('img=>img.naturalWidth>0&&getComputedStyle(img).objectFit==="contain"')
    url = image.get_attribute('src')
    assert url.startswith('/api/company-logos/')
    actual = page.request.get(base + url)
    assert actual.status == 200 and actual.body().startswith(b'\x89PNG')
    card.locator('[data-action=market-company]').click()
    expect(page.locator('#modal-content>.company-symbol img')).to_be_visible()
    assert page.locator('#modal-content>.company-symbol img').get_attribute('src') == url
    folder = Path(__file__).resolve().parents[1] / 'runtime' / 'company-logo-review'
    folder.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(folder / 'detail.png'))
    page.locator('[data-action=close-modal]').click()
    page.screenshot(path=str(folder / 'list.png'))
    page.route('**/api/company-logos/*', lambda route: route.fulfill(status=404, body=''))
    page.reload()
    route(page,'company')
    expect(card.locator('.company-initial')).to_be_visible()
    expect(card.locator('.company-symbol img')).to_be_hidden()
    # 未核验企业由正式市场接口保持字母占位。
    page.request.put(base + '/api/company/profile', data={'name': '隔离无商标企业', 'tracks': ['零售消费'], 'description': ''})
    page.reload()
    route(page,'company')
    pending = page.locator('.discovery-company').filter(has=page.locator('h4', has_text='隔离无商标企业'))
    expect(pending.locator('.company-initial')).to_have_text('隔')
    expect(pending.locator('img')).to_have_count(0)
    page.close()
