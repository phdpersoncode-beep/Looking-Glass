"""Anchoring precision and bounded work on rewritten/repetitive files."""
import json
import subprocess
import sys

import pytest

from looking_glass.anchors import AnchorMapper, relocate
from looking_glass.workspace import Workspace


def mapped_quote(old, new, quote):
    start = old.index(quote)
    mapped = relocate(old, new, start, start + len(quote))
    return new[slice(*mapped)] if mapped else None


def test_replacement_with_matching_sentence_edges_is_not_attached():
    old = '## Decisions\nThe 8/8 dev/test split is accepted.\n## Next steps\n'
    new = '## Decisions\nThe annotators work on Loom and labels are accepted.\n## Next steps\n'
    assert mapped_quote(old, new, 'The 8/8 dev/test split is accepted.') is None


@pytest.mark.parametrize('new,expected', [
    ('New heading\nBefore\nA useful passage for review.\nAfter', 'A useful passage for review.'),
    ('Before\nA very useful passage for review.\nAfter', 'A very useful passage for review.'),
    ('Before\nThis useful passage for discussion.\nAfter', 'This useful passage for discussion.'),
    ('A completely different document.', None),
    ('Before\n\nAfter', None),
])
def test_source_passage_edits(new, expected):
    old = 'Before\nA useful passage for review.\nAfter'
    assert mapped_quote(old, new, 'A useful passage for review.') == expected


def test_repeated_quote_requires_unique_context():
    quote = 'Review this repeated passage.'
    old = 'First section\n' + quote + '\n' + 'x' * 100 + '\nSecond section\n' + quote + '\nEnd'
    new = 'Heading\n' + old + '\nFooter'
    start = old.rindex(quote)
    mapped = relocate(old, new, start, start + len(quote))
    assert mapped == (new.rindex(quote), new.rindex(quote) + len(quote))
    assert mapped_quote('left abc right', 'abc\nabc', 'abc') is None
    # Neither identical passage has surviving unique context after a rewrite.
    assert mapped_quote('left ' + quote + ' right', quote + '\n' + quote, quote) is None


def test_unique_exact_quote_survives_large_move_without_a_diff(monkeypatch):
    import looking_glass.anchors as anchors
    def forbidden(*args, **kwargs):
        pytest.fail('Whole-file or unnecessary character diff')
    monkeypatch.setattr(anchors, 'SequenceMatcher', forbidden)
    quote = 'A unique reviewed passage with 🪞 Unicode.'
    old = ('repeated plan text.\n' * 3000) + quote + '\nold footer'
    new = 'new header\n' + quote + '\n' + ('repeated changed text.\n' * 3000)
    assert mapped_quote(old, new, quote) == quote


def test_large_edited_passage_skips_unbounded_diff(monkeypatch):
    import looking_glass.anchors as anchors
    def forbidden(*args, **kwargs):
        pytest.fail('Oversized character diff')
    monkeypatch.setattr(anchors, 'SequenceMatcher', forbidden)
    quote = 'repeated plan text.\n' * 3000
    old = 'Before\n' + quote + 'After'
    new = old.replace('plan', 'changed plan')
    assert mapped_quote(old, new, quote) is None


def test_budget_exhaustion_is_conservative_and_exact_matches_still_work(monkeypatch):
    import looking_glass.anchors as anchors
    monkeypatch.setattr(anchors, 'MAX_DIFF_WORK', 0)
    quote = 'A useful passage for review.'
    old = 'Before\n' + quote + '\nAfter'
    assert mapped_quote(old, old.replace('useful', 'helpful'), quote) is None
    assert mapped_quote(old, 'Heading\n' + old, quote) == quote
    monkeypatch.setattr(anchors, 'MAX_SEARCH_WORK', 0)
    assert mapped_quote(old, 'Changed prefix\n' + quote + '\nChanged suffix', quote) is None


def test_mapper_shares_changed_passage_work(monkeypatch):
    import looking_glass.anchors as anchors
    original = anchors.SequenceMatcher
    calls = []
    def counted(*args, **kwargs):
        calls.append((len(args[1]), len(args[2])))
        return original(*args, **kwargs)
    monkeypatch.setattr(anchors, 'SequenceMatcher', counted)
    old = 'Before\nA useful passage for review.\nAfter'
    new = old.replace('A useful', 'This useful').replace('review.', 'discussion.')
    mapper = AnchorMapper(old, new)
    start, end = old.index('A useful'), old.index('\nAfter')
    for _ in range(28):
        assert new[slice(*mapper.relocate(start, end))] == 'This useful passage for discussion.'
    assert len(calls) == 1


def test_failed_anchors_keep_history_and_are_not_retried_on_every_poll(tmp_path, monkeypatch):
    file = tmp_path / 'plan.md'
    old = '## Decisions\nThe 8/8 dev/test split is accepted.\n## Next steps\n'
    quote = 'The 8/8 dev/test split is accepted.'
    file.write_text(old)
    ws = Workspace(tmp_path)
    source = ws.read('plan.md')
    start = old.index(quote)
    thread = ws.create_thread('plan.md', start, start + len(quote), 'Review', 'Agent', source['version'])
    ws.update_thread(thread['id'], resolved=True)
    file.write_text(old.replace(quote, 'The annotators work on Loom and labels are accepted.'))
    detached = ws.get_thread(thread['id'])
    assert detached['anchor_status'] == 'needs_reattachment'
    assert detached['quote'] == quote and detached['start'] == start and detached['resolved']
    assert ws.origins.read(thread['id'])['content'] == old
    def forbidden(*args, **kwargs):
        pytest.fail('Retrying an unchanged failed anchor')
    monkeypatch.setattr('looking_glass.workspace.AnchorMapper', forbidden)
    assert ws.get_thread(thread['id']) == detached
    assert Workspace(tmp_path).get_thread(thread['id']) == detached


def test_http_remains_responsive_after_large_repetitive_rewrite(tmp_path):
    # A subprocess deadline prevents the old quadratic algorithm hanging tests.
    # This workload used to exceed two seconds for even one thread.
    code = '''
import json, sys
from pathlib import Path
from looking_glass.app import create_app
root = Path(sys.argv[1])
old = 'prefix\\n' + 'repeated plan text.\\n' * 3000 + 'suffix'
file = root / 'plan.md'; file.write_text(old)
app = create_app(root); ws = app.extensions['workspace']
with ws.connection() as db:
    db.execute('INSERT INTO snapshots VALUES(?,?)', ('plan.md', old))
    for i in range(28):
        start = 7 + i * len('repeated plan text.\\n')
        identifier = db.execute('INSERT INTO threads(path,start,end,quote) VALUES(?,?,?,?)',
                                ('plan.md', start, start + 19, old[start:start+19])).lastrowid
        db.execute('INSERT INTO messages(thread_id,author,body) VALUES(?,?,?)', (identifier, 'Agent', 'Review'))
file.write_text(old.replace('plan', 'new plan'))
client = app.test_client(); headers = {'X-Looking-Glass-Token': ws.token}
assert client.get('/api/threads?status=open', headers=headers).status_code == 200
assert client.get('/api/project', headers=headers).status_code == 200
assert client.get('/api/file?path=plan.md', headers=headers).status_code == 200
assert client.get('/api/threads?status=open', headers=headers).status_code == 200
print(json.dumps(ws.thread_index()))
'''
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    threads = json.loads(result.stdout)
    assert len(threads) == 28
    assert all(t['anchor_status'] == 'needs_reattachment' for t in threads)
