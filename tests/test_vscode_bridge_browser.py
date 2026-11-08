"""Quiet per-file locks retain drafts/history and providers only touch saved Edit buffers."""
import json
import os
import pytest
from test_requested_features import workspace_page, open_file

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


def pair(ws,dirty):
    if not ws.bridge.enabled:ws.bridge.pair({'root':str(ws.root)})
    ws.bridge.snapshot({'sequence':ws.bridge.sequence+1,'documents':[{'path':p,'dirty':True,'version':1} for p in dirty]})


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('theme,width',[('light',1440),('dark',760)])
def test_quiet_lock_preserves_draft_undo_other_file_and_disconnect(workspace_page,theme,width):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    original='value = "😀"\n'
    (root/'a.py').write_text(original);(root/'b.py').write_text('other = 1\n')
    page.goto(url);open_file(page,'a.py')
    page.evaluate('(theme)=>{document.documentElement.dataset.theme=theme}',theme)
    page.set_viewport_size({'width':width,'height':850})
    content=page.locator('.cm-content');content.click();page.keyboard.press('Control+End');page.keyboard.insert_text('# local draft\n')
    expect(page.locator('#dirty')).to_contain_text('Unsaved')
    before=content.inner_text();pair(ws,['a.py'])
    lock=page.locator('#vscode-lock');expect(lock).to_be_visible()
    expect(lock).to_have_attribute('aria-label','Read only — unsaved changes in VS Code')
    expect(page.locator('#save')).to_be_disabled()
    content.click();page.keyboard.insert_text('blocked');page.keyboard.press('Control+z');page.keyboard.press('Control+v')
    expect(content).to_have_js_property('innerText',before)
    assert (root/'a.py').read_text()==original
    lock.focus();expect(lock).to_be_focused()
    if os.environ.get('LG_BRIDGE_SCREENSHOTS'):page.screenshot(path=os.path.join(os.environ['LG_BRIDGE_SCREENSHOTS'],f'bridge-{theme}-{width}.png'))
    open_file(page,'b.py');expect(lock).to_be_hidden()
    expect(page.locator('.tab[data-path="a.py"] .vscode-lock')).to_be_visible()
    content.click();page.keyboard.press('Control+End');page.keyboard.insert_text('# other draft\n')
    expect(content).to_contain_text('# other draft')
    page.locator('.tab[data-path="a.py"] .tab-name').click();expect(content).to_have_js_property('innerText',before)
    pair(ws,[]);expect(lock).to_be_hidden()
    content.click();page.keyboard.press('Control+z');expect(content).not_to_contain_text('# local draft')
    page.keyboard.press('Control+Shift+z');expect(content).to_contain_text('# local draft')
    # Unknown state keeps previously dirty documents locked and all paired writes blocked.
    pair(ws,['a.py']);expect(lock).to_be_visible();ws.bridge.seen-=20
    expect(page.locator('#save')).to_be_disabled()
    page.locator('#bridge-disconnect').click()
    dialog=page.get_by_role('dialog',name='Disconnect VS Code?');expect(dialog).to_be_visible()
    dialog.get_by_role('button',name='Disconnect',exact=True).click()
    expect(lock).to_be_hidden();expect(page.locator('#save')).to_be_enabled()
    expect(content).to_have_js_property('innerText',before)
    assert (root/'a.py').read_text()==original


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_initial_dirty_snapshot_review_lock_and_draft_conflict(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    original='value = 1\n';(root/'a.py').write_text(original)
    pair(ws,['a.py']);page.goto(url);open_file(page,'a.py')
    expect(page.locator('#vscode-lock')).to_be_visible()
    content=page.locator('.cm-content');content.click();page.keyboard.insert_text('blocked')
    expect(content).to_have_text(original)
    page.locator('#work-mode').click();expect(page.locator('#approve-review')).to_be_disabled()
    content.click();page.keyboard.insert_text('blocked');expect(content).to_have_text(original)
    pair(ws,[]);expect(page.locator('#vscode-lock')).to_be_hidden()
    page.locator('#work-mode').click()
    content.click();page.keyboard.press('Control+End');page.keyboard.insert_text('# retained\n')
    pair(ws,['a.py']);expect(page.locator('#vscode-lock')).to_be_visible()
    (root/'a.py').write_text('value = 2\n');pair(ws,[])
    expect(page.locator('#vscode-lock')).to_be_hidden()
    expect(page.locator('#conflict')).to_be_visible(timeout=10000)
    expect(content).to_contain_text('# retained')
    assert (root/'a.py').read_text()=='value = 2\n'


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_saved_provider_completion_hover_sanitization_and_review_fallback(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    source='def hello():\n    return 1\n\nhello()\n';(root/'a.py').write_text(source)
    pair(ws,[]);calls=[]
    def provider(route):
        data=route.request.post_data_json;calls.append(data['provider'])
        result={'definition':{'definitions':[{'path':'a.py','line':1,'column':4,'version':ws.text('a.py')[1],'name':'hello'}]},
            'completion':{'items':[{'label':'hello_bridge','text':'hello_bridge','range':{'start':{'line':3,'character':0},'end':{'line':3,'character':5}}}]},
            'hover':{'markdown':'**Safe hover** <script>window.bridgeUnsafe=true</script>'}}[data['provider']]
        route.fulfill(json=result)
    page.route('**/api/bridge/provider',provider)
    page.goto(url);open_file(page,'a.py')
    content=page.locator('.cm-content');content.locator('.cm-line').first.hover(position={'x':45,'y':8})
    expect(page.locator('.bridge-hover')).to_contain_text('Safe hover')
    assert page.evaluate('window.bridgeUnsafe') is None
    assert page.locator('.bridge-hover script').count()==0
    content.click();page.keyboard.press('Control+End');page.keyboard.press('ArrowUp');page.keyboard.press('Home')
    page.keyboard.press('Control+Space')
    expect(page.locator('.cm-tooltip-autocomplete')).to_contain_text('hello_bridge')
    from test_spotlight_navigation_browser import settle
    settle(page)  # CodeMirror completion interaction guard
    page.locator('.cm-completionLabel').filter(has_text='hello_bridge').click()
    expect(content).to_contain_text('hello_bridge()');expect(page.locator('#dirty')).to_contain_text('Unsaved')
    assert (root/'a.py').read_text()==source
    count=len(calls);page.keyboard.press('Control+Space');page.keyboard.press('Escape')
    assert len(calls)==count
    page.keyboard.press('Control+z');expect(page.locator('.cm-line')).to_have_text(source.split('\n'))
    # Review remains on local navigation even though its initial text equals disk.
    page.locator('#work-mode').click();count=len(calls)
    content.click();page.keyboard.press('Control+End');page.keyboard.press('ArrowUp');page.keyboard.press('Home');page.keyboard.press('F12')
    expect(page.locator('#notice')).to_contain_text('Definition',timeout=10000)
    assert len(calls)==count


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_clean_native_save_refreshes_in_place_even_before_lock_notification(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    source=''.join(f'value_{i} = {i}\n' for i in range(150))
    (root/'a.py').write_text(source);pair(ws,[])
    page.goto(url);open_file(page,'a.py')
    content=page.locator('.cm-content');content.click();page.keyboard.press('Control+End');page.keyboard.press('ArrowUp')
    page.evaluate('window.bridgeEditor=document.querySelector(".cm-content")')
    scroll=page.locator('.cm-scroller').evaluate('el=>el.scrollTop')
    pair(ws,['a.py']);expect(page.locator('#vscode-lock')).to_be_visible()
    # The file poll can observe final bytes before the separate lock-status poll.
    (root/'a.py').write_text(source.replace('value_149 = 149','value_149 = 150'))
    expect(content).to_contain_text('value_149 = 150',timeout=10000)
    assert page.evaluate('window.bridgeEditor===document.querySelector(".cm-content")')
    assert abs(page.locator('.cm-scroller').evaluate('el=>el.scrollTop')-scroll)<40
    expect(page.locator('#dirty')).to_have_text('')
    pair(ws,[]);expect(page.locator('#vscode-lock')).to_be_hidden()
    content.click();page.keyboard.insert_text('# draft')
    expect(page.locator('#dirty')).to_contain_text('Unsaved')
