"""PDF selection/highlights and database-only outline editing in both engines."""
import os

import pytest
from playwright.sync_api import expect

from test_requested_features import workspace_page, open_file
from test_pdfs import make_pdf

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


def select_pdf_text(page, number=1):
    text = page.locator(f'.pdf-page[data-page="{number}"][data-ready=true] .textLayer span').first
    expect(text).to_be_visible()
    box = text.bounding_box()
    page.mouse.move(box['x']+1, box['y']+box['height']/2)
    page.mouse.down()
    page.mouse.move(box['x']+box['width']-1, box['y']+box['height']/2, steps=8)
    page.mouse.up()
    expect(page.locator('#annotate')).to_be_enabled()


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_pdf_selection_comments_highlights_context_and_poll_stability(workspace_page):
    root, page, url, ws = workspace_page
    make_pdf(root/'paper.pdf'); original = (root/'paper.pdf').read_bytes()
    (root/'notes.md').write_text('# Notes\n\nKeep this document working.')
    page.goto(url); open_file(page, 'paper.pdf')
    expect(page.locator('.pdf-page[data-page="1"][data-ready=true]')).to_be_visible()
    expect(page.locator('#work-mode')).to_be_hidden()
    expect(page.locator('#save')).to_be_hidden()
    select_pdf_text(page)
    page.locator('#annotate').click()
    page.locator('#comment-body').fill('Explain this PDF passage')
    page.locator('#comment-form button[type=submit]').click()
    expect(page.locator('.thread')).to_have_count(1)
    expect(page.locator('.pdf-passage')).to_have_count(1)
    identifier = ws.threads('paper.pdf')[0]['id']
    page.evaluate('window.getSelection().removeAllRanges()')
    page.locator('.textLayer span').first.click()
    expect(page.locator('#passage-spotlight')).to_be_visible()
    # Clicking the passage only focuses the sidebar; no document jump.
    before = page.locator('#surface').evaluate('el=>el.scrollTop')
    page.locator('.reply-form textarea').fill('An unsent reply')
    page.locator('.pdf-passage').evaluate('el=>window.pdfMark=el')
    ws.reply(identifier, 'Agent explanation', 'Agent')
    expect(page.locator('.thread')).to_contain_text('Agent explanation', timeout=10000)
    assert page.locator('.reply-form textarea').input_value() == 'An unsent reply'
    assert page.locator('.pdf-passage').evaluate('el=>el===window.pdfMark')
    assert abs(page.locator('#surface').evaluate('el=>el.scrollTop')-before) < 2
    # Open immutable text context, then resume the same PDF surface.
    page.locator('[data-action=original]').first.click()
    expect(page.locator('.original-banner')).to_be_visible()
    expect(page.locator('.cm-content')).to_contain_text('PDF page 1')
    page.locator('#context-return').click()
    expect(page.locator('.pdf-page[data-page="1"][data-ready=true]')).to_be_visible()
    open_file(page, 'notes.md'); open_file(page, 'paper.pdf')
    expect(page.locator('.pdf-passage')).to_have_count(1)
    page.reload(); expect(page.locator('.pdf-passage')).to_have_count(1)
    assert (root/'paper.pdf').read_bytes() == original


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_pdf_bookmark_editor_persistence_navigation_and_layout(workspace_page):
    root, page, url, ws = workspace_page
    make_pdf(root/'paper.pdf'); original = (root/'paper.pdf').read_bytes()
    page.goto(url); open_file(page, 'paper.pdf')
    contents = page.locator('#pdf-contents')
    expect(page.locator('.pdf-page[data-page="1"][data-ready=true]')).to_be_visible()
    contents.locator('summary').click()
    contents.get_by_role('button', name='Conclusion · 3', exact=True).click()
    expect(page.locator('.pdf-page[data-page="3"][data-ready=true]')).to_be_visible()
    assert page.locator('#surface').evaluate('el=>el.scrollTop') > 500
    contents.locator('summary').click()
    contents.get_by_role('button', name='Edit bookmarks', exact=True).click()
    rows = contents.locator('.pdf-bookmark-row')
    rows.nth(2).get_by_role('button', name='Move up Conclusion', exact=True).click()
    rows.nth(0).get_by_label('Bookmark title', exact=True).fill('Final chapter')
    contents.get_by_role('button', name='Add bookmark', exact=True).click()
    rows.last.get_by_label('Bookmark title', exact=True).fill('Custom bookmark')
    rows.last.get_by_label('Bookmark page', exact=True).fill('2')
    rows.nth(1).get_by_role('button', name='Remove Introduction', exact=True).click()
    rows.last.get_by_role('button', name='Indent Custom bookmark', exact=True).click()
    contents.get_by_role('button', name='Save bookmarks', exact=True).click()
    expect(contents.get_by_role('button', name='Edit bookmarks', exact=True)).to_be_visible()
    expected = ws.pdfs.read('paper.pdf')['bookmarks']
    assert [item['title'] for item in expected] == ['Final chapter', 'Details', 'Custom bookmark']
    assert [item['level'] for item in expected] == [0, 0, 1]
    contents.get_by_role('button', name='Edit bookmarks', exact=True).click()
    rows.first.get_by_label('Bookmark title', exact=True).fill('Discard me')
    contents.get_by_role('button', name='Cancel', exact=True).click()
    expect(contents.get_by_role('button', name='Final chapter · 3', exact=True)).to_be_visible()
    contents.get_by_role('button', name='Edit bookmarks', exact=True).click()
    for theme, width in [('light', 900), ('dark', 1440)]:
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme', theme)
        page.set_viewport_size({'width': width, 'height': 960})
        assert contents.locator('nav').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
        page.screenshot(path=f'/tmp/looking-glass-pdf-{theme}-{width}.png')
    contents.get_by_role('button', name='Cancel', exact=True).click()
    page.reload(); expect(page.locator('.pdf-page[data-page="1"][data-ready=true]')).to_be_visible()
    contents.locator('summary').click()
    expect(contents.get_by_role('button', name='Custom bookmark · 2', exact=True)).to_be_visible()
    assert ws.pdfs.read('paper.pdf')['bookmarks'] == expected
    assert (root/'paper.pdf').read_bytes() == original


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_pdf_external_replacement_detaches_and_allows_explicit_reattachment(workspace_page):
    root, page, url, ws = workspace_page
    make_pdf(root/'paper.pdf')
    metadata = ws.pdfs.read('paper.pdf')
    thread = ws.pdfs.create_thread('paper.pdf', dict(page=1, quote='A passage', rects=[[.1,.1,.2,.03]]), 'Existing feedback', 'User', metadata['version'])
    page.goto(url); open_file(page, 'paper.pdf')
    expect(page.locator('.pdf-passage')).to_have_count(1)
    make_pdf(root/'paper.pdf', 'Replacement text')
    expect(page.locator('.pdf-passage')).to_have_count(0, timeout=10000)
    expect(page.locator('.thread')).to_contain_text('reattach')
    select_pdf_text(page)
    page.locator('[data-action=reattach]').click()
    expect(page.locator('.pdf-passage')).to_have_count(1)
    assert ws.get_thread(thread['id'])['anchor_status'] == 'attached'
    assert ws.origins.read(thread['id'])['origin']['render_anchor']['quote'] == 'A passage'


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_pdf_bookmark_conflict_preserves_draft_and_zoom_keeps_geometry(workspace_page):
    root, page, url, ws = workspace_page
    make_pdf(root/'paper.pdf', pages=20)
    (root/'notes.md').write_text('# Notes')
    page.goto(url); open_file(page, 'paper.pdf')
    first = page.locator('.pdf-page[data-page="1"][data-ready=true]')
    expect(first).to_be_visible()
    assert page.locator('.pdf-page canvas').count() < 20
    select_pdf_text(page)
    page.locator('#annotate').click(); page.locator('#comment-body').fill('Zoomed text')
    page.locator('#comment-form button[type=submit]').click()
    expect(page.locator('.pdf-passage')).to_have_count(1)
    width = first.bounding_box()['width']
    page.get_by_role('button', name='Increase PDF zoom', exact=True).click()
    page.wait_for_function('(width)=>document.querySelector(".pdf-page").getBoundingClientRect().width>width', arg=width)
    page.wait_for_function('()=>Math.abs(document.querySelector(".pdf-sheet").getBoundingClientRect().width-document.querySelector(".pdf-page").getBoundingClientRect().width)<1')
    marker, text = page.evaluate('''()=>[document.querySelector('.pdf-passage'),document.querySelector('.textLayer span')].map(el=>{const r=el.getBoundingClientRect();return {x:r.x,width:r.width};})''')
    assert abs(marker['x']-text['x']) < 4
    assert abs(marker['width']-text['width']) < 4
    contents = page.locator('#pdf-contents')
    contents.locator('summary').click(); contents.get_by_role('button', name='Edit bookmarks', exact=True).click()
    contents.get_by_label('Bookmark title', exact=True).first.fill('My unsaved title')
    open_file(page, 'notes.md'); open_file(page, 'paper.pdf')
    contents.locator('summary').click()
    expect(contents.get_by_label('Bookmark title', exact=True).first).to_have_value('My unsaved title')
    metadata = ws.pdfs.read('paper.pdf')
    ws.pdfs.save_bookmarks('paper.pdf', [], metadata['bookmark_revision'], metadata['version'])
    contents.get_by_role('button', name='Save bookmarks', exact=True).click()
    expect(page.locator('#notice')).to_contain_text('changed elsewhere')
    expect(contents.get_by_label('Bookmark title', exact=True).first).to_have_value('My unsaved title')
    assert ws.pdfs.read('paper.pdf')['bookmarks'] == []
    contents.get_by_role('button', name='Cancel', exact=True).click()
    contents.get_by_role('button', name='Reload contents', exact=True).click()
    expect(contents.locator('nav')).to_contain_text('No bookmarks yet')
