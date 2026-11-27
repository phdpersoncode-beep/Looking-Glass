"""Create a tracked, synthetic Looking Glass workspace in a new directory."""
import argparse
import json
import subprocess
from pathlib import Path

from looking_glass.workspace import Workspace

TAGS = ('TODO', 'NOTE', 'P0', 'P1', 'P2', 'P3')
STATUSES = ('backlog', 'in_progress', 'to_review', 'done')
ACTIVE = 'overview.md'
TAB_PATHS = [ACTIVE, *(f'notes/tab-{i:02d}.txt' for i in range(1, 16))]
THREADS_PER_FILE = 10


def generate(root, files, cards, threads):
    if min(files, cards, threads) < 1:
        raise ValueError('File, card, and thread counts must be positive.')
    capacity = (files - files // 4 + 1) * THREADS_PER_FILE
    if threads > capacity:
        raise ValueError(f'Use more files for {threads} threads ({capacity} passages available).')
    root.mkdir(parents=True)
    root = root.resolve()

    def write(path, content):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')

    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True)

    write('.gitignore', '.looking-glass/\n')
    paths = []
    for i in range(files):
        extension = ('py', 'js', 'md', 'ipynb')[i % 4]
        path = f'modules/group-{i // 50:03d}/unit-{i:05d}.{extension}'
        tags = [TAGS[(i + offset) % len(TAGS)] for offset in (0, 3)]
        lines = [f'{tag}: Follow up on synthetic module {i}.' for tag in tags]
        if extension == 'ipynb':
            content = json.dumps(dict(nbformat=4, nbformat_minor=5, metadata={}, cells=[
                dict(cell_type='markdown', id='notes', metadata={}, source=['# '+lines[0]+'\n']),
                dict(cell_type='code', id='example', metadata={}, execution_count=None,
                     source=['# '+lines[1]+'\n', 'value = 42\n'], outputs=[]),
            ]))
        else:
            prefix = dict(py='# ', js='// ', md='- #')[extension]
            content = '\n'.join(prefix + line for line in lines) + '\n\n'
            content += '\n'.join(prefix + f'Review passage {j:02d} for module {i}.'
                                 for j in range(max(THREADS_PER_FILE, 30))) + '\n'
        write(path, content)
        if extension != 'ipynb':
            paths.append(path)
    overview = '# Synthetic review workspace\n\n' + '\n\n'.join(
        f'Review passage {j:02d} in the workspace overview.' for j in range(THREADS_PER_FILE))
    write(ACTIVE, overview + '\n')
    for i, path in enumerate(TAB_PATHS[1:], 1):
        write(path, ''.join(f'{i:02d}/{line:04d} Synthetic design discussion and implementation context.\n'
                            for line in range(2100)))

    git('init', '-q', '--template=')
    git('add', '--', '.')
    git('-c', 'user.name=Looking Glass benchmark', '-c', 'user.email=benchmark@example.invalid',
        '-c', 'commit.gpgSign=false', 'commit', '-qm', 'Add synthetic sources')
    commit = git('rev-parse', 'HEAD').strip()
    paths = [ACTIVE, *paths]

    ws = Workspace(root)
    with ws.connection() as db:
        for i in range(1, cards + 1):
            group = (i - 1) % 50
            milestone = group == 0
            parent = i - group if group else None
            db.execute('''INSERT INTO tasks(id,title,description,status,milestone,milestone_id,
                          position,milestone_number,parent_id,outline_position) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                       (i, f'Synthetic task {i:04d}', 'Review and validate the module. ' * 8,
                        STATUSES[i % 4], milestone, parent, i,
                        (i - 1) // 50 + 1 if milestone else None, parent, i))
            db.execute("INSERT INTO task_activity(card_id,kind,author,body) VALUES(?,'comment','Reviewer',?)",
                       (i, 'Track this in the next milestone.'))
        db.execute('UPDATE task_board_revision SET revision=1,next_card_id=?,next_activity_id=? WHERE id=1',
                   (cards + 1, cards + 1))
        for i in range(threads):
            j = i % THREADS_PER_FILE
            if j == 0:
                path = paths[i // THREADS_PER_FILE]
                content = (root / path).read_text(encoding='utf-8')
                db.execute('INSERT INTO snapshots VALUES(?,?)', (path, content))
            start = content.index(f'Review passage {j:02d}')
            end = content.index('\n', start)
            quote = content[start:end]
            origin = ws.origins.capture(db, path, content, start, end, quote,
                                        metadata=dict(commit_hash=commit, git_root=str(root), git_path=path))
            thread = db.execute('INSERT INTO threads(path,start,end,quote,resolved,origin_id) VALUES(?,?,?,?,?,?)',
                                (path, start, end, quote, i % 5 == 4, origin)).lastrowid
            for author in ('Reviewer', 'Author', 'Reviewer'):
                body = (f'{author} on passage {i:04d}. The **synthetic** example needs a review of '
                        'the expected result before the next checkpoint.\n\n- Compare the output.\n- Record the decision.')
                db.execute('INSERT INTO messages(thread_id,author,body,origin_id) VALUES(?,?,?,?)',
                           (thread, author, body, origin))

    return dict(files=files + len(TAB_PATHS) + 1, markers=files * 2, cards=cards,
                board_cards=cards - (cards + 49) // 50, threads=threads, messages=threads * 3,
                active_threads=min(threads, THREADS_PER_FILE))


def workload_arguments(parser):
    parser.add_argument('--files', type=int, default=2000, help='Number of generated marker files.')
    parser.add_argument('--cards', type=int, default=1200, help='Number of generated tasks including milestones.')
    parser.add_argument('--threads', type=int, default=3000, help='Number of generated three-message threads.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, help='New directory for the synthetic Git project.')
    workload_arguments(parser)
    args = parser.parse_args()
    try:
        summary = generate(args.root, args.files, args.cards, args.threads)
    except (FileExistsError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(summary, indent=2))
