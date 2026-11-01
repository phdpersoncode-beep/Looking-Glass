"""LaTeX stays readable, editable and anchored across Markdown surfaces."""
import os
from pathlib import Path

import pytest
from test_requested_features import workspace_page, open_file
from test_markdown_discussions import select_text

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]
SAMPLE = (Path(__file__).parent/'fixtures'/'markdown-math.md').read_text()


def drag_math(page, formula, reverse=False):
    """Use visible glyph coordinates without creating a synthetic selection."""
    formula.scroll_into_view_if_needed()
    points = formula.locator('.katex-html').evaluate('''el=>{
      const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT),points=[];let node;
      while(node=walker.nextNode())if(node.data.trim()){
        const range=document.createRange();range.selectNodeContents(node);const rect=range.getBoundingClientRect();
        if(rect.width>0&&rect.height>0)points.push({x:rect.x,y:rect.y,width:rect.width,height:rect.height});
      }
      return points.slice(0,3);
    }''')
    first, last = points[0], points[-1]
    start = (first['x']+1, first['y']+first['height']/2)
    end = (last['x']+last['width']-1, last['y']+last['height']/2)
    if reverse:
        start, end = end, start
    page.mouse.move(*start); page.mouse.down(); page.mouse.move(*end, steps=12); page.mouse.up()


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'preview'])
def test_requested_math_and_tables_render_locally_in_both_themes(workspace_page, mode):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    (root/'math.md').write_text(SAMPLE)
    requests = []
    page.on('request', lambda request: requests.append(request.url))
    page.goto(url); open_file(page, 'math.md'); page.locator('#mode').select_option(mode)
    host = page.locator('#surface')
    expect(host.locator('.katex')).to_have_count(8)
    expect(host.locator('.katex-display')).to_have_count(2)
    expect(host.locator('.math-error')).to_have_count(0)
    expect(host.locator('tbody td:first-child .katex annotation')).to_have_text(['R', 'B', 'K'])
    expect(host.locator('.katex-display').first).to_contain_text('valid completed reconstruction')
    expect(host.locator('mfrac')).to_have_count(1)
    for theme in ['light', 'dark']:
        if page.locator('html').get_attribute('data-theme') != theme:
            page.locator('#theme').click()
        page.evaluate('document.fonts.ready')
        expect(host.locator('.katex')).to_have_count(8)
        assert host.locator('.katex').first.evaluate('el=>getComputedStyle(el).color') == host.evaluate('el=>getComputedStyle(el).color')
        assert page.evaluate('document.fonts.check("16px KaTeX_Main")')
        page.set_viewport_size({'width': 960, 'height': 800})
        for formula in host.locator('.md-math-display').all():
            assert formula.evaluate('el=>el.clientWidth>0 && el.getBoundingClientRect().right<=document.documentElement.clientWidth')
    assert all(request.startswith(url+'/') for request in requests), requests
    assert (root/'math.md').read_text() == SAMPLE


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'preview'])
def test_formula_annotations_keep_tex_source_and_survive_polling_and_context(workspace_page, mode):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    original = '😀 before.\r\n\r\n| First | Second |\r\n| --- | --- |\r\n| $x^2$ | $x^2$ |\r\n\r\n$$\r\n\\frac{a}{b}\r\n$$\r\n'
    (root/'math.md').write_bytes(original.encode())
    page.goto(url); open_file(page, 'math.md'); page.locator('#mode').select_option(mode)
    host = '.md-table' if mode == 'live' else '.markdown-preview'
    select_text(page, host+' tbody td:last-child .katex-html')
    expect(page.locator('#annotate')).to_be_enabled(); page.locator('#annotate').click()
    expect(page.locator('#selected-quote')).to_have_text('$x^2$')
    page.locator('#comment-body').fill('Compare $x^2$ with $y^2$.'); page.locator('#comment-submit').click()
    expect(page.locator(host+' .md-math.passage-highlight .katex')).to_have_count(1)
    thread = ws.threads()[0]
    assert thread['quote'] == '$x^2$' and thread['start'] == original.rindex('$x^2$')
    expect(page.locator('.comment-markdown .katex')).to_have_count(2)
    # New discussion data refreshes highlights without rebuilding KaTeX nodes.
    page.locator(host+' tbody td:last-child .katex').evaluate('el=>el.dataset.identity="kept"')
    ws.reply(thread['id'], 'Also $z^2$.', 'Agent')
    expect(page.locator('.comment-markdown .katex')).to_have_count(3)
    expect(page.locator(host+' tbody td:last-child .katex')).to_have_attribute('data-identity', 'kept')
    select_text(page, '#surface .md-math-display .katex-html')
    expect(page.locator('#annotate')).to_be_enabled(); page.locator('#annotate').click()
    expect(page.locator('#selected-quote')).to_have_text('$$\n\\frac{a}{b}\n$$')
    page.locator('#comment-body').fill('Check the fraction'); page.locator('#comment-submit').click()
    expect(page.locator('.thread')).to_have_count(2)
    expect(page.locator('#comment-dialog')).not_to_be_visible()
    assert ws.threads()[-1]['quote'] == '$$\r\n\\frac{a}{b}\r\n$$'
    page.locator('#mode').select_option('preview')
    expect(page.locator('.markdown-preview .md-math.passage-highlight .katex')).to_have_count(2)
    page.locator('.thread .original-context').first.click()
    expect(page.locator('.original-reading .katex')).to_have_count(3)
    page.locator('#context-return').click()
    expect(page.locator('.markdown-preview .md-math.passage-highlight .katex')).to_have_count(2)
    page.reload()
    expect(page.locator('.markdown-preview .md-math.passage-highlight .katex')).to_have_count(2)
    assert (root/'math.md').read_bytes() == original.encode()


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_live_math_source_editing_undo_and_fences(workspace_page):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    original = 'Inline $x^2$.\n\n$$\nE=mc^2\n$$\n\n```latex\n\\begin{pmatrix}a&b\\\\c&d\\end{pmatrix}\n```\n'
    (root/'math.md').write_text(original)
    page.goto(url); open_file(page, 'math.md')
    expect(page.locator('#surface .katex')).to_have_count(3)
    page.locator('.md-formula-inline').focus(); page.keyboard.press('Enter')
    expect(page.get_by_role('button', name='Done editing math')).to_be_visible()
    line = page.locator('.cm-line', has_text='Inline $x^2$.')
    line.click(); page.keyboard.press('Home'); page.keyboard.press('Shift+End'); page.keyboard.insert_text('Inline $y_1$.')
    page.get_by_role('button', name='Done editing math').click()
    expect(page.locator('.md-formula-inline annotation')).to_have_text('y_1')
    page.keyboard.press('Control+z')
    expect(page.locator('.md-formula-inline annotation')).to_have_text('x^2')
    page.get_by_role('button', name='Edit math source', exact=True).first.click()
    line = page.locator('.cm-line', has_text='E=mc^2')
    line.click(); page.keyboard.press('Home'); page.keyboard.press('Shift+End'); page.keyboard.insert_text('E=mc^3')
    page.get_by_role('button', name='Done editing math').click()
    expect(page.locator('#surface .md-math-display annotation').first).to_have_text('E=mc^3')
    page.keyboard.press('Control+s'); expect(page.locator('#dirty')).to_have_text('')
    page.locator('#mode').select_option('source'); expect(page.locator('.cm-content')).to_contain_text('E=mc^3')
    page.locator('#mode').select_option('live'); expect(page.locator('#surface .katex')).to_have_count(3)
    assert (root/'math.md').read_text() == original.replace('mc^2', 'mc^3')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'preview'])
