"""Passage inspection holds its viewport; sidebar icons deliberately navigate."""
import os
import pytest
from test_requested_features import workspace_page,open_file
from test_discussion_reading_browser import endpoint

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


def settle(page):
    page.evaluate('''()=>new Promise(resolve=>{let n=8;function frame(){if(--n)requestAnimationFrame(frame);else resolve()}requestAnimationFrame(frame)})''')


def align_bottom(target,pane):
    target.evaluate('''(el,selector)=>{
      const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT),node=walker.nextNode();
      const range=document.createRange();range.setStart(node,2);range.setEnd(node,3);
      const r=range.getBoundingClientRect(),pane=document.querySelector(selector),b=pane.getBoundingClientRect();
      pane.scrollTop+=(r.top+r.bottom)/2-(b.bottom-8);
    }''',pane)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('mode',['live','source','preview'])
@pytest.mark.parametrize('hidden',[False,True])
def test_low_formatted_highlight_holds_clicked_text(workspace_page,mode,hidden):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    text='\n\n'.join(f'[Reference](https://example.invalid/'+('very-long-link/'*35)+f') **Passage {i:02}**: '+'Prose for reading a long document. '*10 for i in range(85))+'\n'
    (root/'note.md').write_text(text);version=ws.read('note.md')['version'];at=text.index('Passage 70')
    thread=ws.create_thread('note.md',at,at+10,'Discussion. '*80,'Reviewer',version)
    # Narrow viewports force substantial reflow when the sidebar is reopened.
    page.set_viewport_size({'width':1000,'height':680});page.goto(url);open_file(page,'note.md');page.locator('#mode').select_option(mode)
    page.locator('.thread [data-action=jump]').first.evaluate('el=>el.click()')
    target=page.locator('#surface .passage-highlight').filter(has_text='Passage 70').first
    expect(target).to_be_visible();settle(page)
    if hidden:page.locator('#discussions-toggle').click();settle(page)
    pane_selector='#surface' if mode=='preview' else '.cm-scroller';pane=page.locator(pane_selector)
    target.scroll_into_view_if_needed();align_bottom(target,pane_selector);settle(page)
    point=endpoint(target,2);before=pane.evaluate('el=>el.scrollTop')
    page.mouse.click(**point);expect(page.locator('#passage-spotlight')).to_be_visible();settle(page)
    expect(page.locator('.thread.active')).to_have_attribute('data-thread',str(thread['id']))
    assert abs(endpoint(target,2)['y']-point['y'])<2
    if not hidden:assert abs(pane.evaluate('el=>el.scrollTop')-before)<2
    # The protection releases promptly for ordinary user scrolling/navigation.
    wheel_before=pane.evaluate('el=>el.scrollTop')
    bounds=pane.bounding_box();page.mouse.move(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)
    page.mouse.wheel(0,-350)
    page.wait_for_function('([selector,before])=>document.querySelector(selector).scrollTop<before',arg=[pane_selector,wheel_before])
    page.keyboard.press('Escape');expect(page.locator('#passage-spotlight')).not_to_be_visible()
    assert (root/'note.md').read_text()==text


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('mode',['table','html'])
@pytest.mark.parametrize('hidden',[False,True])
def test_low_native_highlight_holds_position(workspace_page,mode,hidden):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    if mode=='table':
        text='Introductory prose.\n\n'+'Before the table.\n\n'*25+'| Label | Value |\n| --- | --- |\n'+''.join(f'| **Passage {i:02}** | '+('Wide cell content. '*12)+' |\n' for i in range(30))
        name='note.md';quote='Passage 20'
    else:
        text=''.join(f'<p id="p{i}"><a href="https://example.invalid">Reference</a> <strong>Passage {i:02}</strong>: '+('Prose for reading a long document. '*10)+'</p>' for i in range(40))
        name='report.html';quote='Passage 30'
    (root/name).write_text(text);at=text.index(quote);thread=ws.create_thread(name,at,at+10,'Review. '*80,'Reviewer',ws.read(name)['version'])
    page.set_viewport_size({'width':1000,'height':680});page.goto(url);open_file(page,name)
    page.locator('.thread [data-action=jump]').first.evaluate('el=>el.click()');settle(page)
    if hidden:page.locator('#discussions-toggle').click();settle(page)
    if mode=='table':
        target=page.locator('.md-table .passage-highlight').filter(has_text=quote).first
        target.scroll_into_view_if_needed();align_bottom(target,'.cm-scroller');settle(page)
        point=endpoint(target,2);before=point['y'];page.mouse.click(**point)
    else:
        frame=page.frame_locator('#html-preview');target=frame.locator('#p30 strong');target.scroll_into_view_if_needed()
        # Stop the sidebar jump animation before recording this click's baseline.
        target.evaluate('''el=>{const r=el.getBoundingClientRect();window.scrollBy({top:(r.top+r.bottom)/2-(window.innerHeight-8),behavior:'instant'})}''');settle(page)
        point=endpoint(target,2);before=point['y'];bounds=page.locator('#html-preview').bounding_box()
        page.mouse.click(bounds['x']+point['x'],bounds['y']+point['y'])
    expect(page.locator('#passage-spotlight')).to_be_visible();settle(page)
    assert abs(endpoint(target,2)['y']-before)<2
    expect(page.locator('.thread.active')).to_have_attribute('data-thread',str(thread['id']))
    page.keyboard.press('Escape');expect(page.locator('#passage-spotlight')).not_to_be_visible()
    assert (root/name).read_text()==text


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('mode',['live','source','preview','html'])
def test_sidebar_icon_navigates_and_spotlights(workspace_page,mode):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    quote='Target passage'
    if mode=='html':
        name='report.html';text='<p>Start.</p><div style="height:2400px"></div><p id="target">Target passage with surrounding context.</p><div style="height:1200px"></div>'
    else:
        name='note.md';text='Start.\n\n'+'Surrounding context.\n\n'*80+'Target passage with surrounding context.\n\n'+'Ending context.\n\n'*20
    (root/name).write_text(text);at=text.index(quote);t=ws.create_thread(name,at,at+len(quote),'Review target.','Reviewer',ws.read(name)['version'])
    page.goto(url);open_file(page,name)
    if mode!='html':page.locator('#mode').select_option(mode)
    page.locator('#collapse-threads').click();sidebar=page.locator('.discussion-content');saved=sidebar.evaluate('el=>el.scrollTop')
    page.locator('.thread-summary svg').click()
    heading=page.locator('#passage-spotlight');expect(heading).to_be_visible();settle(page)
    expect(page.locator('.thread.active')).to_have_attribute('data-thread',str(t['id']))
    expect(page.locator('#all-discussions kbd')).to_have_text('Esc')
    expect(page.locator('#all-discussions')).to_have_attribute('aria-keyshortcuts','Escape')
    if mode=='html':
        target=page.frame_locator('#html-preview').locator('#target');expect(target).to_be_in_viewport()
        assert target.evaluate('()=>window.scrollY')>1000
    else:
        target=page.locator('#surface .focused-highlight').filter(has_text=quote).first;expect(target).to_be_in_viewport()
        scroller=page.locator('#surface' if mode=='preview' else '.cm-scroller');assert scroller.evaluate('el=>el.scrollTop')>1000
        r=target.bounding_box();bounds=page.locator('#surface').bounding_box()
        assert bounds['y']+40<r['y']<bounds['y']+bounds['height']-40
    page.locator('.thread.active textarea').fill('Draft after navigation')
    page.keyboard.press('Escape');expect(heading).not_to_be_visible()
    assert abs(sidebar.evaluate('el=>el.scrollTop')-saved)<2
    expect(page.locator('.thread.active textarea')).to_have_value('Draft after navigation')
    assert (root/name).read_text()==text


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_sidebar_icon_cross_file_and_drag_still_work(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    (root/'a.md').write_text('First file.')
    text='Beginning.\n\n'+'Context.\n\n'*60+'Highlighted passage to select.\n\n'+'Tail.\n\n'*20
    (root/'b.md').write_text(text);at=text.index('Highlighted');t=ws.create_thread('b.md',at,at+19,'Review.','Reviewer',ws.read('b.md')['version'])
    page.goto(url);open_file(page,'a.md');page.locator('#thread-scope').check();page.locator('#collapse-threads').click()
    page.locator('.thread-summary').click();expect(page.locator('#document-name')).to_have_text('b.md');expect(page.locator('#passage-spotlight')).to_be_visible()
    page.keyboard.press('Escape');target=page.locator('#surface .passage-highlight').first
    start=endpoint(target,1);end=endpoint(target,16)
    page.mouse.move(**start);page.mouse.down();page.mouse.move(**end,steps=12);page.mouse.up();settle(page)
    expect(page.locator('#selection-comment')).to_be_visible();expect(page.locator('#passage-spotlight')).not_to_be_visible()
    page.keyboard.press('ArrowRight');page.keyboard.press('ArrowDown');page.keyboard.insert_text('Edited ')
    expect(page.locator('#dirty')).to_have_text(' · Unsaved')
    assert (root/'b.md').read_text()==text
