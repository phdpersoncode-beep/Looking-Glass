"""Behavior contracts across architecture boundaries, in both browser engines."""
import os
import pytest
from test_requested_features import workspace_page, open_file
from test_spotlight_navigation_browser import settle

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_repeated_card_activation_reveals_same_passage(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = ''.join(f'Line {i:03}\n' for i in range(180))
    (root / 'note.txt').write_text(text)
    start = text.index('Line 150')
    thread = ws.create_thread('note.txt', start, start + 8, 'Far passage', 'Reviewer', ws.read('note.txt')['version'])
    page.goto(url); open_file(page, 'note.txt')
    card = page.locator(f'.thread[data-thread="{thread["id"]}"]')
    card.click(position={'x': 4, 'y': 4}); settle(page)
    first = page.locator('.cm-scroller').evaluate('el=>el.scrollTop')
    assert first > 500
    page.locator('.cm-scroller').evaluate('el=>el.scrollTop=0'); settle(page)
    card.click(position={'x': 4, 'y': 4}); settle(page)
    expect(card).to_have_class('thread active')
    assert abs(page.locator('.cm-scroller').evaluate('el=>el.scrollTop') - first) < 3


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_mode_switch_preserves_each_modes_undo(workspace_page):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    (root / 'note.txt').write_text('Original')
    page.goto(url); open_file(page, 'note.txt')
    page.locator('.cm-content').click(); page.keyboard.press('Control+End')
    page.keyboard.insert_text(' edit'); page.locator('#save').click()
    expect(page.locator('#dirty')).to_have_text('')
    page.locator('#work-mode').click()
    expect(page.locator('#work-mode')).to_have_attribute('aria-checked', 'true')
    page.locator('.cm-content').click(); page.keyboard.press('Control+End')
    page.keyboard.insert_text(' proposal')
    expect(page.locator('#review-status')).to_have_text('Review saved')
    page.locator('#work-mode').click()
    expect(page.locator('#work-mode')).to_have_attribute('aria-checked', 'false')
    page.locator('.cm-content').click(); page.keyboard.press('Control+z')
    expect(page.locator('.cm-content')).to_have_text('Original')
    page.keyboard.press('Control+Shift+z')
    expect(page.locator('.cm-content')).to_have_text('Original edit')
    expect(page.locator('#dirty')).to_have_text('')
    page.locator('#work-mode').click()
    expect(page.locator('.cm-content')).to_contain_text('proposal')
    page.locator('.cm-content').click(); page.keyboard.press('Control+z')
    expect(page.locator('.cm-content')).to_have_text('Original edit')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_queued_navigation_waits_for_target_before_reveal(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    (root / 'a.txt').write_text('Alpha')
    (root / 'b.txt').write_text('Beta passage')
    thread = ws.create_thread('b.txt', 5, 12, 'Target in B', 'Reviewer', ws.read('b.txt')['version'])
    page.goto(url); page.locator('#thread-scope').check()
    expect(page.locator('.thread')).to_have_count(1)
    held = []
    page.route('**/api/file?*', lambda route: held.append(route)
               if 'path=a.txt' in route.request.url else route.continue_())
    page.locator('.file-entry[data-path="a.txt"]').click()
    page.wait_for_function('()=>true')
    page.locator(f'.thread[data-thread="{thread["id"]}"] blockquote').click()
    assert held
    held[0].continue_()
    expect(page.locator('#document-name')).to_have_text('b.txt')
    expect(page.locator('.thread.active')).to_have_attribute('data-thread', str(thread['id']))
    page.locator('#annotate').click()
    expect(page.locator('#selected-quote')).to_have_text('passage')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_poll_updates_keep_cards_messages_composers_and_selection(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    (root / 'note.txt').write_text('First second')
    version = ws.read('note.txt')['version']
    first = ws.create_thread('note.txt', 0, 5, 'Native copying survives replies.', 'Reviewer', version)
    second = ws.create_thread('note.txt', 6, 12, 'Other discussion', 'Reviewer', version)
    page.goto(url); open_file(page, 'note.txt')
    card = page.locator(f'.thread[data-thread="{first["id"]}"]')
    card.click(position={'x': 4, 'y': 4})
    field = card.locator('textarea'); field.fill('Unsent reply')
    field.evaluate('el=>el.setSelectionRange(2,6)')
    page.evaluate('''id=>{const card=document.querySelector(`[data-thread="${id}"]`);
      window.heldDiscussionNodes=[card,card.querySelector('.message'),card.querySelector('.comment-markdown p').firstChild,card.querySelector('.reply-form'),card.querySelector('textarea')];
    }''', first['id'])
    ws.reply(first['id'], 'Incoming reply', 'Agent')
    expect(card.locator('.comment-markdown').last).to_have_text('Incoming reply')
    assert page.evaluate('window.heldDiscussionNodes.every(node=>node.isConnected)')
    expect(field).to_be_focused(); expect(field).to_have_value('Unsent reply')
    assert field.evaluate('el=>[el.selectionStart,el.selectionEnd]') == [2, 6]
    card.locator('.comment-markdown p').first.evaluate('''el=>{const range=document.createRange();range.selectNodeContents(el);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);}''')
    selected = page.evaluate('getSelection().toString()')
    ws.reply(second['id'], 'Unrelated update', 'Agent')
    expect(page.locator(f'.thread[data-thread="{second["id"]}"] .comment-markdown').last).to_have_text('Unrelated update')
    assert page.evaluate('getSelection().toString()') == selected
    assert page.evaluate('window.heldDiscussionNodes.every(node=>node.isConnected)')
