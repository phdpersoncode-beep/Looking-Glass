"""Lists have visible hierarchy while preserving editable Markdown and anchors."""
import os
import pytest
from test_requested_features import workspace_page, open_file

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]

LISTS = ('Before lists.\n\n- Bullet root\n  - Bullet child\n    - Bullet grandchild\n\n'
         '7. Number root\n   1. Number child\n      1. Number grandchild\n8. Number sibling\n\n'
         '- Mixed root\n  1. Mixed child\n     - Mixed grandchild\n\n'
         '- [ ] Task root\n  - [x] Task child\n    - [ ] Task grandchild\n\nAfter lists.\n')


def text_rect(locator, text):
    return locator.evaluate('''(el,text)=>{
      const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);let node;
      while(node=walker.nextNode()){
        const at=node.data.indexOf(text);if(at<0)continue;
        const range=document.createRange();range.setStart(node,at);range.setEnd(node,at+text.length);
        const {x,y,width,height}=range.getBoundingClientRect();return {x,y,width,height};
      }
      throw new Error('Missing text: '+text);
    }''', text)


def item(page, mode, text):
    return page.locator('.cm-line' if mode == 'live' else '.markdown-preview .md-mapped-text').filter(has_text=text).first


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'preview'])
def test_list_levels_are_indented_in_both_themes_and_narrow_panes(workspace_page, mode):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    (root/'lists.md').write_text(LISTS)
    page.goto(url); open_file(page, 'lists.md'); page.locator('#mode').select_option(mode)
    for width in [1440, 960]:
        page.set_viewport_size({'width': width, 'height': 1100})
        for theme in ['light', 'dark']:
            if page.locator('html').get_attribute('data-theme') != theme:page.locator('#theme').click()
            page.evaluate('document.fonts.ready')
            prose = text_rect(item(page, mode, 'Before lists.'), 'Before lists.')
            for family in ['Bullet', 'Number', 'Mixed', 'Task']:
                positions = [text_rect(item(page, mode, f'{family} {level}'), f'{family} {level}')['x'] for level in ['root', 'child', 'grandchild']]
                assert positions[0] >= prose['x']+20
                assert positions[1] >= positions[0]+15
                assert positions[2] >= positions[1]+15
            assert page.locator('#surface').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
    if mode == 'live':
        expect(page.locator('.md-task-checkbox')).to_have_count(3)
        expect(page.locator('.cm-content')).to_contain_text('7.')
        expect(page.locator('.cm-content')).to_contain_text('8.')
    else:
        expect(page.locator('.markdown-preview>ol')).to_have_attribute('start', '7')
        task = page.locator('.markdown-preview li').filter(has=page.locator('input[type=checkbox]')).last
        assert task.evaluate('el=>getComputedStyle(el).listStyleType') == 'none'
        expect(page.locator('.markdown-preview>ul').first.locator('ul ul')).to_have_count(1)
    assert (root/'lists.md').read_text() == LISTS


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_wrapped_continuations_edits_undo_and_task_toggle(workspace_page):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    text = ('Before.\n\n- Parent\n\n  12. '+'Long child content '*35+'\n      Continuation text.\n\n'
            '      Second paragraph.\n\n- [ ] Toggle this task\n\nAfter.\n')
    (root/'lists.md').write_text(text)
    page.goto(url); open_file(page, 'lists.md')
    page.set_viewport_size({'width': 1000, 'height': 1000}); page.evaluate('document.fonts.ready')
    line = item(page, 'live', 'Long child content')
    geometry = line.evaluate('''el=>{
      const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT),rects=[];let node;
      while(node=walker.nextNode())if(node.data.includes('Long child content')){
        const range=document.createRange();range.selectNodeContents(node);rects.push(...range.getClientRects());
      }
      return rects.filter(r=>r.width>1).map(r=>({x:r.x,y:r.y}));
    }''')
    # Ligature/font fragments can produce multiple rectangles on one visual row.
    rows = {}
    for rect in geometry:
        row = round(rect['y'], 1)
        rows[row] = min(rows.get(row, float('inf')), rect['x'])
    assert len(rows) >= 3
    assert max(rows.values())-min(rows.values()) <= 1
    for label in ['Continuation text.', 'Second paragraph.']:
        assert abs(text_rect(item(page, 'live', label), label)['x']-geometry[0]['x']) <= 1
    # Caret movement exposes syntax without shifting the text or losing hierarchy.
    before = text_rect(line, 'Long child content')
    line.click(); page.keyboard.press('Home')
    assert abs(text_rect(line, 'Long child content')['x']-before['x']) <= 1
    page.keyboard.press('Control+End'); page.keyboard.insert_text('Draft'); page.keyboard.press('Control+z')
    page.locator('.md-task-checkbox').check(); page.keyboard.press('Control+s')
    expect(page.locator('#dirty')).to_have_text('')
    assert (root/'lists.md').read_text() == text.replace('[ ]', '[x]')
    page.locator('#mode').select_option('source')
    expect(page.locator('.md-list-line')).to_have_count(0)
    expect(page.locator('.cm-content')).to_contain_text('  12.')
    page.locator('#mode').select_option('live')
    expect(page.locator('[data-list-depth="2"]').first).to_be_visible()


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_nested_list_annotations_comments_and_original_context(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    original = LISTS.replace('\n', '\r\n').replace('Bullet grandchild', '😀 Bullet grandchild')
    (root/'lists.md').write_bytes(original.encode())
    quote = '😀 Bullet grandchild'; start = original.index(quote)
    thread = ws.create_thread('lists.md', start, start+len(quote), LISTS, 'Reviewer', ws.read('lists.md')['version'])
    page.goto(url); open_file(page, 'lists.md')
    expect(page.locator('.cm-line[data-list-depth="3"] .passage-highlight')).to_have_text(quote)
    expect(page.locator('.comment-markdown ul ul ul')).to_have_count(2)
    page.locator('.original-context').click()
    expect(page.locator('.original-reading ul ul ul')).to_have_count(2)
    expect(page.locator('.original-reading .passage-highlight')).to_have_text(quote)
    page.locator('#context-return').click()
    page.locator('#mode').select_option('preview')
    leaf=page.locator('.markdown-preview .passage-highlight')
    expect(leaf).to_have_text(quote)
    # A deep item still maps to its exact Unicode/CRLF source, without list prefixes.
    leaf.evaluate('''el=>{const r=document.createRange();r.selectNodeContents(el);const s=getSelection();s.removeAllRanges();s.addRange(r);}''')
    page.locator('#annotate').click();expect(page.locator('#selected-quote')).to_have_text(quote)
    page.locator('#comment-body').fill('Nested source selection');page.locator('#comment-submit').click()
    expect(page.locator('#comment-dialog')).not_to_be_visible()
    created = next(t for t in ws.threads() if t['id'] != thread['id'])
    assert created['start'] == start and created['quote'] == quote
    assert (root/'lists.md').read_bytes() == original.encode()
