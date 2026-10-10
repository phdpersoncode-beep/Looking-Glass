"""Stable focus and autosave feedback through real user interactions."""
import os
import pytest
from test_requested_features import workspace_page, open_file
from test_spotlight_navigation_browser import settle
from test_discussion_reading_browser import endpoint

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_review_toggle_and_quiet_autosave(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    (root / 'note.txt').write_text('Original text.\n')
    page.goto(url); open_file(page, 'note.txt')
    toggle = page.get_by_role('switch', name='Review mode')
    expect(toggle).to_have_attribute('aria-checked', 'false')
    toggle.focus(); page.keyboard.press('Space')
    expect(toggle).to_have_attribute('aria-checked', 'true')
    held = []
    page.route('**/api/reviews/*', lambda route: held.append(route)
               if route.request.method == 'PATCH' else route.continue_())
    page.evaluate('''()=>{
      window.dirtyFlashes=[];
      new MutationObserver(()=>{
        if(document.querySelector('#dirty').textContent || document.querySelector('.tab-name').textContent.includes('•'))window.dirtyFlashes.push(true);
      }).observe(document.querySelector('.main-pane')||document.body,{subtree:true,childList:true,characterData:true});
    }''')
    page.locator('.cm-content').click(); page.keyboard.press('Control+End')
    page.keyboard.insert_text('Human addition')
    expect(page.locator('#review-status')).to_have_text('Saving review…')
    expect(page.locator('#dirty')).to_have_text('')
    expect(page.locator('.tab-name')).not_to_contain_text('•')
    page.wait_for_timeout(600)
    assert held
    held[0].continue_(); page.unroute('**/api/reviews/*')
    expect(page.locator('#review-status')).to_have_text('Review saved')
    assert page.evaluate('window.dirtyFlashes') == []
    assert ws.reviews.read(ws.reviews.list()[0]['id'])['content'].endswith('Human addition')
    assert (root / 'note.txt').read_text() == 'Original text.\n'
    toggle.focus(); page.keyboard.press('Enter')
    expect(toggle).to_have_attribute('aria-checked', 'false')
    page.locator('.cm-content').click(); page.keyboard.press('Control+End'); page.keyboard.insert_text('Manual edit')
    expect(page.locator('#dirty')).to_contain_text('Unsaved')
    expect(page.locator('.tab-name')).to_contain_text('•')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'preview', 'source'])
def test_many_highlights_reuse_text_and_hold_viewport(workspace_page, mode):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = '| Passage | Value |\n| --- | --- |\n' + ''.join(
        f'| Passage {i:03} | value {i} |\n' for i in range(80))
    (root / 'note.md').write_text(text)
    version = ws.read('note.md')['version']
    threads = []
    for i in range(80):
        quote = f'Passage {i:03}'; start = text.index(quote)
        threads.append(ws.create_thread('note.md', start, start + len(quote), f'Comment {i}', 'Reviewer', version))
    page.goto(url); open_file(page, 'note.md'); page.locator('#mode').select_option(mode)
    expect(page.locator('.thread')).to_have_count(80)
    target = page.locator('#surface [data-anchor]').filter(has_text='Passage 005').first
    target.scroll_into_view_if_needed(); settle(page)
    page.evaluate('''()=>{
      window.passageNodes=[...document.querySelectorAll('#surface [data-anchor]')].map(el=>[el,el.firstChild]);
      window.readingScroll=(document.querySelector('.cm-scroller')||document.querySelector('#surface')).scrollTop;
    }''')
    for i in [5, 6, 7, 5]:
        mark = page.locator('#surface [data-anchor]').filter(has_text=f'Passage {i:03}').first
        point = endpoint(mark, 3); page.mouse.click(**point); settle(page)
        expect(page.locator('.thread.active')).to_have_attribute('data-thread', str(threads[i]['id']))
        assert page.evaluate('window.passageNodes.every(([el,text])=>el.isConnected&&text.isConnected)')
        assert page.evaluate('Math.abs((document.querySelector(".cm-scroller")||document.querySelector("#surface")).scrollTop-window.readingScroll)') < 2
    assert (root / 'note.md').read_text() == text


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_thread_card_focus_preserves_selection_and_controls(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = 'First passage.\nSecond passage.\n'
    (root / 'note.txt').write_text(text); version = ws.read('note.txt')['version']
    first = ws.create_thread('note.txt', 0, 5, 'Copy these words. [Reference](https://example.invalid)', 'Reviewer', version)
    second = ws.create_thread('note.txt', 15, 21, 'Other discussion', 'Reviewer', version)
    page.goto(url); open_file(page, 'note.txt')
    a = page.locator(f'.thread[data-thread="{first["id"]}"]')
    b = page.locator(f'.thread[data-thread="{second["id"]}"]')
    b.click(position={'x':4,'y':4}); expect(b).to_have_class('thread active')
    a.locator('.comment-markdown p').click(position={'x':15,'y':8}); expect(a).to_have_class('thread active')
    a.locator('textarea').fill('Draft reply')
    expect(a.locator('textarea')).to_be_focused()
    # Double-click and drag selections remain in the sidebar, ready to copy.
    a.locator('.comment-markdown p').dblclick(position={'x':15,'y':8})
    assert page.evaluate('window.getSelection().toString()')
    page.evaluate('window.getSelection().removeAllRanges()')
    b.focus(); page.keyboard.press('Enter'); expect(b).to_have_class('thread active')
    paragraph = a.locator('.comment-markdown p')
    start = endpoint(paragraph, 0); end = endpoint(paragraph, 10)
    page.mouse.move(**start); page.mouse.down(); page.mouse.move(**end, steps=12); page.mouse.up()
    assert page.evaluate('window.getSelection().toString()')
    expect(b).to_have_class('thread active')
    page.evaluate('window.getSelection().removeAllRanges()')
    a.locator('blockquote').dblclick(position={'x':18,'y':12})
    assert page.evaluate('window.getSelection().toString()')
    page.evaluate('window.getSelection().removeAllRanges()')
    b.focus(); page.keyboard.press('Enter')
    with page.expect_popup() as popup:
        a.get_by_role('link', name='Reference').click()
    popup.value.close()
    expect(b).to_have_class('thread active')
    a.get_by_role('button', name='Edit comment', exact=True).click()
    expect(page.locator('#edit-comment-dialog')).to_be_visible()
    page.locator('#edit-comment-dialog [data-close]').click()
    expect(b).to_have_class('thread active')
    a.get_by_role('button', name='Resolve thread', exact=True).click()
    expect(a).to_be_hidden()
