"""Thread navigation must stay in spotlight throughout repeated key presses."""
import os

import pytest
from test_requested_features import workspace_page, open_file
from test_spotlight_navigation_browser import settle
from test_spotlight_controls_browser import discussions

pytestmark = [pytest.mark.browser, pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_all_thread_navigation_clicks_enter_spotlight_and_keep_keyboard_focus(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    threads = discussions(root, ws)
    page.goto(url); open_file(page, 'note.md')
    card = page.locator(f'.thread[data-thread="{threads[0]["id"]}"]')
    for selector in ['.thread-heading [data-action=jump]', 'blockquote[data-action=jump]', '.comment-markdown p', None, '.thread-summary']:
        page.keyboard.press('Escape')
        if selector == '.thread-summary':
            card.locator('[data-action=collapse-thread]').click()
        if selector:
            card.locator(selector).click()
        else:
            card.click(position={'x':4, 'y':4})
        expect(page.locator('#passage-spotlight')).to_be_visible()
        assert card.evaluate('el=>el.contains(document.activeElement)')
        # No manual focus call: clicking any navigation target must make arrows work.
        page.keyboard.press('ArrowRight')
        expect(page.locator('.thread.active')).to_have_attribute('data-thread', str(threads[1]['id']))
        page.keyboard.press('ArrowLeft')
        expect(card).to_have_class('thread active')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_keyboard_hints_are_visible_without_hovering(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    discussions(root, ws)
    page.goto(url); open_file(page, 'note.md')
    search_y = page.locator('#thread-search').bounding_box()['y']
    page.locator('.thread .thread-heading [data-action=jump]').first.click()
    hints = page.locator('#spotlight-shortcuts')
    expect(hints).to_be_visible()
    for text in ['←', '→', '↑', '↓', 'Threads', 'Search', 'Reply']:
        expect(hints).to_contain_text(text)
    assert page.locator('#thread-search').bounding_box()['y'] == search_y


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_repeated_cross_file_arrows_keep_spotlight_until_latest_destination_ready(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    threads = []
    for name in ['a.txt', 'b.txt', 'c.txt']:
        (root/name).write_text('Target passage in ' + name)
        threads.append(ws.create_thread(name, 0, 6, 'Review ' + name, 'Reviewer', ws.read(name)['version']))
    page.goto(url); open_file(page, 'a.txt'); page.locator('#thread-scope').check()
    first = page.locator(f'.thread[data-thread="{threads[0]["id"]}"]')
    first.click(position={'x':4, 'y':4}); expect(page.locator('#passage-spotlight')).to_be_visible()
    first.locator('textarea').fill('Unsent draft'); first.focus()
    held = []
    def hold(route):
        if 'path=b.txt' in route.request.url:
            held.append(route); page.evaluate('window.blockedArrowRead = true')
        else:
            route.continue_()
    page.route('**/api/file?*', hold)
    page.keyboard.press('ArrowRight')
    page.wait_for_function('()=>window.blockedArrowRead === true')
    expect(page.locator('#passage-spotlight')).to_be_visible()
    expect(first).to_be_visible()
    page.keyboard.press('ArrowRight')
    # Keep every displayed frame, rather than checking only the settled destination.
    page.evaluate('''()=>{window.arrowFrames=[];let frames=50;function sample(){
      const heading=document.querySelector('#passage-spotlight'),cards=[...document.querySelectorAll('.thread')].filter(el=>!el.hidden);
      window.arrowFrames.push({spotlight:!heading.hidden,active:cards.filter(el=>el.classList.contains('active')).length,name:document.querySelector('#document-name').textContent});
      if(--frames)requestAnimationFrame(sample);
    }requestAnimationFrame(sample);}''')
    held[0].continue_()
    expect(page.locator('#document-name')).to_have_text('c.txt')
    expect(page.locator('.thread.active')).to_have_attribute('data-thread', str(threads[2]['id']))
    expect(page.locator('.thread.active')).to_be_focused(); settle(page)
    samples = page.evaluate('window.arrowFrames')
    assert samples and all(sample['spotlight'] and sample['active'] == 1 for sample in samples), samples
    assert all(sample['name'] != 'b.txt' for sample in samples), samples
    page.keyboard.press('ArrowRight')
    expect(page.locator('#document-name')).to_have_text('a.txt')
    expect(first.locator('textarea')).to_have_value('Unsent draft')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'source', 'preview'])
def test_arrow_key_burst_keeps_one_spotlight_and_no_document_selection_popup(workspace_page, mode):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = ''.join(f'## Passage {i:02}\n\n[Reference](https://example.invalid/long-link) **Paragraph {i:02}**\n\n| Name | Value |\n| --- | --- |\n| Item | {i} |\n\n' for i in range(15))
    (root/'note.md').write_text(text); version = ws.read('note.md')['version']
    threads = []
    for i in range(15):
        start = text.index(f'Paragraph {i:02}')
        threads.append(ws.create_thread('note.md', start, start+12, 'Review paragraph', 'Reviewer', version))
    page.goto(url); open_file(page, 'note.md'); page.locator('#mode').select_option(mode)
    page.locator('.thread .thread-heading [data-action=jump]').first.click()
    expect(page.locator('#passage-spotlight')).to_be_visible(); settle(page)
    page.locator('.thread.active textarea').fill('Keep this draft')
    page.locator('.thread.active').focus()
    page.evaluate('''()=>{window.burstSurface=document.querySelector('#surface').firstElementChild;
      window.burstFrames=[];let remaining=25;function sample(){
        window.burstFrames.push({spotlight:!document.querySelector('#passage-spotlight').hidden,
          active:document.querySelectorAll('.thread.active:not([hidden])').length,
          surface:window.burstSurface===document.querySelector('#surface').firstElementChild,
          popup:!document.querySelector('#selection-tools').hidden});
        if(--remaining)requestAnimationFrame(sample);
      }requestAnimationFrame(sample);
      for(let i=0;i<7;i++)document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',repeat:i>0,bubbles:true,cancelable:true}));
    }''')
    expect(page.locator('.thread.active')).to_have_attribute('data-thread', str(threads[7]['id']))
    expect(page.locator('.thread.active')).to_be_focused(); settle(page)
    frames = page.evaluate('window.burstFrames')
    assert frames and all(frame['spotlight'] and frame['active'] == 1 and frame['surface'] and not frame['popup'] for frame in frames), frames
    page.keyboard.press('Escape')
    page.locator(f'.thread[data-thread="{threads[0]["id"]}"] .thread-heading [data-action=jump]').click()
    expect(page.locator('.thread.active textarea')).to_have_value('Keep this draft')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_thread_click_cancels_an_unfinished_arrow_document_load(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    threads = []
    for name in ['a.txt', 'b.txt']:
        (root/name).write_text('Target passage in ' + name)
        threads.append(ws.create_thread(name, 0, 6, 'Review ' + name, 'Reviewer', ws.read(name)['version']))
    page.goto(url); open_file(page, 'a.txt'); page.locator('#thread-scope').check()
    first = page.locator(f'.thread[data-thread="{threads[0]["id"]}"]')
    first.locator('.thread-heading [data-action=jump]').click()
    held = []
    def hold(route):
        if 'path=b.txt' in route.request.url:
            held.append(route); page.evaluate('window.blockedClickRead = true')
        else:
            route.continue_()
    page.route('**/api/file?*', hold)
    page.keyboard.press('ArrowRight')
    page.wait_for_function('()=>window.blockedClickRead === true')
    first.locator('.comment-markdown p').click()
    expect(first).to_be_focused()
    with page.expect_response(lambda response: '/api/file?' in response.url and 'path=b.txt' in response.url) as response:
        held[0].continue_()
    response.value.finished(); settle(page)
    expect(page.locator('#document-name')).to_have_text('a.txt')
    expect(first).to_have_class('thread active')
    expect(first).to_be_focused()
    expect(page.locator('#passage-spotlight')).to_be_visible()
