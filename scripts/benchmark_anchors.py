"""Disposable changed-file anchoring benchmark; never reads user workspaces."""
import json
import statistics
import tempfile
import time
from pathlib import Path

from looking_glass.app import create_app


def measure(lines, unique):
    elapsed, unchanged = [], []
    for _ in range(5):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            filler = 'repeated plan text.\n' * lines
            quotes = [f'Reviewed passage {i:02}: keep this exact decision.' for i in range(28)]
            old = 'prefix\n' + filler + '\n'.join(quotes) + '\nsuffix' if unique else 'prefix\n' + filler + 'suffix'
            new = '\n'.join(reversed(quotes)) + '\n' + filler.replace('plan', 'new plan') + 'new footer' if unique else old.replace('plan', 'new plan')
            file = root / 'plan.md'; file.write_text(old, encoding='utf-8')
            app = create_app(root); ws = app.extensions['workspace']
            with ws.connection() as db:
                db.execute('INSERT INTO snapshots VALUES(?,?)', ('plan.md', old))
                for i in range(28):
                    quote = quotes[i] if unique else 'repeated plan text.\n'
                    start = old.index(quote) if unique else 7 + i * len(quote)
                    identifier = db.execute('INSERT INTO threads(path,start,end,quote) VALUES(?,?,?,?)',
                                            ('plan.md', start, start + len(quote), quote)).lastrowid
                    db.execute('INSERT INTO messages(thread_id,author,body) VALUES(?,?,?)', (identifier, 'Agent', 'Review'))
            file.write_text(new, encoding='utf-8')
            client = app.test_client(); headers = {'X-Looking-Glass-Token': ws.token}
            route = '/api/threads?status=open'
            started = time.perf_counter()
            response = client.get(route, headers=headers)
            elapsed.append(1000 * (time.perf_counter() - started))
            assert response.status_code == 200
            statuses = [t['anchor_status'] for t in response.json['threads']]
            expected = 'attached' if unique else 'needs_reattachment'
            assert statuses == [expected] * 28
            started = time.perf_counter()
            assert client.get(route, headers=headers).status_code == 200
            unchanged.append(1000 * (time.perf_counter() - started))
    return dict(source_bytes=len(old.encode('utf-8')), threads=28,
                workload='moved unique passages' if unique else 'rewritten repeated passages',
                changed_request_median_ms=round(statistics.median(elapsed), 2),
                unchanged_request_median_ms=round(statistics.median(unchanged), 2),
                attached=statuses.count('attached'), needs_reattachment=statuses.count('needs_reattachment'))


if __name__ == '__main__':
    print(json.dumps([measure(lines, unique) for lines in (3000, 100000) for unique in (False, True)], indent=2))
