"""Reading affordances remain quiet, legible, and usable in both themes."""
import os

import pytest
from test_requested_features import workspace_page, open_file
from test_spotlight_navigation_browser import settle

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('name,mode', [
    ('note.md', 'live'), ('note.md', 'source'), ('note.txt', None), ('note.py', None),
])
def test_monospace_line_numbers_follow_edits_and_fit_the_reading_pane(workspace_page, name, mode):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    text = '\n'.join(f"line_{i} = 'A little text to read.'" for i in range(1, 121))
    (root/name).write_text(text)
    page.goto(url); open_file(page, name)
    if mode:
        page.locator('#mode').select_option(mode)
    gutter = page.locator('.cm-lineNumbers')
    expect(gutter).to_be_visible()
    for theme, width in [('light', 1440), ('dark', 900)]:
        if page.locator('html').get_attribute('data-theme') != theme:
            page.locator('#theme').click()
        page.set_viewport_size({'width': width, 'height': 800}); settle(page)
        assert gutter.evaluate("el=>getComputedStyle(el).fontFamily").replace(' ', '') == page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--mono').trim()").replace(' ', '')
        bounds = gutter.bounding_box()
        assert 20 <= bounds['width'] <= 65
        # Numbers and content occupy separate columns, including at three digits.
        content = page.locator('.cm-content').bounding_box()
        assert content['x'] >= bounds['x'] + bounds['width'] - 1
        if name != 'note.py':
            assert page.locator('.cm-scroller').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
    page.locator('.cm-content').click(); page.keyboard.press('Control+End')
    expect(gutter.locator('.cm-gutterElement', has_text='120').last).to_be_visible()
    page.keyboard.press('Enter'); page.keyboard.insert_text('New final line')
    expect(gutter.locator('.cm-gutterElement', has_text='121').last).to_be_visible()
    page.keyboard.press('Control+s'); expect(page.locator('#dirty')).to_have_text('')
    assert (root/name).read_text() == text + '\nNew final line'


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'preview'])
def test_fenced_code_has_one_background_rounded_ends_and_quiet_quotes(workspace_page, mode):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    text = '# Reading\n\n```python\nvalue = 42\nprint(value)\n```\n\n' \
        '> First quoted line\n> Second quoted line\n\nInline `code` remains distinct.\n'
    (root/'note.md').write_text(text)
    page.goto(url); open_file(page, 'note.md'); page.locator('#mode').select_option(mode)
    code = page.locator('.md-code-block').first if mode == 'live' else page.locator('.markdown-preview pre')
    quote = page.locator('.md-quote').first if mode == 'live' else page.locator('.markdown-preview blockquote')
    expect(code).to_be_visible(); expect(quote).to_be_visible()
    for theme in ['light', 'dark']:
        if page.locator('html').get_attribute('data-theme') != theme:
            page.locator('#theme').click()
        if mode == 'live':
            code.click()  # The caret/active-line style must not create a stripe.
            expect(page.locator('.md-quote')).to_have_count(2)
            edges = [page.locator('.md-code-start'), page.locator('.md-code-end')]
        else:
            edges = [code, code]
        assert edges[0].evaluate('el=>parseFloat(getComputedStyle(el).borderTopLeftRadius)') >= 8
        assert edges[1].evaluate('el=>parseFloat(getComputedStyle(el).borderBottomLeftRadius)') >= 8
        assert code.evaluate('''el=>{
          const panel=getComputedStyle(el).backgroundColor;
          const lines=[el,...el.querySelectorAll('*')];
          return lines.every(node=>['rgba(0, 0, 0, 0)','transparent',panel].includes(getComputedStyle(node).backgroundColor));
        }''')
        assert quote.evaluate('el=>getComputedStyle(el).fontStyle') == 'normal'
        assert quote.evaluate('el=>getComputedStyle(el).backgroundColor') in ['rgba(0, 0, 0, 0)', 'transparent']
        assert quote.evaluate('el=>parseFloat(getComputedStyle(el).borderLeftWidth)') == 2
    inline = page.locator('.md-code') if mode == 'live' else page.locator('.markdown-preview p code')
    expect(inline).to_have_text('code')
    assert inline.evaluate('el=>getComputedStyle(el).backgroundColor') not in ['rgba(0, 0, 0, 0)', 'transparent']
    assert (root/'note.md').read_text() == text
