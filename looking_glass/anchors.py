"""Conservative, bounded source anchoring. Offsets count Unicode code points."""
from difflib import SequenceMatcher

# Per changed file, shared by every thread, including resolved ones. Exhaustion
# means manual reattachment, never a more speculative fallback.
MAX_DIFF_WORK = 1_000_000
MAX_DIFF_SIDE = 2048
MAX_SEARCH_WORK = 256 * 1024 * 1024
CONTEXT = 48


def occurrences(text, quote, limit=None):
    pos, found = 0, []
    while quote and (limit is None or len(found) < limit):
        at = text.find(quote, pos)
        if at < 0:
            break
        found.append(at)
        pos = at + 1
    return found


def common_edges(old, new):
    """Disjoint unchanged prefix/suffix; linear even for repetitive input."""
    prefix, suffix = 0, 0
    size = min(len(old), len(new))
    while prefix < size and old[prefix] == new[prefix]:
        prefix += 1
    while suffix < size - prefix and old[-1-suffix] == new[-1-suffix]:
        suffix += 1
    return prefix, suffix


class AnchorMapper:
    """One reconciliation, without whole-document fuzzy diffs.

    Exact unchanged ranges and unique quotes are cheap. An edited quote needs
    unique unchanged context on both sides and substantial surviving text.
    Only its bounded changed middle is diffed. Failed/ambiguous matches retain
    the previous quote/positions for manual repair and immutable origin access.
    """

    def __init__(self, old, new):
        self.old, self.new = old, new
        self.prefix, self.suffix = common_edges(old, new)
        self.diff_work = MAX_DIFF_WORK
        self.search_work = MAX_SEARCH_WORK
        self._hits, self._old_hits, self._similarity, self._mapped = {}, {}, {}, {}

    def hits(self, quote, original=False):
        text, cache = (self.old, self._old_hits) if original else (self.new, self._hits)
        if quote not in cache:
            # Two hits suffice to reject ambiguity. Do not allocate all matches
            # for a short quote in a repetitive multi-megabyte document.
            cost = 2 * len(text)
            if cost > self.search_work:
                return None
            self.search_work -= cost
            cache[quote] = occurrences(text, quote, limit=2)
        return cache[quote]

    def similar(self, old, new):
        key = old, new
        if key in self._similarity:
            return self._similarity[key]
        prefix, suffix = common_edges(old, new)
        a = old[prefix:len(old)-suffix]
        b = new[prefix:len(new)-suffix]
        cost = len(a) * len(b)
        if max(len(a), len(b)) > MAX_DIFF_SIDE or cost > self.diff_work:
            return False
        self.diff_work -= cost
        blocks = SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
        surviving = prefix + suffix + sum(size for _, _, size in blocks)
        longest = max(prefix, suffix, max(size for _, _, size in blocks))
        meaningful = lambda text: sum(not c.isspace() for c in text)
        kept = meaningful(old[:prefix]) + meaningful(old[len(old)-suffix:])
        kept += sum(meaningful(a[x:x+size]) for x, _, size in blocks)
        # Previously a few characters, or just matching first/last letters,
        # could attach a rewritten sentence to an unrelated passage.
        result = (surviving >= .7 * len(old) and surviving >= .6 * len(new)
                  and 3 * surviving >= len(old) + len(new)
                  and kept >= .65 * meaningful(old) and kept >= .5 * meaningful(new)
                  and longest >= min(12, max(1, len(old) // 2))
                  and len(old.strip()) >= 8)
        self._similarity[key] = result
        return result

    def relocate(self, start, end):
        key = start, end
        if key not in self._mapped:
            self._mapped[key] = self._relocate(start, end)
        return self._mapped[key]

    def _relocate(self, start, end):
        old, new = self.old, self.new
        if not 0 <= start < end <= len(old):
            return None
        if end <= self.prefix:
            return start, end
        if self.suffix and start >= len(old) - self.suffix:
            shift = len(new) - len(old)
            return start + shift, end + shift
        quote = old[start:end]
        before, after = old[max(0, start-CONTEXT):start], old[end:end+CONTEXT]
        exact = self.hits(quote)
        if exact is None:
            return None
        original = self.hits(quote, original=True) if len(exact) == 1 else None
        if original is not None and len(original) == 1 and len(exact) == 1 and len(quote.strip()) >= 8:
            return exact[0], exact[0] + len(quote)
        # Repeated/short quotes need unique surrounding context, rather than
        # whichever identical passage a character diff happened to choose.
        supported = self.hits(before + quote + after)
        original_context = self.hits(before + quote + after, original=True) if supported else None
        if (supported is not None and len(supported) == 1
                and original_context is not None and len(original_context) == 1):
            at = supported[0] + len(before)
            return at, at + len(quote)
        if exact:
            return None
        left = self.hits(before) if before else [0]
        right = self.hits(after) if after else [len(new)]
        if left is None or right is None or len(left) != 1 or len(right) != 1:
            return None
        a, b = left[0] + len(before), right[0]
        if a < b and self.similar(quote, new[a:b]):
            return a, b
        return None


def relocate(old, new, start, end):
    return AnchorMapper(old, new).relocate(start, end)
