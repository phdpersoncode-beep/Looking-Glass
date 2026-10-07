"""Rendered HTML ↔ raw source annotation regressions in both browser engines."""
import os
import pytest
from test_requested_features import workspace_page, open_file

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


def select(page,selector,start=None,end=None):
    from playwright.sync_api import expect
    page.frame_locator('#html-preview').locator(selector).evaluate('''(el,offsets)=>{
      window.focus();el.scrollIntoView();const range=document.createRange();
      if(offsets[0]===null)range.selectNodeContents(el);
      else {range.setStart(el.firstChild,offsets[0]);range.setEnd(el.firstChild,offsets[1]);}
      const selection=getSelection();selection.removeAllRanges();selection.addRange(range);
    }''',[start,end])
    expect(page.locator('#selection-comment')).to_be_visible()


def comment(page,body,shortcut=False):
    from playwright.sync_api import expect
    if shortcut:page.keyboard.press('Control+Enter')
    else:page.locator('#selection-comment').click()
    expect(page.locator('#comment-dialog')).to_be_visible()
    page.locator('#comment-body').fill(body);page.locator('#comment-submit').click()
    expect(page.get_by_text(body,exact=True)).to_be_visible()


def highlights(page,name='looking-glass-passages'):
    return page.frame_locator('#html-preview').locator('body').evaluate('(_,name)=>[...CSS.highlights.get(name)||[]].map(r=>r.toString())',name)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_html_source_selection_navigation_and_persistence(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    source='<!doctype html>\r\n<html><body><p>🪞 München</p><p id="passage">Hello <strong>world</strong> &amp; friends.</p><table><tr><td>same<td id="second">same</table><p id="emoji">A &#x1F600; B &NotEqualTilde; C</p><button onclick="this.textContent=\'Works\'">Run</button></body></html>'
    (root/'report.html').write_bytes(source.encode())
    page.goto(url);open_file(page,'report.html')
    select(page,'#passage');page.locator('#selection-comment').click()
    expect(page.locator('#selected-quote')).to_have_text('Hello world & friends.')
    expect(page.locator('#anchor-note')).to_have_text('Anchored to HTML source')
    page.locator('#comment-body').fill('Across tags and entities');page.locator('#comment-submit').click()
    expect(page.get_by_text('Across tags and entities',exact=True)).to_be_visible()
    t=ws.threads()[0];quote='Hello <strong>world</strong> &amp; friends.'
    assert t['anchor_kind']=='source' and t['quote']==quote and t['start']==source.index(quote)
    expect(page.frame_locator('#html-preview').locator('body')).to_be_visible()
    assert ''.join(highlights(page))=='Hello world & friends.'
    page.locator('#html-toggle').click()
    expect(page.locator('.passage-highlight')).to_have_text(quote)
    page.locator('.thread .jump').click();expect(page.locator('#html-toggle span.active')).to_have_text('Source')
    page.locator('#html-toggle').click();select(page,'#second');comment(page,'Second repeated cell',shortcut=True)
    second=next(t for t in ws.threads() if t['messages'][0]['body']=='Second repeated cell')
    assert second['start']==source.index('same</table>')
    select(page,'#emoji',2,4);comment(page,'Astral entity')
    assert next(t for t in ws.threads() if t['messages'][0]['body']=='Astral entity')['quote']=='&#x1F600;'
    page.locator(f'.thread[data-thread="{second["id"]}"] .jump').click()
    expect(page.locator('#html-toggle span.active')).to_have_text('Rendered')
    assert highlights(page,'looking-glass-active')==['same']
    page.frame_locator('#html-preview').get_by_role('button',name='Run',exact=True).click()
    expect(page.frame_locator('#html-preview').get_by_role('button',name='Works',exact=True)).to_be_visible()
    assert page.frame_locator('#html-preview').locator('body').evaluate('()=>{try{return !!parent.document}catch{return false}}') is False
    page.reload();expect(page.get_by_text('Second repeated cell',exact=True)).to_be_visible()
    expect(page.frame_locator('#html-preview').locator('#second')).to_be_visible()
    assert (root/'report.html').read_bytes()==source.encode()
    # Reply/resolve/reopen use the same thread controls as Markdown and code.
    thread=page.locator(f'.thread[data-thread="{second["id"]}"]');thread.locator('.jump').click()
    thread.locator('.reply-form textarea').fill('Same source thread')
    thread.locator('.reply-form button[type=submit]').click();expect(page.get_by_text('Same source thread',exact=True)).to_be_visible()
    thread.get_by_role('button',name='Resolve thread',exact=True).click()
    page.locator('#show-resolved').check();thread.get_by_role('button',name='Reopen thread',exact=True).click()
    assert ws.get_thread(second['id'])['resolved'] is False


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_html_edits_reattachment_and_original_context(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    original='<p id="passage">A distinctive original passage.</p><p id="replacement">A replacement passage.</p>'
    path=root/'report.html';path.write_text(original)
    page.goto(url);open_file(page,'report.html');select(page,'#passage');comment(page,'Persistent review')
    t=ws.threads()[0]
    path.write_text('<h1>Inserted title</h1>'+original)
    expect(page.frame_locator('#html-preview').locator('h1')).to_have_text('Inserted title')
    assert ws.get_thread(t['id'])['start']==original.index('A distinctive')+len('<h1>Inserted title</h1>')
    path.write_text('<p id="replacement">A replacement passage.</p>')
    expect(page.locator('.anchor-warning')).to_be_visible()
    select(page,'#replacement');page.locator('[data-action=reattach]').click()
    expect(page.locator('.anchor-warning')).to_have_count(0)
    assert ws.get_thread(t['id'])['quote']=='A replacement passage.'
    page.locator('[data-action=original]').click()
    expect(page.locator('.original-editor')).to_contain_text('A distinctive original passage.')
    assert ws.origins.read(t['id'])['content']==original
    # An unsaved source edit is saved before a rendered selection is submitted.
    open_file(page,'report.html');page.locator('#html-toggle').click()
    page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.insert_text('<p id="draft">Unsaved draft passage.</p>')
    page.locator('#html-toggle').click();select(page,'#draft');comment(page,'Saved with annotation')
    assert 'Unsaved draft passage.' in path.read_text()
    assert next(t for t in ws.threads() if t['messages'][0]['body']=='Saved with annotation')['quote']=='Unsaved draft passage.'


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_html_dynamic_and_legacy_anchors_stay_rendered_only(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    source='<p id="static">Static passage.</p><p id="dynamic"></p><script>document.querySelector("#dynamic").textContent="Generated passage."</script>'
    (root/'report.html').write_text(source)
    legacy=ws.create_rendered_thread('report.html',dict(quote='Static passage.',prefix='',suffix=''),'Legacy discussion','Reviewer',ws.read('report.html')['version'])
    page.goto(url);open_file(page,'report.html');select(page,'#dynamic')
    page.locator('#selection-comment').click();expect(page.locator('#anchor-note')).to_contain_text('Rendered-only passage')
    page.locator('#comment-body').fill('Generated discussion');page.locator('#comment-submit').click()
    expect(page.get_by_text('Generated discussion',exact=True)).to_be_visible()
    assert all(t['anchor_kind']=='rendered' for t in ws.threads())
    expect(page.get_by_text('Legacy discussion',exact=True)).to_be_visible()
    # A source thread whose DOM was replaced retains its disk anchor; navigation
    # goes to source rather than highlighting an unrelated identical quote.
    select(page,'#static');comment(page,'Static source discussion')
    static=next(t for t in ws.threads() if t['anchor_kind']=='source')
    page.frame_locator('#html-preview').locator('#static').evaluate("el=>el.textContent='Changed dynamically.'")
    page.wait_for_timeout(250)
    assert ws.get_thread(static['id'])['anchor_status']=='attached'
    page.locator(f'.thread[data-thread="{static["id"]}"] .jump').click()
    expect(page.locator('#html-toggle span.active')).to_have_text('Source')
    expect(page.locator('.passage-highlight')).to_have_text('Static passage.')
    assert ws.get_thread(legacy['id'])['anchor_kind']=='rendered'
