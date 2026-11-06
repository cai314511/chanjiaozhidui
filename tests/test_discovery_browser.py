from pathlib import Path

from playwright.sync_api import expect

from tests.test_browser import browser_system, register, route
from tests.test_api import job_data


def test_company_tracks_guided_exploration_search_and_favorites(browser_system):
    browser, base = browser_system
    employer = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    employer.on('pageerror', lambda error: errors.append(str(error)))
    employer.goto(base)
    employer.locator('.topbar [data-action=register]').click()
    form = employer.locator('#auth-form')
    for name, value in {'username': 'discovery-company', 'password': 'test-password-123', 'name': '隔离多赛道企业'}.items():
        form.locator(f'[name={name}]').fill(value)
    form.locator('[name=role]').select_option('employer')
    for track in ['农业', '生物医药', '新材料探索']:
        form.locator('#company-track-input').fill(track)
        form.locator('#add-company-track').click()
    form.locator('[type=submit]').click()
    expect(employer.locator('#modal')).not_to_be_visible()
    assert employer.request.get(base + '/api/company/profile').json()['tracks'] == ['农业', '生物医药', '新材料探索']
    assert employer.request.post(base + '/api/jobs', data={**job_data(), 'industry': '农业', 'title': '农业数据研究员'}).status == 200

    student = browser.new_page(viewport={'width': 1440, 'height': 1000})
    student.on('pageerror', lambda error: errors.append(str(error)))
    register(student, base, 'student', 'discovery-student', dismiss_exploration=False)
    modal = student.locator('#exploration-dialog')
    expect(modal).to_be_visible()
    for choice in ['科学与健康', '研究实验与探索', '医疗与健康']:
        modal.locator(f'[data-action=guide-select][data-id="{choice}"]').click()
        modal.locator('[data-action=guide-next]').click()
    expect(modal).to_contain_text('这些方向，值得先了解一下')
    modal.locator('[data-action=favorite-track][data-id="生物医药"]').click()
    expect(student.locator('#toast')).to_contain_text('收藏')
    modal.locator('[data-action=guide-explore][data-id="生物医药"]').click()
    expect(modal).not_to_be_visible()
    expect(student.locator('.discovery-company')).to_contain_text('隔离多赛道企业')
    expect(student.locator('#discovery-form [name=track]')).to_have_value('生物医药')
    student.locator('.discovery-company [data-action=favorite-company]').click()
    route(student, 'my-space')
    expect(student.locator('#space-favorites')).to_contain_text('隔离多赛道企业')
    expect(student.locator('#space-favorites')).to_contain_text('生物医药')
    expect(student.locator('#space-feed')).to_contain_text('农业数据研究员')
    student.reload()
    expect(student.locator('#discovery-form')).to_be_visible()
    expect(student.locator('#exploration-dialog')).not_to_be_visible()
    student.locator('[data-action=exploration-start]').click()
    expect(modal).to_be_visible()
    folder = Path(__file__).resolve().parents[1] / 'runtime' / 'discovery-review'
    folder.mkdir(parents=True, exist_ok=True)
    student.screenshot(path=str(folder / 'guide-desktop.png'))
    student.set_viewport_size({'width': 390, 'height': 844})
    assert modal.evaluate('(el)=>el.scrollWidth<=el.clientWidth')
    student.screenshot(path=str(folder / 'guide-mobile.png'))
    modal.locator('[data-action=explore-skip][aria-label="跳过探索"]').click()
    student.locator('#discovery-form [name=q]').fill('隔离多赛道企业')
    student.locator('#discovery-form [type=submit]').click()
    expect(student.locator('.discovery-company')).to_have_count(1)
    assert student.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert errors == [], errors
    student.close()
    employer.close()


def test_job_pagination_is_available_when_company_count_is_small(browser_system):
    browser, base = browser_system
    company = browser.new_context()
    assert company.request.post(base + '/api/auth/register', data={'username': 'paging-company', 'password': 'test-password-123',
        'name': '分页专用企业', 'role': 'employer', 'company_tracks': ['农业']}).status == 200
    for index in range(25):
        assert company.request.post(base + '/api/jobs', data={**job_data(), 'title': f'分页验证岗位{index}', 'industry': '农业'}).status == 200
    page = browser.new_page()
    register(page, base, 'student', 'paging-student')
    page.locator('#discovery-form [name=q]').fill('分页专用企业')
    page.locator('#discovery-form [type=submit]').click()
    expect(page.locator('.discovery-job')).to_have_count(20)
    page.locator('[data-action=market-page]').click()
    expect(page.locator('.discovery-job')).to_have_count(5)
    page.close()
    company.close()
