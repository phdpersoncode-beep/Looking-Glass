"""Focused composer outlines must not paint over neighboring content."""
import os
import json
import pytest
from playwright.sync_api import expect
from test_requested_features import workspace_page,open_file
from test_html_annotations_browser import select

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


def assert_focus_clearance(page):
    geometry=page.locator('#comment-body').evaluate('''el=>{
      const r=el.getBoundingClientRect(),s=getComputedStyle(el);
      const extent=parseFloat(s.outlineWidth)+Math.max(0,parseFloat(s.outlineOffset));
      const form=el.closest('form'),row=el.closest('.composer-input');
      const before=[...form.children].slice(0,[...form.children].indexOf(row)).filter(n=>n.getClientRects().length).at(-1).getBoundingClientRect();
      const next=[...form.children].slice([...form.children].indexOf(row)+1).filter(n=>n.getClientRects().length)[0].getBoundingClientRect();
      const dialog=form.closest('dialog'),d=dialog.getBoundingClientRect();
      return {outline:extent,above:r.top-before.bottom,below:next.top-r.bottom,left:r.left-d.left,right:d.right-r.right};
    }''')
    assert geometry['outline']>0,geometry
    for side in ['above','below','left','right']:
        assert geometry[side]>=geometry['outline']+1,geometry


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('theme,width,height',[('light',1440,960),('dark',1440,960),('light',420,500),('dark',420,500)])
@pytest.mark.parametrize('kind',['html_source','html_runtime','markdown','text'])
def test_comment_focus_ring_has_room_for_notes_quotes_attachments_and_errors(workspace_page,theme,width,height,kind):
    root,page,url,ws=workspace_page
    quote='Each beam entry carries its own copy of the environment. '+('A longer selected passage wraps across several lines. '*5)
    if kind.startswith('html'):
        source='<p id="passage">'+quote+'</p>' if kind=='html_source' else '<p id="passage"></p><script>document.querySelector("#passage").textContent='+json.dumps(quote)+'</script>'
        name='report.html';(root/name).write_text(source)
    else:
        name='notes.md' if kind=='markdown' else 'notes.txt';(root/name).write_text(quote)
    page.set_viewport_size({'width':width,'height':height});page.goto(url);open_file(page,name)
    page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
    if kind.startswith('html'):
        select(page,'#passage');page.locator('#selection-comment').click()
        expect(page.locator('#anchor-note')).to_contain_text('Anchored to HTML source' if kind=='html_source' else 'Rendered-only passage')
    else:
        if kind=='markdown':page.locator('#mode').select_option('source')
        page.locator('.cm-content').click();page.keyboard.press('Control+Home');page.keyboard.press('Control+a');page.locator('#annotate').click()
        expect(page.locator('#anchor-note')).to_be_hidden()
    field=page.locator('#comment-body');field.fill('What would this mean for us?');expect(field).to_be_focused()
    assert_focus_clearance(page)
    page.locator('#comment-form .attach-files').set_input_files({'name':'context.txt','mimeType':'text/plain','buffer':b'Context'})
    expect(page.locator('#comment-form .pending-file')).to_have_count(1);field.focus();assert_focus_clearance(page)
    # A real failed submission exercises the error row and retains focusable text.
    page.route('**/api/threads',lambda route:route.fulfill(status=409,json={'error':'The selected passage changed. Select it again before commenting.'}))
    page.locator('#comment-submit').click();expect(page.locator('#comment-error')).to_contain_text('selected passage changed')
    field.focus();expect(field).to_have_value('What would this mean for us?');assert_focus_clearance(page)
    page.unroute('**/api/threads')
    page.locator('#comment-submit').click();expect(page.locator('#comment-dialog')).to_be_hidden()
    assert ws.threads(name)[0]['messages'][0]['body']=='What would this mean for us?'
