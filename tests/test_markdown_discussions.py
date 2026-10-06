"""Rendered Markdown discussions use exact, persistent source passages."""
import os
import pytest
from test_requested_features import workspace_page, open_file
pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


def select_text(page, selector):
    page.locator(selector).evaluate('''el=>{
      const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);const nodes=[];let node;
      while(node=walker.nextNode())nodes.push(node);
      const range=document.createRange();range.setStart(nodes[0],0);range.setEnd(nodes.at(-1),nodes.at(-1).length);
      const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
    }''')


def test_live_table_annotations_and_explicit_source_edit(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    text='# Results\n\n| Label | Value |\n| --- | --- |\n| **width** | `12` |\n\nAfter.\n'
    (root/'table.md').write_text(text)
    page.goto(url);open_file(page,'table.md')
    select_text(page,'.md-table strong')
    expect(page.locator('#annotate')).to_be_enabled()
    expect(page.locator('.md-table table')).to_be_visible()
    page.locator('#annotate').click();expect(page.locator('#selected-quote')).to_have_text('width')
    page.locator('#comment-body').fill('Check width');page.locator('#comment-submit').click()
    expect(page.locator('.md-table .passage-highlight')).to_have_text('width')
    thread=ws.threads()[0];assert thread['quote']=='width' and text[thread['start']:thread['end']]=='width'
    page.locator('.md-table .passage-highlight').click();expect(page.locator('.thread.active')).to_be_visible()
    page.get_by_role('button',name='Edit table source',exact=True).click()
    expect(page.locator('.cm-content')).to_contain_text('| **width** | `12` |')
    page.locator('.cm-line',has_text='| **width** | `12` |').click();page.keyboard.press('End')
    page.keyboard.press('ArrowLeft');page.keyboard.press('ArrowLeft');page.keyboard.press('ArrowLeft')
    page.keyboard.press('Shift+ArrowLeft');page.keyboard.press('Shift+ArrowLeft');page.keyboard.insert_text('24')
    page.keyboard.press('Control+s');expect(page.locator('#dirty')).to_have_text('')
    page.get_by_role('button',name='Done editing table',exact=True).click()
    expect(page.locator('.md-table .passage-highlight')).to_have_text('width')
    page.locator('#mode').select_option('preview')
    expect(page.locator('.markdown-preview .passage-highlight')).to_have_text('width')
    page.locator('.thread blockquote').click();expect(page.locator('#mode')).to_have_value('preview')
    assert (root/'table.md').read_text()==text.replace('`12`','`24`')


def test_preview_discussions_repeated_text_entities_unicode_and_navigation(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    text='# Notes\r\n\r\n[link](https://example.invalid/target) target **😀 &amp; café**.\r\n\r\n| Word | Word |\r\n| --- | --- |\r\n| repeat | repeat |\r\n'
    (root/'note.md').write_bytes(text.encode())
    page.goto(url);open_file(page,'note.md');page.locator('#mode').select_option('preview')
    select_text(page,'.markdown-preview p strong');page.locator('#annotate').click()
    expect(page.locator('#selected-quote')).to_have_text('😀 &amp; café')
    page.locator('#comment-body').fill('Read in preview');page.locator('#comment-submit').click()
    expect(page.locator('.markdown-preview .passage-highlight')).to_have_text('😀 & café')
    first=ws.threads()[0];assert text[first['start']:first['end']]=='😀 &amp; café'
    select_text(page,'.markdown-preview tbody td:last-child');page.keyboard.press('Control+Enter')
    expect(page.locator('#comment-dialog')).to_be_visible();page.locator('#comment-body').fill('Second repeated cell');page.locator('#comment-submit').click()
    expect(page.locator('.thread')).to_have_count(2)
    second=ws.threads()[1];assert second['start']==text.rindex('repeat')
    page.locator('.thread blockquote').first.click();expect(page.locator('#mode')).to_have_value('preview')
    page.reload();expect(page.locator('.markdown-preview .passage-highlight')).to_have_count(2)
    page.locator('#mode').select_option('source');expect(page.locator('.cm-content .passage-highlight')).to_have_count(2)


def test_loading_and_oversized_warning(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    (root/'note.txt').write_text('Notes')
    with (root/'huge.html').open('wb') as file:file.truncate(300*1024*1024)
    page.goto(url)
    pending=[];page.route('**/api/discussions?*',lambda route:pending.append(route))
    open_file(page,'note.txt');expect(page.locator('#threads-loading')).to_be_visible()
    expect(page.locator('#threads')).to_have_attribute('aria-busy','true')
    pending[0].fulfill(status=200,content_type='application/json',body='{"threads":[],"index":[],"html":""}')
    expect(page.locator('#threads-loading')).not_to_be_visible()
    page.unroute('**/api/discussions?*');page.route('**/api/discussions?*',lambda route:route.fulfill(status=503,content_type='application/json',body='{"error":"Temporary failure"}'))
    page.locator('#thread-scope').check();expect(page.locator('#threads-loading')).not_to_be_visible()
    expect(page.locator('#threads')).to_have_attribute('aria-busy','false')
    page.unroute('**/api/discussions?*');open_file(page,'huge.html')
    expect(page.locator('.file-size-warning')).to_contain_text('300.0 MiB')
    expect(page.locator('.file-size-warning')).to_contain_text('8 MiB')
    expect(page.locator('#html-preview')).to_have_count(0)


def test_mermaid_live_preview_source_edit_and_invalid_diagram(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    (root/'diagram.md').write_text('# Flow\n\n```mermaid\nflowchart TD\n A[Read] --> B[Discuss]\n```\n\nEnd.\n')
    page.goto(url);open_file(page,'diagram.md')
    expect(page.locator('.md-diagram svg')).to_be_visible(timeout=20000)
    expect(page.locator('.md-diagram')).to_contain_text('Discuss')
    page.get_by_role('button',name='Edit diagram source').click()
    expect(page.locator('.cm-content')).to_contain_text('flowchart TD')
    page.get_by_role('button',name='Done editing diagram').click()
    expect(page.locator('.md-diagram svg')).to_be_visible()
    page.locator('#mode').select_option('preview');expect(page.locator('.markdown-preview svg')).to_be_visible()
    page.locator('#theme').click();expect(page.locator('.markdown-preview svg')).to_be_visible()
    page.locator('#mode').select_option('source');expect(page.locator('.cm-content')).to_contain_text('```mermaid')
    (root/'bad.md').write_text('# Invalid\n\n```mermaid\nthis is not a diagram\n```\n')
    page.locator('#refresh-files').click();open_file(page,'bad.md')
    expect(page.locator('.diagram-error')).to_contain_text('Unable to render diagram')
    expect(page.locator('.diagram-error')).to_contain_text('this is not a diagram')


def test_preview_multiline_quote_list_escaped_pipe_and_code_annotations(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    text='> First line\n> second line\n\n- One\n  continued\n\n| Key | Value |\n| --- | --- |\n| A\\|B | other |\n\n```python\nx = 1\ny = 2\n```\n'
    (root/'cases.md').write_text(text)
    page.goto(url);open_file(page,'cases.md');page.locator('#mode').select_option('preview')
    for selector,quote in [('.markdown-preview blockquote p','First line\n> second line'),('.markdown-preview li','One\n  continued'),('.markdown-preview tbody td:first-child','A\\|B'),('.markdown-preview pre code','x = 1\ny = 2\n')]:
        select_text(page,selector);expect(page.locator('#annotate')).to_be_enabled();page.locator('#annotate').click()
        page.locator('#comment-body').fill('Review '+quote);page.locator('#comment-submit').click()
        expect(page.locator('.thread')).to_have_count(len(ws.threads()))
        assert ws.threads()[-1]['quote']==quote
    expect(page.locator('.markdown-preview .passage-highlight')).to_have_count(4)
    assert (root/'cases.md').read_text()==text


def test_table_done_control_survives_temporarily_invalid_source(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    (root/'edit.md').write_text('# Table\n\n| Name | Value |\n| --- | --- |\n| width | 12 |\n')
    page.goto(url);open_file(page,'edit.md')
    page.get_by_role('button',name='Edit table source').click()
    page.locator('.cm-line',has_text='| --- | --- |').click();page.keyboard.press('Home')
    page.keyboard.press('Shift+End');page.keyboard.insert_text('temporarily invalid separator')
    expect(page.get_by_role('button',name='Done editing table')).to_be_visible()
    page.keyboard.press('Control+z')
    page.get_by_role('button',name='Done editing table').click();expect(page.locator('.md-table table')).to_be_visible()
