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


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'source', 'preview'])
def test_unanchored_spotlight_preserves_reading_and_opens_context_only_on_request(workspace_page, mode):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    original = '# Notes\n\nFirst stable passage.\n\nDetached passage.\n\n' + 'Reading context.\n\n'*70 + 'Last stable passage.\n'
    (root/'note.md').write_text(original)
    version = ws.read('note.md')['version']
    threads = []
    for quote in ['First stable', 'Detached passage', 'Last stable']:
        start = original.index(quote)
        threads.append(ws.create_thread('note.md', start, start+len(quote), 'Review '+quote, 'Reviewer', version))
    (root/'note.md').write_text(original.replace('Detached passage.', 'Replacement sentence.'))
    ws.read('note.md')
    assert ws.get_thread(threads[1]['id'])['anchor_status'] == 'needs_reattachment'
    page.goto(url); open_file(page, 'note.md'); page.locator('#mode').select_option(mode)
    first = page.locator(f'.thread[data-thread="{threads[0]["id"]}"]')
    detached = page.locator(f'.thread[data-thread="{threads[1]["id"]}"]')
    first.locator('.thread-heading [data-action=jump]').click(); settle(page)
    first.locator('textarea').fill('Keep my reply draft'); first.focus()
    page.evaluate('''()=>{window.readingNode=document.querySelector('#surface').firstElementChild;
      window.readingScroller=document.querySelector('.cm-scroller')||document.querySelector('#surface');
      window.readingTop=window.readingScroller.scrollTop;}''')
    context_requests = []
    page.on('request', lambda request: context_requests.append(request.url) if '/original' in request.url else None)
    page.keyboard.press('ArrowRight')
    expect(detached).to_have_class('thread active'); expect(detached).to_be_focused(); settle(page)
    assert page.evaluate('window.readingNode===document.querySelector("#surface").firstElementChild')
    assert abs(page.evaluate('window.readingScroller.scrollTop-window.readingTop')) < 2
    expect(page.locator('#document-name')).to_have_text('note.md')
    expect(page.locator('.original-banner')).to_have_count(0)
    for selector in ['.thread-heading [data-action=jump]', 'blockquote', '.comment-markdown p']:
        detached.locator(selector).click()
        expect(detached).to_be_focused(); expect(page.locator('#passage-spotlight')).to_be_visible()
        assert page.evaluate('window.readingNode===document.querySelector("#surface").firstElementChild')
    # Sample every frame of repeated navigation through the unavailable passage.
    page.evaluate('''()=>{window.unanchoredFrames=[];window.unanchoredDone=false;let remaining=30;
      function sample(){window.unanchoredFrames.push({surface:window.readingNode===document.querySelector('#surface').firstElementChild,
        spotlight:!document.querySelector('#passage-spotlight').hidden,
        active:document.querySelectorAll('.thread.active:not([hidden])').length,
        original:document.querySelectorAll('.original-banner').length});
        if(--remaining)requestAnimationFrame(sample);else window.unanchoredDone=true;
      }requestAnimationFrame(sample);}''')
    for key in ['ArrowRight', 'ArrowLeft', 'ArrowLeft', 'ArrowRight', 'ArrowRight', 'ArrowLeft']:
        page.keyboard.press(key)
    expect(detached).to_have_class('thread active')
    page.wait_for_function('()=>window.unanchoredDone')
    frames = page.evaluate('window.unanchoredFrames')
    assert all(frame['surface'] and frame['spotlight'] and frame['active']==1 and not frame['original'] for frame in frames), frames
    assert context_requests == []
    detached.locator('textarea').fill('Detached draft')
    detached.locator('[data-action=original]').click()
    expect(page.locator('.original-banner')).to_be_visible()
    expect(page.locator('.original-reading,.original-editor')).to_contain_text('Detached passage')
    assert context_requests
    page.locator('#context-return').click()
    expect(page.locator('#document-name')).to_have_text('note.md')
    assert page.evaluate('window.readingNode===document.querySelector("#surface").firstElementChild')
    expect(detached.locator('textarea')).to_have_value('Detached draft')
    detached.focus(); page.keyboard.press('ArrowLeft')
    expect(first.locator('textarea')).to_have_value('Keep my reply draft')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_reading_scrollbars_are_thin_and_themed_without_disabling_scrolling(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page

    def assert_thin_scrollbar(pane):
        if page.context.browser.browser_type.name == 'firefox' and not os.environ.get('LOOKING_GLASS_HEADED'):
            # Playwright Firefox registers hidden-scrollbars.css as a browser
            # !important rule in headless mode. Check the matching application
            # declaration; theme colours and native scrolling are still observable.
            assert pane.evaluate('''el=>[...document.styleSheets].some(sheet=>
              [...sheet.cssRules].some(rule=>rule.selectorText && el.matches(rule.selectorText)
                && rule.style.scrollbarWidth==='thin'))''')
        else:
            assert pane.evaluate('el=>getComputedStyle(el).scrollbarWidth') == 'thin'

    (root/'long.py').write_text(''.join(f'line_{i} = "'+ 'long_value_'*120 + '"\n' for i in range(160)))
    (root/'long.md').write_text('# Reading\n\n' + 'A paragraph to scroll through.\n\n'*150)
    page.goto(url); open_file(page, 'long.py')
    colors = []
    for theme in ['light', 'dark']:
        if page.locator('html').get_attribute('data-theme') != theme:
            page.locator('#theme').click()
        page.set_viewport_size({'width':900,'height':720})
        scroller = page.locator('.cm-scroller')
        assert_thin_scrollbar(scroller)
        colors.append(scroller.evaluate('el=>getComputedStyle(el).scrollbarColor'))
        assert scroller.evaluate('''el=>{
          const style=getComputedStyle(el);
          return style.scrollbarColor.includes('rgba(0, 0, 0, 0)') && !style.scrollbarColor.includes('auto');
        }''')
        assert scroller.evaluate('el=>el.scrollHeight>el.clientHeight && el.scrollWidth>el.clientWidth')
        scroller.hover(); page.mouse.wheel(240, 320)
        page.wait_for_function('()=>document.querySelector(".cm-scroller").scrollTop>0 && document.querySelector(".cm-scroller").scrollLeft>0')
        page.locator('.cm-content').click(); page.keyboard.press('Control+Home')
        page.wait_for_function('()=>document.querySelector(".cm-scroller").scrollTop<50')
        expect(page.locator('.cm-line').first).to_be_in_viewport()
    assert colors[0] != colors[1]
    open_file(page, 'long.md'); page.locator('#mode').select_option('preview')
    pane = page.locator('#surface')
    assert_thin_scrollbar(pane)
    pane.hover(); page.mouse.wheel(0, 500)
    page.wait_for_function('()=>document.querySelector("#surface").scrollTop>0')
    page.locator('#go-to-top').click()
    page.wait_for_function('()=>document.querySelector("#surface").scrollTop===0')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('control', ['search', 'reply'])
def test_cancelling_arrow_navigation_while_discussions_load_keeps_document_and_cards_together(workspace_page, control):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    threads = []
    for name in ['a.txt', 'b.txt']:
        (root/name).write_text('Target passage in '+name)
        threads.append(ws.create_thread(name, 0, 6, 'Review '+name, 'Reviewer', ws.read(name)['version']))
    page.goto(url); open_file(page, 'a.txt'); page.locator('#thread-scope').check()
    first = page.locator(f'.thread[data-thread="{threads[0]["id"]}"]')
    first.locator('.thread-heading [data-action=jump]').click()
    held = []
    def hold(route):
        if 'path=b.txt' in route.request.url:
            held.append(route); page.evaluate('window.blockedDiscussionRead=true')
        else:
            route.continue_()
    page.route('**/api/discussions?*', hold)
    page.keyboard.press('ArrowRight')
    page.wait_for_function('()=>window.blockedDiscussionRead')
    expect(page.locator('#document-name')).to_have_text('a.txt')
    expect(first).to_have_class('thread active')
    field = page.locator('#thread-search') if control=='search' else first.locator('textarea')
    field.fill('Keep focus here')
    with page.expect_response(lambda response: '/api/discussions?' in response.url and 'path=b.txt' in response.url) as response:
        held[0].continue_()
    response.value.finished(); settle(page)
    expect(page.locator('#document-name')).to_have_text('a.txt')
    expect(field).to_be_focused(); expect(field).to_have_value('Keep focus here')
    assert not page.locator('.thread.active:visible[data-path="b.txt"]').count()
