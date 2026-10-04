"""Browser regressions for the viewer and review improvements."""
import os
import threading
import pytest
from werkzeug.serving import make_server
from looking_glass.app import create_app
pytestmark=pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER for browser checks')

@pytest.fixture
def workspace_page(tmp_path):
    from playwright.sync_api import sync_playwright
    app=create_app(tmp_path)
    server=make_server('127.0.0.1',0,app,threaded=True)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        with sync_playwright() as pw:
            executable=os.environ['LOOKING_GLASS_BROWSER']
            browser=pw.chromium.launch(executable_path=None if executable=='installed' else executable,headless=True,args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':1440,'height':960})
            page=context.new_page();errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            yield tmp_path,page,f'http://127.0.0.1:{server.server_port}',app.extensions['workspace']
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();worker.join(timeout=5);server.server_close()

def open_file(page,name):
    from playwright.sync_api import expect
    page.locator(f'.file-entry[data-path="{name}"]').click()
    expect(page.locator('#document-name')).to_have_text(name)

def test_markdown_tables(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    original='# Report\n\n| Name | Value |\n| :--- | ---: |\n| **width** | `12` |\n\nEnding.\n'
    (root/'table.md').write_text(original)
    page.goto(url);open_file(page,'table.md')
    expect(page.locator('.md-table th')).to_have_text(['Name','Value'])
    expect(page.locator('.md-table strong')).to_have_text('width')
    expect(page.locator('.md-table code')).to_have_text('12')
    assert page.locator('.md-table td').last.evaluate('el=>getComputedStyle(el).textAlign').endswith('right')
    page.locator('.md-table td').first.click()
    expect(page.locator('.md-table')).to_have_count(0)
    expect(page.locator('.cm-content')).to_contain_text('| Name | Value |')
    page.keyboard.press('Control+End');expect(page.locator('.md-table table')).to_be_visible()
    page.locator('#mode').select_option('preview');expect(page.locator('.markdown-preview table')).to_be_visible()
    page.locator('#mode').select_option('source');expect(page.locator('.md-table')).to_have_count(0)
    assert (root/'table.md').read_text()==original

def test_json_folding(workspace_page):
    import json
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    data={'first':{'nested':[1,2]},'second':{'value':3}}
    original=json.dumps(data,indent=2)
    (root/'data.json').write_text(original)
    (root/'rows.jsonl').write_text(json.dumps(data)+'\n{"other":[4,5]}\ninvalid\n')
    page.goto(url)
    for name in ('data.json','rows.jsonl'):
        open_file(page,name)
        page.get_by_role('button',name='Collapse all',exact=True).click()
        expect(page.locator('.cm-foldPlaceholder')).to_have_count(1)
        page.locator('.cm-foldPlaceholder').first.click()
        expect(page.locator('.cm-foldPlaceholder')).to_have_count(2)
        expect(page.locator('.cm-content')).not_to_contain_text('nested')
        page.locator('.cm-foldPlaceholder').first.click()
        expect(page.locator('.cm-content')).to_contain_text('nested')
        expect(page.locator('.cm-content')).not_to_contain_text('value')
        page.get_by_role('button',name='Expand all',exact=True).click()
        expect(page.locator('.cm-foldPlaceholder')).to_have_count(0)
        expect(page.locator('.cm-content')).to_contain_text('value')
    page.locator('.jsonl-row[data-row="1"]').click();expect(page.locator('.cm-content')).to_contain_text('other')
    page.locator('.jsonl-row[data-row="2"]').click();expect(page.locator('.jsonl-detail .viewer-heading')).to_contain_text('MALFORMED')
    assert (root/'data.json').read_text()==original
