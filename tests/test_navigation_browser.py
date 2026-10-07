"""Explorer, Markdown contents, and JSONL navigation regressions."""
import os
import pytest
from test_requested_features import workspace_page, open_file

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_explorer_toggle_preserves_width_folders_and_draft(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    (root/'folder').mkdir();(root/'folder'/'note.md').write_text('# Notes\n\nDraft.\n')
    page.goto(url);page.locator('#expand-files').click();open_file(page,'folder/note.md')
    separator=page.get_by_role('separator',name='Resize file explorer')
    separator.focus();page.keyboard.press('Home');page.keyboard.press('Shift+ArrowRight')
    expect(separator).to_have_attribute('aria-valuenow','170')
    page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.insert_text('Unsaved')
    width=page.locator('.document-panel').bounding_box()['width']
    arrow_box=page.locator('#explorer-toggle').bounding_box()
    page.get_by_role('button',name='Hide file explorer',exact=True).click()
    assert page.locator('#explorer-toggle').bounding_box()==arrow_box
    expect(separator).not_to_be_visible()
    expect(page.locator('#file-tree')).not_to_be_visible()
    assert page.locator('.file-sidebar').bounding_box()['width']==36
    expect(page.locator('#explorer-toggle')).to_be_focused()
    expect(page.locator('#tabs')).to_be_visible()
    assert page.locator('.document-panel').bounding_box()['width']>width
    expect(page.locator('.cm-content')).to_contain_text('Unsaved')
    page.locator('#zen-toggle').click();expect(page.locator('#explorer-toggle')).not_to_be_visible()
    page.locator('#zen-toggle').click();expect(page.locator('#explorer-toggle')).to_be_visible()
    page.get_by_role('button',name='Show file explorer',exact=True).click()
    expect(separator).to_have_attribute('aria-valuenow','170')
    assert page.locator('#explorer-toggle').bounding_box()==arrow_box
    expect(page.locator('.file-folder')).to_have_attribute('open','')
    expect(page.locator('.cm-content')).to_contain_text('Unsaved')
    page.locator('#save').click();expect(page.locator('#dirty')).to_have_text('')
    page.locator('#explorer-toggle').click();page.reload()
    expect(page.locator('#file-tree')).not_to_be_visible()
    assert page.locator('.file-sidebar').bounding_box()['width']==36
    page.locator('#explorer-toggle').click();expect(separator).to_have_attribute('aria-valuenow','170')
    expect(page.locator('.file-folder')).to_have_attribute('open','')
    page.locator('#collapse-files').click();expect(page.locator('.file-folder')).not_to_have_attribute('open','')
    page.locator('#expand-files').click();expect(page.locator('.file-folder')).to_have_attribute('open','')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_live_markdown_contents_tracks_headings_and_navigates(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    text='# **Report** &amp; café\r\n\r\n'+('Paragraph.\r\n\r\n'*80)+'## [Results](https://example.invalid)\r\n\r\n```md\r\n# Not a heading\r\n```\r\n\r\nSetext section\r\n--------------\r\n\r\n### Details\r\n'
    (root/'note.md').write_bytes(text.encode());(root/'empty.md').write_text('No headings.\n');(root/'other.md').write_text('# Other\n')
    page.goto(url);open_file(page,'note.md')
    bar=page.locator('#markdown-contents');expect(bar).to_be_visible()
    top=bar.bounding_box()['y'];bar.locator('summary').click()
    expect(bar.locator('nav button')).to_have_text(['Report & café','Results','Setext section','Details'])
    bar.get_by_role('button',name='Results',exact=True).click()
    expect(bar).not_to_have_attribute('open','')
    expect(page.locator('.cm-content')).to_be_focused()
    page.wait_for_function('()=>document.querySelector(".cm-scroller").scrollTop>500')
    assert abs(bar.bounding_box()['y']-top)<1
    # The selected heading is the actual source position, including CRLF conversion.
    page.keyboard.press('End');page.keyboard.insert_text(' updated')
    bar.locator('summary').click();expect(bar.locator('nav button')).to_contain_text(['Results updated'])
    page.keyboard.press('Escape');expect(bar).not_to_have_attribute('open','')
    page.locator('#mode').select_option('source');expect(bar).not_to_be_visible()
    page.locator('#mode').select_option('preview');expect(bar).not_to_be_visible()
    open_file(page,'other.md');bar.locator('summary').click();expect(bar.locator('nav button')).to_have_text(['Other'])
    open_file(page,'empty.md');bar.locator('summary').click();expect(bar.locator('nav')).to_have_text('No headings yet')
    assert (root/'note.md').read_bytes()==text.encode()


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_jsonl_entry_arrows_and_scroll_retention(workspace_page):
    import json
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    rows=[{f'field_{i:03}':f'{name} value {i}' for i in range(140)} for name in ['first','second','third']]
    original='\n'.join(json.dumps(row) for row in rows)+'\ninvalid\n'
    (root/'rows.jsonl').write_text(original);(root/'empty.jsonl').write_text('')
    page.goto(url);open_file(page,'rows.jsonl')
    previous=page.get_by_role('button',name='Previous entry',exact=True);next_=page.get_by_role('button',name='Next entry',exact=True)
    scroller=page.locator('.jsonl-detail .cm-scroller')
    expect(previous).to_be_disabled();expect(next_).to_be_enabled()
    scroller.evaluate('el=>el.scrollTop=700')
    page.wait_for_function('()=>document.querySelector(".jsonl-detail .cm-scroller").scrollTop>=690')
    top=scroller.evaluate('el=>el.scrollTop')
    next_.click();expect(page.locator('.jsonl-detail .viewer-heading')).to_contain_text('ROW 2 / 4')
    expect(page.locator('.jsonl-row.selected')).to_have_attribute('data-row','1')
    page.wait_for_function('()=>Math.abs(document.querySelector(".jsonl-detail .cm-scroller").scrollTop-700)<10')
    assert abs(scroller.evaluate('el=>el.scrollTop')-top)<10
    page.locator('.jsonl-row[data-row="2"]').click()
    expect(page.locator('.jsonl-detail .viewer-heading')).to_contain_text('ROW 3 / 4')
    page.wait_for_function('()=>Math.abs(document.querySelector(".jsonl-detail .cm-scroller").scrollTop-700)<10')
    previous.click();expect(page.locator('.jsonl-detail .viewer-heading')).to_contain_text('ROW 2 / 4')
    page.locator('.jsonl-raw').focus();page.keyboard.press('ArrowDown')
    expect(page.locator('.jsonl-detail .viewer-heading')).to_contain_text('ROW 3 / 4')
    # Search selects entries through the same scroll-preserving path.
    page.keyboard.press('Control+f');page.get_by_role('textbox',name='Find in JSONL').fill('first value 100')
    expect(page.locator('.jsonl-detail .viewer-heading')).to_contain_text('ROW 1 / 4')
    page.wait_for_function('()=>Math.abs(document.querySelector(".jsonl-detail .cm-scroller").scrollTop-700)<10')
    page.get_by_role('button',name='Close JSONL search').click()
    page.locator('.jsonl-row[data-row="3"]').click()
    expect(page.locator('.jsonl-detail .viewer-heading')).to_contain_text('MALFORMED')
    expect(next_).to_be_disabled();assert scroller.evaluate('el=>el.scrollTop')==0
    open_file(page,'empty.jsonl');expect(previous).to_be_disabled();expect(next_).to_be_disabled()
    assert (root/'rows.jsonl').read_text()==original
