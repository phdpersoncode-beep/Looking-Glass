"""Collapsed previews follow the text and keep crowded passages readable."""
import os

import pytest
from playwright.sync_api import expect

from test_requested_features import open_file, workspace_page

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER'),
]


def add_thread(ws, name, text, passage, message):
    start = text.index(passage)
    return ws.create_thread(name, start, start + len(passage), message, 'Reviewer', ws.read(name)['version'])['id']


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('theme, width, mode', [('light', 1270, 'preview'), ('dark', 900, 'live')])
def test_collapsed_stacks_follow_passage_and_reveal_extra_threads(workspace_page, theme, width, mode):
    root, page, url, ws = workspace_page
    text = ('# City trees\n\n' + 'Read the planting plan.\n\n' * 9
            + 'Leave room for mature roots.\n\nMap the shade.\n\nWatch where runoff collects.\n\n'
            + 'Keep notes on each site.\n\n' * 25)
    name = 'trees.md'
    (root / name).write_text(text)
    roots = [add_thread(ws, name, text, 'room for mature roots', body) for body in (
        'Clarify **how much** space a mature tree needs.',
        'Could we show minimum pit dimensions?',
        'Add a diagram of the soil trench.',
        'Define continuous soil for volunteers.',
    )]
    nearby = [add_thread(ws, name, text, anchor, body) for anchor, body in (
        ('Map the shade', 'Include a simple shade map.'),
        ('Map the shade', 'Use a late afternoon photo.'),
        ('Watch where runoff collects', 'Add a photo of pooling water.'),
    )]
    page.set_viewport_size({'width': width, 'height': 850})
    page.add_init_script(f"localStorage.setItem('looking-glass-theme', '{theme}');")
    page.goto(url)
    open_file(page, name)
    page.locator('#mode').select_option(mode)
    sidebar = page.locator('.discussion-content')
    if theme == 'dark':
        sep = page.get_by_role('separator', name='Resize discussions')
        sep.focus()
        page.keyboard.press('Home')
        expect(sep).to_have_attribute('aria-valuenow', '220')
    scroller = page.locator('#surface' if mode == 'preview' else '#surface .cm-scroller')
    page.get_by_role('button', name='Collapse all threads').click()
    preview = page.get_by_role('button', name=f'Expand thread {roots[0]}', exact=True)
    expect(preview).to_have_text('Clarify how much space(...)')
    expect(preview.locator('svg')).to_be_visible()
    toggle = page.get_by_role('button', name='+2 more', exact=True)
    expect(toggle).to_have_attribute('aria-expanded', 'false')
    expect(page.locator(f'.thread[data-thread="{roots[2]}"]')).to_be_hidden()
    target = page.locator(f'#surface .passage-highlight[data-anchor="{roots[0]}"]').first
    target.scroll_into_view_if_needed()
    expect(sidebar).to_have_attribute('data-aligned-thread-previews', '')
    page.wait_for_function('''([id, delta]) => {
      const mark = document.querySelector('#surface [data-anchor="' + id + '"]');
      const button = document.querySelector('.thread[data-thread="' + id + '"] .thread-summary');
      return mark && Math.abs(mark.getBoundingClientRect().y + mark.getBoundingClientRect().height / 2
        - button.getBoundingClientRect().y - button.getBoundingClientRect().height / 2) < delta;
    }''', arg=[roots[0], 4])
    before = preview.bounding_box()['y']
    scroller.evaluate('el => el.scrollTop += 65')
    page.wait_for_function('''([id, expected]) => {
      const button = document.querySelector('.thread[data-thread="' + id + '"] .thread-summary');
      return Math.abs(button.getBoundingClientRect().y - expected) < 3;
    }''', arg=[roots[0], before - 65])
    cards = page.locator('#threads > .thread:visible').evaluate_all('cards => cards.map(card => card.getBoundingClientRect().toJSON())')
    assert all(first['bottom'] <= second['top'] for first, second in zip(cards, cards[1:]))
    document = page.locator('#surface').bounding_box()
    assert preview.bounding_box()['x'] >= document['x'] + document['width']
    expect(page.get_by_role('button', name=f'Expand thread {nearby[-1]}', exact=True)).to_be_visible()
    toggle.focus()
    page.keyboard.press('Enter')
    show_fewer = page.get_by_role('button', name='Show fewer', exact=True)
    expect(show_fewer).to_have_attribute('aria-expanded', 'true')
    expect(show_fewer).to_be_focused()
    page.get_by_role('button', name=f'Expand thread {roots[3]}', exact=True).click()
    expect(page.locator(f'.thread.active[data-thread="{roots[3]}"] .thread-body')).to_contain_text('Define continuous soil')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_collapsed_html_preview_tracks_report_scroll(workspace_page):
    root, page, url, ws = workspace_page
    name = 'report.html'
    text = '<div style="height:280px"></div><p id="target">Tree report passage</p><div style="height:1800px"></div>'
    (root / name).write_text(text)
    thread_id = add_thread(ws, name, text, 'Tree report passage', 'Clarify the findings about young trees.')
    page.goto(url)
    open_file(page, name)
    report = page.frame_locator('#html-preview').locator('#target')
    expect(report).to_be_visible()
    page.get_by_role('button', name='Collapse all threads').click()
    expect(page.locator('.discussion-content')).to_have_attribute('data-aligned-thread-previews', '')
    preview = page.get_by_role('button', name=f'Expand thread {thread_id}', exact=True)
    expect(preview).to_have_text('Clarify the findings about(...)')
    before = preview.bounding_box()['y']
    report.evaluate('() => window.scrollTo(0, 80)')
    page.wait_for_function('''([id, y]) => {
      const preview = document.querySelector('.thread[data-thread="' + id + '"] .thread-summary');
      return Math.abs(preview.getBoundingClientRect().top - y) < 3;
    }''', arg=[thread_id, before - 80])
