"""Assert CI's browser shards contain every collected case exactly once."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def collect(*arguments):
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', '-m', 'browser', '--collect-only', '-q', *arguments],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return {line for line in result.stdout.splitlines() if line.startswith('tests/') and '::' in line}


def main():
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    if total < 1:
        raise SystemExit('Shard count must be positive.')
    cases = collect()
    shards = [collect(f'--browser-shard={index}/{total}') for index in range(total)]
    if not cases or set.union(*shards) != cases or sum(map(len, shards)) != len(cases):
        raise SystemExit('Browser shards dropped or duplicated cases.')
    print(f'{len(cases)} browser cases, shard sizes {[len(shard) for shard in shards]}: complete and disjoint.')


if __name__ == '__main__':
    main()