def test_review_math_keeps_provenance_and_katex_structure(workspace_page, mode):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    original = 'Value $x^2$.\n\n$$\n\\frac{a}{b}\n$$\n'
    (root/'math.md').write_text(original)
    page.goto(url); open_file(page, 'math.md'); page.locator('#work-mode').click()
    expect(page.locator('#approve-review')).to_be_visible()
    draft = ws.reviews.read(ws.reviews.list()[0]['id'])
    start = original.index('x^2')
    draft = ws.reviews.update(draft['id'], draft['version'], [dict(start=start, end=start+3, insert='y_1')], 'Codex', 'agent')
    expect(page.locator('#surface .md-math.review-agent .katex')).to_have_count(1)
    page.locator('#mode').select_option(mode)
    expect(page.locator('#surface .md-math.review-agent annotation')).to_have_text('y_1')
    expect(page.locator('#surface .md-math .review-deletion')).to_have_text('x^2')
    select_text(page, '#surface .md-math.review-agent .katex-html')
    page.locator('#annotate').click(); expect(page.locator('#selected-quote')).to_have_text('$y_1$')
    page.locator('#comment-body').fill('Review $y_1$.'); page.locator('#comment-submit').click()
    expect(page.locator('#surface .md-math.passage-highlight.review-agent .katex')).to_have_count(1)
    page.reload()
    expect(page.locator('#surface .md-math.passage-highlight.review-agent annotation')).to_have_text('y_1')
    assert (root/'math.md').read_text() == original
    assert ws.threads('math.md', review=draft['id'])[0]['quote'] == '$y_1$'


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_math_errors_untrusted_commands_and_discussion_markup_stay_inert(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    original = 'Safe text.\n\n$\\notACommand{x}$\n\n$\\def\\loop{\\loop}\\loop$\n\n$\\href{javascript:alert(1)}{click}$\n\n$\\includegraphics{https://example.invalid/image}$\n\n$\\text{\\#123}$\n\n`$literal$`\n\nCosts $5 and $10.\n'
    (root/'math.md').write_text(original)
    ws.create_thread('math.md', 0, 4, original+'\n<button class="thread-action">Forged</button><span data-lg-math="forged" class="md-math">Fake</span>', 'Reviewer', ws.read('math.md')['version'])
    page.goto(url); open_file(page, 'math.md'); page.locator('#mode').select_option('preview')
    for host in ['.markdown-preview', '.comment-markdown']:
        expect(page.locator(host+' .math-error')).to_have_count(2)
        expect(page.locator(host+' .math-error').first).to_have_text('$\\notACommand{x}$')
        expect(page.locator(host+' .katex')).to_have_count(3)
        expect(page.locator(host+' a, '+host+' img, '+host+' button')).to_have_count(0)
        expect(page.locator(host+' [data-lg-math]')).to_have_count(0)
        expect(page.locator(host+' code')).to_have_text('$literal$')
    assert page.locator('.comment-markdown .md-math').count() == 5
    assert (root/'math.md').read_text() == original


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'preview'])
def test_nested_math_delimiters_fences_and_wide_equations(workspace_page, mode):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    original = r'''# Heading with $\alpha$

**Inline \(x_i^2\)** and $\sqrt{x}$.

> \[
> \begin{aligned}a&=b\\c&=d\end{aligned}
> \]

- \(\beta\)

  $$
  \begin{bmatrix}1&0\\0&1\end{bmatrix}
  $$

~~~math
\sum_{i=1}^n i=\frac{n(n+1)}{2}
~~~

$$a_1+a_2+a_3+a_4+a_5+a_6+a_7+a_8+a_9+a_{10}+a_{11}+a_{12}=0$$
'''
    (root/'math.md').write_text(original)
    page.goto(url); open_file(page, 'math.md'); page.locator('#mode').select_option(mode)
    expect(page.locator('#surface .katex')).to_have_count(8)
    expect(page.locator('#surface .math-error')).to_have_count(0)
    expect(page.locator('#surface .katex-display')).to_have_count(4)
    page.set_viewport_size({'width': 960, 'height': 800})
    wide = page.locator('#surface .md-math-display').last
    assert wide.evaluate('el=>el.scrollWidth>el.clientWidth')
    before = wide.evaluate('el=>el.getBoundingClientRect().width')
    page.locator('#font-larger').click()
    assert wide.evaluate('el=>el.getBoundingClientRect().width') == before
    if mode == 'live':
        wide.locator('..').locator('..').hover()
        assert wide.evaluate('el=>el.closest(".md-formula").querySelector("button").getBoundingClientRect().right<=el.getBoundingClientRect().left')
        page.locator('#markdown-contents summary').click()
        expect(page.locator('#markdown-contents nav button')).to_have_count(1)
        expect(page.locator('#markdown-contents nav button')).to_contain_text('Heading with')
    assert (root/'math.md').read_text() == original


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_live_equation_widget_changes_between_inline_and_block_after_neighbor_edits(workspace_page):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    (root/'math.md').write_text('Before.\n\n$$x$$ tail\n\nAfter.\n')
    page.goto(url); open_file(page, 'math.md')
    expect(page.locator('.md-formula-inline')).to_have_count(1)
    point = page.locator('.cm-line', has_text='tail').evaluate('''el=>{
      const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);let node;
      while(node=walker.nextNode())if(node.data.includes('tail')&&!node.parentElement.closest('.md-formula')){
        const range=document.createRange();range.selectNodeContents(node);const rect=range.getBoundingClientRect();
        return {x:rect.x+rect.width/2,y:rect.y+rect.height/2};
      }
    }''')
    page.mouse.click(point['x'], point['y']); page.keyboard.press('End')
    for _ in range(5):
        page.keyboard.press('Shift+ArrowLeft')
    page.keyboard.press('Backspace')
    expect(page.locator('.md-formula-inline')).to_have_count(0)
    expect(page.get_by_role('button', name='Edit math source', exact=True)).to_be_visible()
    expect(page.locator('#surface .katex annotation')).to_have_text('x')
    page.keyboard.press('Control+z')
    expect(page.locator('.md-formula-inline')).to_have_count(1)
    expect(page.locator('#surface .katex annotation')).to_have_text('x')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'preview'])
