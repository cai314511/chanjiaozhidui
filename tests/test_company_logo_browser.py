"""已核验品牌走正式注册、检索与本地图像端点；缺图故障单独模拟。"""

from pathlib import Path

from playwright.sync_api import expect

from tests.test_browser import browser_system


def test_local_logo_in_company_list_detail_and_image_failure(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1380, 'height': 1000})
    response = page.request.post(base + '/api/auth/register', data={
        'username': 'logo-browser', 'password': 'isolated-logo-1234',
        'name': '7-ELEVEn', 'role': 'employer', 'company_tracks': ['零售消费'],
    })
    assert response.status == 200
    page.goto(base)
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
    expect(card.locator('.company-initial')).to_be_visible()
    expect(card.locator('.company-symbol img')).to_be_hidden()
    # 未核验企业由正式市场接口保持字母占位。
    page.request.put(base + '/api/company/profile', data={'name': '隔离无商标企业', 'tracks': ['零售消费'], 'description': ''})
    page.reload()
    pending = page.locator('.discovery-company').filter(has=page.locator('h4', has_text='隔离无商标企业'))
    expect(pending.locator('.company-initial')).to_have_text('隔')
    expect(pending.locator('img')).to_have_count(0)
    page.close()
