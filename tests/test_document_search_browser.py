"""Compact document search keeps the reading area and keyboard state stable."""
import os

import pytest
from test_requested_features import workspace_page, open_file
from test_spotlight_navigation_browser import settle

pytestmark = [pytest.mark.browser, pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('work_mode', ['edit', 'review'])
def test_search_replace_shortcuts_options_and_undo(workspace_page, work_mode):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    original = 'cat Cat scatter cat\nitem12 item34\n'
    (root/'note.txt').write_text(original)
    page.goto(url); open_file(page, 'note.txt')
    if work_mode == 'review':
        page.locator('#work-mode').click()
        expect(page.locator('#work-mode')).to_have_attribute('aria-checked', 'true')
    page.locator('.cm-content').click(); page.keyboard.press('Control+Home')
    panel = page.locator('.document-search')
    page.keyboard.press('Control+f')
    expect(panel).to_be_visible()
    expect(panel.locator('[name=search]')).to_be_focused()
    expect(panel.locator('input[name=replace]')).to_be_hidden()
    expect(panel.locator('input[type=checkbox]')).to_have_count(0)
    for button in panel.locator('button').all():
        assert button.get_attribute('title') and button.get_attribute('aria-label')
    panel.locator('[name=search]').fill('cat')
    panel.get_by_role('button', name='Match case', exact=True).click()
    panel.get_by_role('button', name='Whole words', exact=True).click()
    expect(page.locator('.cm-searchMatch')).to_have_count(2)
    page.keyboard.press('Control+h')
    expect(panel.locator('input[name=replace]')).to_be_visible()
    expect(panel.locator('[name=search]')).to_have_value('cat')
    expect(panel.locator('[name=caseSensitive]')).to_have_attribute('aria-pressed', 'true')
    panel.locator('input[name=replace]').fill('dog')
    panel.get_by_role('button', name='Replace all', exact=True).click()
    if work_mode == 'review':
        expect(page.locator('.review-human').filter(has_text='dog')).to_have_text(['dog', 'dog'])
    else:
        expect(page.locator('.cm-content')).to_contain_text('dog Cat scatter dog')
    page.keyboard.press('Control+h')
    expect(panel).to_be_visible(); expect(panel.locator('input[name=replace]')).to_be_hidden()
    expect(panel.locator('[name=search]')).to_have_value('cat')
    page.keyboard.press('Control+h')
    expect(panel.locator('input[name=replace]')).to_have_value('dog')
    page.keyboard.press('Control+f')
    expect(panel).to_be_visible(); expect(panel.locator('input[name=replace]')).to_be_hidden()
    page.keyboard.press('Control+f'); expect(panel).to_have_count(0)
    expect(page.locator('.cm-content')).to_be_focused()
    page.keyboard.press('Control+z'); expect(page.locator('.cm-content')).to_contain_text('cat Cat scatter cat')
    expect(page.locator('#dirty')).to_have_text('')

    page.keyboard.press('Control+Home'); page.keyboard.press('Control+f')
    panel.locator('[name=search]').fill(r'item\d+')
    panel.get_by_role('button', name='Regular expression', exact=True).click()
    page.keyboard.press('Enter')
    expect(page.locator('.cm-searchMatch-selected')).to_have_text('item12')
    page.keyboard.press('Enter')
    expect(page.locator('.cm-searchMatch-selected')).to_have_text('item34')
    page.keyboard.press('Shift+Enter')
    expect(page.locator('.cm-searchMatch-selected')).to_have_text('item12')
    panel.get_by_role('button', name='Select all matches', exact=True).click()
    expect(page.locator('.cm-searchMatch-selected')).to_have_count(2)
    panel.get_by_role('button', name='Previous match (Shift+Enter)', exact=True).click()
    expect(page.locator('.cm-searchMatch-selected')).to_have_text('item34')
    panel.get_by_role('button', name='Next match (Enter)', exact=True).click()
    expect(page.locator('.cm-searchMatch-selected')).to_have_text('item12')
    # Switching from a focused replacement field retains a regex, not its match.
    page.keyboard.press('Control+h'); panel.locator('input[name=replace]').fill('record')
    page.keyboard.press('Control+h'); expect(panel.locator('[name=search]')).to_have_value(r'item\d+')
    page.keyboard.press('Control+h'); panel.locator('input[name=replace]').focus(); page.keyboard.press('Enter')
    expect(page.locator('.cm-content')).to_contain_text('record item34')
    panel.locator('[name=search]').fill('[')
    expect(panel.locator('[name=search]')).to_have_attribute('aria-invalid', 'true')
    panel.locator('[name=search]').fill(r'item\d+')
    expect(panel.locator('[name=search]')).to_have_attribute('aria-invalid', 'false')
    panel.get_by_role('button', name='Close search (Esc)', exact=True).click()
    page.keyboard.press('Control+z'); expect(page.locator('#dirty')).to_have_text('')
    assert (root/'note.txt').read_text() == original


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_search_layout_keeps_full_viewport_and_toolbar_stable(workspace_page):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    (root/'long.md').write_text('# Heading\n\n' + ''.join(f'Paragraph {i:03}.\n\n' for i in range(200)))
    (root/'report.html').write_text('<p>Report</p><div style="height:5000px"></div>')
    page.goto(url)
    for width, theme in [(1440, 'light'), (900, 'dark')]:
        page.set_viewport_size({'width': width, 'height': 800})
        page.evaluate('theme=>document.documentElement.dataset.theme=theme', theme)
        open_file(page, 'long.md')
        settle(page)
        top = page.locator('#go-to-top').bounding_box()
        page.evaluate('''()=>{
          window.topSamples=[];window.sampleTop=true;
          const sample=()=>{if(!window.sampleTop)return;const el=document.querySelector('#go-to-top'),r=el.getBoundingClientRect();
            window.topSamples.push({x:r.x,y:r.y,width:r.width,height:r.height,visible:getComputedStyle(el).display!=='none'});requestAnimationFrame(sample);};sample();
        }''')
        for mode in ['source', 'live', 'preview', 'live']:
            page.locator('#mode').select_option(mode); settle(page)
            surface = page.locator('#surface').bounding_box()
            pane = page.locator('.reading-pane').bounding_box()
            assert abs(surface['height'] - pane['height']) < 1
            assert page.locator('#surface').evaluate('el=>getComputedStyle(el).paddingBottom') == '0px'
        page.locator('#work-mode').click(); settle(page)
        page.locator('#work-mode').click(); settle(page)
        scroller = page.locator('.cm-scroller')
        scroller.evaluate('el=>el.scrollTop=1600'); settle(page)
        geometry = scroller.bounding_box(); scroll = scroller.evaluate('el=>el.scrollTop')
        # Toolbar focus also routes the document shortcut correctly.
        page.locator('#go-to-top').focus(); page.keyboard.press('Control+f'); settle(page)
        panel = page.locator('.document-search'); expect(panel).to_be_visible()
        box = panel.bounding_box()
        assert geometry['x'] <= box['x'] and box['x'] + box['width'] <= geometry['x'] + geometry['width']
        assert 0 <= box['y'] - geometry['y'] <= 12
        assert abs(geometry['x'] + geometry['width'] - box['x'] - box['width']) <= 12
        assert abs(scroller.bounding_box()['height'] - geometry['height']) < 1
        assert abs(scroller.evaluate('el=>el.scrollTop') - scroll) < 2
        assert panel.evaluate('el=>el.scrollWidth<=el.clientWidth')
        page.keyboard.press('Control+h'); settle(page)
        assert abs(scroller.bounding_box()['height'] - geometry['height']) < 1
        assert abs(scroller.evaluate('el=>el.scrollTop') - scroll) < 2
        page.keyboard.press('Escape'); expect(panel).to_have_count(0)
        samples = page.evaluate('()=>{window.sampleTop=false;return window.topSamples;}')
        assert samples and all(sample['visible'] and sample['width'] > 0 for sample in samples)
        assert all(abs(sample['x'] - top['x']) < 1 and abs(sample['y'] - top['y']) < 1 for sample in samples)
        for name in ['report.html', 'long.md']:
            open_file(page, name); settle(page)
            if name.endswith('.html'):
                frame = page.locator('#html-preview').bounding_box()
                surface = page.locator('#surface').bounding_box()
                assert abs(frame['height'] - surface['height']) < 1
                before = page.locator('#go-to-top').bounding_box()
                page.locator('#html-toggle').click(); settle(page)
                after = page.locator('#go-to-top').bounding_box()
                assert abs(before['x'] - after['x']) < 1 and abs(before['y'] - after['y']) < 1
                page.locator('#html-toggle').click()


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_search_is_scoped_and_read_only_context_cannot_replace(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    (root/'note.txt').write_text('First phrase. Second phrase.')
    thread = ws.create_thread('note.txt', 0, 5, 'Discuss this', 'Reviewer', ws.read('note.txt')['version'])
    page.goto(url); open_file(page, 'note.txt')
    page.locator(f'.thread[data-thread="{thread["id"]}"] [data-action=original]').click()
    expect(page.locator('.original-editor')).to_be_visible()
    page.locator('#go-to-top').focus(); page.keyboard.press('Control+h')
    panel = page.locator('.document-search'); expect(panel).to_be_visible()
    expect(panel.locator('input[name=replace]')).to_be_hidden()
    expect(panel.locator('[name=toggleReplace]')).to_be_hidden()
    page.keyboard.press('Escape'); expect(panel).to_have_count(0)
    expect(page.locator('.original-editor')).to_be_visible()
    page.keyboard.press('Escape'); expect(page.locator('.original-editor')).to_have_count(0)
    page.locator('#thread-search').fill('phrase')
    page.keyboard.press('Escape')
    expect(page.locator('#thread-search')).to_have_value('')
    assert (root/'note.txt').read_text() == 'First phrase. Second phrase.'
