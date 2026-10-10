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


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_approval_confirmation_cancel_and_layout(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    (root / 'note.txt').write_text('Original\n')
    page.goto(url); open_file(page, 'note.txt')
    toggle = page.locator('#work-mode')
    for width, theme in [(1440, 'light'), (900, 'dark')]:
        page.set_viewport_size({'width': width, 'height': 800})
        page.evaluate("theme=>document.documentElement.dataset.theme=theme", theme)
        before = toggle.bounding_box()
        toggle.click(); expect(toggle).to_have_attribute('aria-checked', 'true')
        after = toggle.bounding_box()
        assert abs(before['x'] - after['x']) < 1 and abs(before['y'] - after['y']) < 1
        button = page.locator('#approve-review'); expect(button).to_be_visible()
        pane = page.locator('.reading-pane').bounding_box(); box = button.bounding_box()
        assert 0 <= pane['x'] + pane['width'] - box['x'] - box['width'] <= 20
        assert 0 <= pane['y'] + pane['height'] - box['y'] - box['height'] <= 15
        assert button.locator('svg').count() == 1
        assert button.evaluate("el=>getComputedStyle(el).borderTopColor===getComputedStyle(el).color")
        toggle.click(); expect(toggle).to_have_attribute('aria-checked', 'false')
    toggle.click(); expect(toggle).to_have_attribute('aria-checked', 'true')
    page.locator('.cm-content').click(); page.keyboard.press('Control+End'); page.keyboard.insert_text('Proposal')
    requests = []
    page.on('request', lambda r: requests.append(r.url) if r.url.endswith('/approve') else None)
    dialog = page.locator('#review-approve-dialog')
    for cancel in ['button', 'escape']:
        page.locator('#approve-review').click(); expect(dialog).to_be_visible()
        expect(dialog).to_contain_text('replaces the original file on disk')
        expect(page.locator('#review-approve-path')).to_have_text('note.txt')
        expect(dialog.get_by_role('button', name='Cancel')).to_be_focused()
        if cancel == 'button':
            dialog.get_by_role('button', name='Cancel').click()
        else:
            page.keyboard.press('Escape')
        expect(dialog).to_be_hidden()
        assert requests == []
        assert (root / 'note.txt').read_text() == 'Original\n'
        expect(toggle).to_have_attribute('aria-checked', 'true')
    page.locator('#approve-review').click(); page.locator('#confirm-review-approve').click()
    expect(toggle).to_have_attribute('aria-checked', 'false')
    assert len(requests) == 1
    assert (root / 'note.txt').read_text() == 'Original\nProposal'


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_confirmation_does_not_approve_a_newer_agent_revision(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    (root / 'note.txt').write_text('Original')
    page.goto(url); open_file(page, 'note.txt'); page.locator('#work-mode').click()
    expect(page.locator('#review-status')).to_have_text('Review saved')
    page.locator('#approve-review').click()
    expect(page.locator('#review-approve-dialog')).to_be_visible()
    draft = ws.reviews.read(ws.reviews.list()[0]['id'])
    ws.reviews.update(draft['id'], draft['version'], [dict(start=8, end=8, insert=' agent edit')], 'Agent', 'agent')
    expect(page.locator('.review-agent')).to_have_text('agent edit')
    page.locator('#confirm-review-approve').click()
    expect(page.locator('#notice')).to_contain_text('review changed while confirmation was open')
    assert (root / 'note.txt').read_text() == 'Original'
    page.locator('#approve-review').click(); page.locator('#confirm-review-approve').click()
    expect(page.locator('#work-mode')).to_have_attribute('aria-checked', 'false')
    assert (root / 'note.txt').read_text() == 'Original agent edit'


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('name,text', [('data.json', '{"value":1}'), ('report.HTML', '<p>Original</p>'), ('report.htm', '<p>Original</p>')])
def test_json_html_ignore_review_preference_and_preserve_existing_drafts(workspace_page, name, text):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    (root / 'note.txt').write_text('Reviewable')
    (root / name).write_text(text)
    # Old drafts remain stored, but the UI always opens the ordinary disk file.
    draft = ws.reviews.start(name, ws.read(name)['version'])
    ws.reviews.update(draft['id'], draft['version'], [dict(start=len(text), end=len(text), insert=' old proposal')], 'Agent', 'agent')
    page.goto(url); open_file(page, 'note.txt'); page.locator('#work-mode').click()
    expect(page.locator('#work-mode')).to_have_attribute('aria-checked', 'true')
    open_file(page, name)
    for selector in ['#work-mode', '#approve-review', '#review-status', '#review-history']:
        expect(page.locator(selector)).to_be_hidden()
    page.reload(); expect(page.locator('#document-name')).to_have_text(name)
    expect(page.locator('#work-mode')).to_be_hidden()
    if name != 'data.json':
        expect(page.frame_locator('#html-preview').locator('p')).to_have_text('Original')
        page.locator('#html-toggle').click()
    expect(page.locator('.cm-content')).not_to_contain_text('old proposal')
    page.locator('.cm-content').click(); page.keyboard.press('Control+End'); page.keyboard.insert_text(' ')
    expect(page.locator('#dirty')).to_contain_text('Unsaved')
    page.locator('#save').click(); expect(page.locator('#dirty')).to_have_text('')
    assert (root / name).read_text() == text + ' '
    assert ws.reviews.read(draft['id'])['content'] == text + ' old proposal'
    assert len(ws.reviews.list()) == 2
    open_file(page, 'note.txt'); expect(page.locator('#work-mode')).to_have_attribute('aria-checked', 'true')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'preview', 'source'])
def test_thread_card_scrolls_to_passage_without_stealing_sidebar_focus(workspace_page, mode):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = ''.join(f'Paragraph {i:03}: a passage with surrounding context.\n\n' for i in range(100))
    (root / 'note.md').write_text(text)
    quote = 'Paragraph 090'; start = text.index(quote)
    thread = ws.create_thread('note.md', start, start + len(quote), 'Far-away passage', 'Reviewer', ws.read('note.md')['version'])
    page.goto(url); open_file(page, 'note.md'); page.locator('#mode').select_option(mode)
    card = page.locator(f'.thread[data-thread="{thread["id"]}"]')
    card.focus(); card.click(position={'x':4,'y':4})
    expect(card).to_have_class('thread active')
    expect(card).to_be_focused()
    mark = page.locator('#surface [data-anchor]').filter(has_text=quote).first
    expect(mark).to_be_in_viewport()
    settle(page)
    scroller = '.cm-scroller' if mode != 'preview' else '#surface'
    assert page.locator(scroller).evaluate('el=>el.scrollTop') > 100
    # Clicking the already-active card navigates again after manual scrolling.
    page.locator(scroller).evaluate('el=>el.scrollTop=0'); settle(page)
    card.locator('.comment-markdown p').click()
    expect(mark).to_be_in_viewport()
    assert page.locator(scroller).evaluate('el=>el.scrollTop') > 100
    assert (root / 'note.md').read_text() == text
