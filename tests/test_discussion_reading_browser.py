"""Text-only selections, shared Markdown, and temporary discussion cards."""
import os
import pytest
from test_requested_features import workspace_page,open_file

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


def endpoint(locator,offset):
    return locator.evaluate('''(host,offset)=>{
      const walker=document.createTreeWalker(host,NodeFilter.SHOW_TEXT);let node;
      while((node=walker.nextNode())){if(offset<node.length){const range=document.createRange();range.setStart(node,offset);range.setEnd(node,offset+1);const r=range.getClientRects()[0];return {x:r.left+.5,y:(r.top+r.bottom)/2}}offset-=node.length}
      throw new Error('Text endpoint missing');
    }''',offset)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('mode',['live','preview'])
@pytest.mark.parametrize('reverse',[False,True])
def test_multiline_selection_only_paints_text(workspace_page,mode,reverse):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    first='First short line.';last='Final short line.'
    middle=('Wrapped prose with café and 🪞 and mixed words. '*28).strip()
    source=f'{first}\r\n\r\n{middle}\r\n\r\n{last}\r\n'
    (root/'note.md').write_bytes(source.encode());page.goto(url);open_file(page,'note.md')
    page.locator('#mode').select_option(mode)
    host='.cm-line' if mode=='live' else '#surface .markdown-preview>p'
    lines=page.locator(host);start=endpoint(lines.filter(has_text=first).first,3);end=endpoint(lines.filter(has_text=last).first,len(last)-3)
    if reverse:start,end=end,start
    page.mouse.move(**start);page.mouse.down();page.mouse.move(**end,steps=30);page.mouse.up()
    expect(page.locator('#selection-comment')).to_be_visible()
    if mode=='live':
        marks=page.locator('.cm-text-selection');expect(marks.first).to_be_visible()
        boxes=marks.evaluate_all('els=>els.map(el=>{const r=el.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width,top:r.top}})')
        assert len(boxes)>5
        # Short first/last lines must not extend to either side margin.
        assert boxes[0]['width']<180 and boxes[-1]['width']<180
        assert all(box['width']<800 for box in boxes)
        assert page.locator('.cm-selectionBackground').first.evaluate('el=>getComputedStyle(el).backgroundColor')=='rgba(0, 0, 0, 0)'
    else:
        page.wait_for_function('()=>CSS.highlights.has("looking-glass-text-selection")')
        ranges=page.evaluate('''()=>[...CSS.highlights.get('looking-glass-text-selection')].map(r=>({text:r.toString(),width:r.getClientRects()[0].width,node:r.startContainer.nodeType}))''')
        assert len(ranges)==3 and all(r['node']==3 for r in ranges)
        assert ranges[0]['width']<180 and ranges[-1]['width']<180
        assert lines.first.evaluate('el=>getComputedStyle(el,"::selection").backgroundColor')=='rgba(0, 0, 0, 0)'
    page.locator('#selection-comment').click();quote=page.locator('#selected-quote').text_content()
    assert middle in quote and 'First' not in quote and 'Final' in quote
    page.locator('#comment-body').fill('**Reviewed** multiline text');page.locator('#comment-submit').click()
    expect(page.locator('.comment-markdown strong')).to_have_text('Reviewed')
    thread=ws.threads()[0];assert thread['quote']==source[thread['start']:thread['end']]
    assert (root/'note.md').read_bytes()==source.encode()


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_discussion_markdown_shared_styles_and_safe_refresh(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    (root/'note.md').write_text('Reviewed passage.\n')
    body='''## Findings

**Bold** and *italic* with `code` and [link](https://example.invalid).

- first item
- second item

> Quoted observation.

| Label | Value |
| :--- | ---: |
| **width** | `12` |
| very long value that needs some space | another value |

```python
if True:
    print("café")
```

```mermaid
graph TD
  A[Input] --> B[Result]
```

<script>window.commentInjected=true</script><img src="/missing.png" onerror="window.commentInjected=true">
<style>.thread { display:none }</style>
<button data-action="delete-thread">Bad action</button><span class="thread" data-thread="99" id="author">Safe text</span>
'''
    thread=ws.create_thread('note.md',0,17,body,'Tester',ws.read('note.md')['version'])
    page.goto(url);open_file(page,'note.md');content=page.locator('.comment-markdown')
    expect(content.locator('h2')).to_have_text('Findings');expect(content.locator('ul li')).to_have_text(['first item','second item'])
    expect(content.locator('em')).to_have_text('italic');expect(content.locator('blockquote')).to_have_text('Quoted observation.')
    expect(content.locator('table strong')).to_have_text('width');expect(content.locator('table code')).to_have_text('12')
    expect(content.locator('pre .tok-keyword').first).to_be_visible();expect(content.locator('.mermaid-diagram svg')).to_be_visible()
    assert content.locator('script,button,[data-action],[data-thread],#author,.thread').count()==0
    # Mermaid generates an SVG-local style element after sanitization.
    assert all(content.locator('style').evaluate_all('els=>els.map(el=>!!el.closest("svg"))'))
    assert not page.evaluate('!!window.commentInjected')
    assert content.locator('a').get_attribute('target')=='_blank'
    assert content.evaluate('el=>parseFloat(getComputedStyle(el).fontSize)')<page.locator('.cm-scroller').evaluate('el=>parseFloat(getComputedStyle(el).fontSize)')
    assert content.locator('table').evaluate('el=>parseFloat(getComputedStyle(el).fontSize)')<content.evaluate('el=>parseFloat(getComputedStyle(el).fontSize)')
    assert content.locator('table td').first.evaluate('el=>parseFloat(getComputedStyle(el).paddingTop)')==3
    for theme in ['dark','light']:
        if page.locator('html').get_attribute('data-theme')!=theme:page.locator('#theme').click()
        page.locator('.passage-highlight').first.click();expect(page.locator('.floating-discussion')).to_be_visible()
        page.locator('.floating-discussion .reply-form textarea').fill('**Reply** with `code`')
        page.locator('.floating-discussion .reply-form button[type=submit]').click()
        expect(page.locator('.comment-markdown strong').filter(has_text='Reply')).to_have_count(1 if theme=='dark' else 2)
    page.reload();expect(page.locator('.comment-markdown h2')).to_have_text('Findings')
    assert ws.get_thread(thread['id'])['messages'][0]['body']==body.strip()


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('mode',['live','preview','source'])
def test_float_thread_keeps_reading_and_list_positions(workspace_page,mode):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    text='\n\n'.join(f'Passage {i:02}: A unique reviewed sentence.' for i in range(40))+'\n'
    (root/'note.md').write_text(text);version=ws.read('note.md')['version'];threads=[]
    for i in range(30):
        quote=f'Passage {i:02}';start=text.index(quote)
        threads.append(ws.create_thread('note.md',start,start+len(quote),'Long discussion.\n\n'+'Detail. '*120,'Reviewer',version))
    page.goto(url);open_file(page,'note.md');page.locator('#mode').select_option(mode)
    page.locator('#show-resolved').check()
    pane=page.locator('#surface' if mode=='preview' else '.cm-scroller')
    pane.evaluate('el=>el.scrollTop=400')
    page.wait_for_function('selector=>document.querySelector(selector).scrollTop>300',arg='#surface' if mode=='preview' else '.cm-scroller')
    target=page.locator('#surface .passage-highlight').filter(has_text='Passage 12').first
    target.scroll_into_view_if_needed();before=pane.evaluate('el=>el.scrollTop')
    sidebar=page.locator('.discussion-content');sidebar.evaluate('el=>el.scrollTop=180');side_before=sidebar.evaluate('el=>el.scrollTop')
    target.click();overlay=page.locator('.floating-discussion');expect(overlay).to_be_visible()
    expect(overlay.locator('.thread')).to_have_attribute('data-thread',str(threads[12]['id']))
    assert abs(pane.evaluate('el=>el.scrollTop')-before)<2
    assert abs(sidebar.evaluate('el=>el.scrollTop')-side_before)<2
    assert page.locator('.thread-placeholder').count()==1
    assert overlay.bounding_box()['y']>=page.locator('.discussion-sidebar>.panel-heading').bounding_box()['y']
    assert overlay.bounding_box()['y']+overlay.bounding_box()['height']<960
    field=overlay.locator('textarea');field.fill('Unsent **draft**');field.evaluate('el=>el.setSelectionRange(3,8)')
    ws.reply(threads[12]['id'],'External *update*.','Agent')
    # A real action refreshes the thread while the unsent reply keeps focus.
    overlay.locator('[data-action=resolve]').evaluate('el=>el.click()')
    expect(overlay.get_by_text('External update.')).to_be_visible(timeout=8000)
    expect(overlay.locator('textarea')).to_have_value('Unsent **draft**');expect(overlay.locator('textarea')).to_be_focused()
    assert overlay.locator('textarea').evaluate('el=>[el.selectionStart,el.selectionEnd]')==[3,8]
    overlay.locator('[data-action=resolve]').evaluate('el=>el.click()')
    expect(overlay.locator('.thread')).to_have_attribute('data-resolved','false')
    assert abs(pane.evaluate('el=>el.scrollTop')-before)<2
    overlay.locator('[data-action=collapse-thread]').click();expect(overlay).not_to_be_visible()
    expect(page.locator(f'#threads>.thread[data-thread="{threads[12]["id"]}"]')).to_have_class('thread active collapsed')
    assert page.locator('.thread-placeholder').count()==0
    ids=page.locator('#threads>.thread').evaluate_all('els=>els.map(el=>Number(el.dataset.thread))')
    assert ids==[t['id'] for t in threads]
    page.locator(f'#threads>.thread[data-thread="{threads[12]["id"]}"] [data-action=expand-thread]').click()
    expect(overlay).not_to_be_visible()
    assert abs(pane.evaluate('el=>el.scrollTop')-before)<2
    # Escape can arrive before the pointer-release fallback's animation frame.
    # A handled click must never leave a second activation waiting to reopen it.
    target.evaluate('''async el=>{
      const r=el.getBoundingClientRect(),point={bubbles:true,button:0,clientX:r.left+2,clientY:r.top+2};
      el.dispatchEvent(new PointerEvent('pointerdown',point));
      el.dispatchEvent(new PointerEvent('pointerup',point));
      el.dispatchEvent(new MouseEvent('click',{...point,detail:1}));
      await Promise.resolve();
      document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    }''')
    expect(overlay).not_to_be_visible()
    assert page.locator('.thread-placeholder').count()==0
    target.click();expect(overlay).to_be_visible();expect(overlay.locator('textarea')).to_have_value('Unsent **draft**')
    page.keyboard.press('Escape');expect(overlay).not_to_be_visible();assert abs(pane.evaluate('el=>el.scrollTop')-before)<2
    target.click();expect(overlay).to_be_visible();page.locator('#document-name').click();expect(overlay).not_to_be_visible()
    assert abs(pane.evaluate('el=>el.scrollTop')-before)<2
    target.click();expect(overlay).to_be_visible()
    # Explicit navigation is allowed to move the document.
    overlay.locator('[data-action=jump]').first.click()
    expect(overlay).not_to_be_visible()
    expect(page.locator('.thread.active')).to_have_attribute('data-thread',str(threads[12]['id']))
    page.locator('#collapse-threads').click();expect(overlay).not_to_be_visible()
    page.locator('#discussions-toggle').click();target.click()
    expect(page.locator('#discussions-toggle')).to_have_attribute('aria-label','Hide discussions')
    expect(overlay).to_be_visible()
    assert (root/'note.md').read_text()==text


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_html_thread_float_preserves_report_scroll_and_defocus(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    source=''.join(f'<p id="p{i}">Report passage {i:02}.</p><div style="height:90px"></div>' for i in range(25))+'<button>Report control</button>'
    (root/'report.html').write_text(source);version=ws.read('report.html')['version'];threads=[]
    for i in range(25):
        quote=f'Report passage {i:02}.';start=source.index(quote)
        threads.append(ws.create_thread('report.html',start,start+len(quote),'**HTML** review.\n\n'+'Details. '*70,'Reviewer',version))
    page.goto(url);open_file(page,'report.html');frame=page.frame_locator('#html-preview')
    passage=frame.locator('#p18');passage.scroll_into_view_if_needed()
    before=passage.evaluate('()=>window.scrollY')
    point=endpoint(passage,3);bounds=page.locator('#html-preview').bounding_box()
    page.mouse.click(bounds['x']+point['x'],bounds['y']+point['y'])
    overlay=page.locator('.floating-discussion');expect(overlay).to_be_visible()
    expect(overlay.locator('.thread')).to_have_attribute('data-thread',str(threads[18]['id']))
    expect(overlay.locator('.comment-markdown strong')).to_have_text('HTML')
    assert abs(passage.evaluate('()=>window.scrollY')-before)<2
    overlay.locator('[data-action=collapse-thread]').click();expect(overlay).not_to_be_visible()
    assert abs(passage.evaluate('()=>window.scrollY')-before)<2
    page.mouse.click(bounds['x']+point['x'],bounds['y']+point['y']);expect(overlay).to_be_visible()
    frame.locator('#p18+div').click();expect(overlay).not_to_be_visible()
    assert abs(passage.evaluate('()=>window.scrollY')-before)<2
    assert (root/'report.html').read_text()==source