@pytest.mark.parametrize('formula,reverse', [
    ('$abc=xyz$', False),
    ('$$\r\n\\frac{abc}{xyz}=123\r\n$$', True),
    ('$$\r\n\\begin{cases}abc,& xyz>0\\\\0,& xyz\\leq0\\end{cases}\r\n$$', False),
])
def test_mouse_drag_math_anchors_exact_repeated_source(workspace_page, mode, formula, reverse):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    original = '😀 Before.\r\n\r\n'+formula+'\r\n\r\n'+formula+'\r\n\r\nAfter.\r\n'
    (root/'math.md').write_bytes(original.encode())
    page.goto(url); open_file(page, 'math.md'); page.locator('#mode').select_option(mode)
    page.evaluate('document.fonts.ready')
    if mode == 'live':
        page.locator('.cm-line').first.click()
    target = page.locator('#surface .md-math').nth(1)
    drag_math(page, target, reverse)
    expect(page.locator('#annotate')).to_be_enabled()
    expect(page.locator('#selection-tools')).to_be_visible()
    selected = page.evaluate('getSelection().toString()')
    assert selected.strip()
    with page.expect_response(lambda response: '/api/discussions?' in response.url):
        pass
    assert page.evaluate('getSelection().toString()') == selected
    if reverse:
        page.keyboard.press('Control+Enter')
    else:
        page.locator('#selection-comment').click()
    expect(page.locator('#selected-quote')).to_have_text(formula.replace('\r\n', '\n'))
    page.locator('#comment-body').fill('Check this equation'); page.locator('#comment-submit').click()
    expect(page.locator('.thread')).to_have_count(1)
    expect(page.locator('#comment-dialog')).not_to_be_visible()
    thread = ws.threads()[0]
    assert thread['quote'] == formula and thread['start'] == original.rindex(formula)
    assert original[thread['start']:thread['end']] == formula
    mark = page.locator('#surface .md-math.passage-highlight')
    expect(mark.locator('.katex')).to_have_count(1)
    # A normal click remains navigation; it must not force another selection.
    page.evaluate('getSelection().removeAllRanges()')
    mark.locator('.katex-html .base').first.click()
    expect(page.locator('.thread.active')).to_have_count(1)
    assert page.evaluate('getSelection().isCollapsed')
    page.locator('#mode').select_option('preview'); page.reload()
    expect(page.locator('.markdown-preview .md-math.passage-highlight .katex')).to_have_count(1)
    assert (root/'math.md').read_bytes() == original.encode()


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'preview'])
def test_display_math_has_compact_spacing_and_aligns_with_prose(workspace_page, mode):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    (root/'math.md').write_text('Before.\n\n$$\n\\frac{abc}{xyz}=123\n$$\n\nAfter.\n')
    page.goto(url); open_file(page, 'math.md'); page.locator('#mode').select_option(mode)
    formula = page.locator('#surface .md-math-display')
    expect(formula.locator('.katex')).to_have_count(1)
    for theme in ['light', 'dark']:
        if page.locator('html').get_attribute('data-theme') != theme:
            page.locator('#theme').click()
        for width in [1440, 960]:
            page.set_viewport_size({'width': width, 'height': 900})
            page.evaluate('document.fonts.ready')
            geometry = formula.evaluate('''el=>{
              const box=el.getBoundingClientRect(),bases=[...el.querySelectorAll('.katex-html>.base')].map(n=>n.getBoundingClientRect());
              const left=Math.min(...bases.map(r=>r.left)),right=Math.max(...bases.map(r=>r.right)),top=Math.min(...bases.map(r=>r.top)),bottom=Math.max(...bases.map(r=>r.bottom));
              const host=el.closest('.md-formula')||el,prose=document.querySelector('#surface .cm-line,#surface .markdown-preview p');
              const walk=document.createTreeWalker(prose,NodeFilter.SHOW_TEXT),range=document.createRange();range.selectNodeContents(walk.nextNode());
              return {width:box.width,visibleWidth:right-left,height:host.getBoundingClientRect().height,visibleHeight:bottom-top,left:box.left,proseLeft:range.getBoundingClientRect().left};
            }''')
            assert geometry['width'] <= geometry['visibleWidth']+4
            assert geometry['height'] <= geometry['visibleHeight']+24
            assert abs(geometry['left']-geometry['proseLeft']) <= 3
            if mode == 'live':
                for gap in page.locator('.cm-line.md-math-gap').all():
                    assert gap.bounding_box()['height'] <= 20
                labels = page.locator('.cm-lineNumbers .cm-gutterElement').evaluate_all('''elements=>elements.filter(el=>el.textContent.trim()&&getComputedStyle(el).visibility!=='hidden').map(el=>{
                  const range=document.createRange();range.selectNodeContents(el);const rect=range.getBoundingClientRect();return {top:rect.top,bottom:rect.bottom};
                })''')
                for before, after in zip(labels, labels[1:]):
                    assert after['top'] >= before['bottom']-1
                page.locator('.md-formula').hover()
                expect(page.get_by_role('button', name='Edit math source', exact=True)).to_be_visible()
