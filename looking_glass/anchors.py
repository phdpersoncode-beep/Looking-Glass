"""Conservative character-range mapping. Offsets count Unicode code points."""
from difflib import SequenceMatcher


def occurrences(text, quote):
    pos, found = 0, []
    while quote:
        at = text.find(quote, pos)
        if at < 0:
            break
        found.append(at)
        pos = at + 1
    return found


def relocate(old, new, start, end):
    if old == new:
        return start, end
    quote = old[start:end]
    if not quote:
        return None
    prefix, suffix = old[max(0, start - 48):start], old[end:end + 48]
    candidates = occurrences(new, quote)
    supported = [p for p in candidates if
                 (not prefix or new[max(0, p-len(prefix)):p] == prefix) and
                 (not suffix or new[p+len(quote):p+len(quote)+len(suffix)] == suffix)]
    if len(supported) > 1:
        return None
    matcher = SequenceMatcher(None, old, new, autojunk=False)
    # An unchanged block gives an unambiguous edit-history mapping.
    for a, b, size in matcher.get_matching_blocks():
        if a <= start and end <= a + size:
            # A whole-document replacement with repeated quotes has no reliable history.
            if len(occurrences(new, quote)) > 1 and size == len(quote):
                return None
            return b + start - a, b + end - a
    # Preserve changes strictly contained within an anchored passage, with
    # unchanged boundaries. Destruction/replacement of the full passage is orphaned.
    starts, ends = [], []
    for tag, a, z, b, y in matcher.get_opcodes():
        if tag == 'equal':
            if a <= start < z:
                starts.append(b + start - a)
            if a < end <= z:
                ends.append(b + end - a)
    if starts and ends and starts[0] < ends[-1]:
        return starts[0], ends[-1]
    # A normal edit at the first/last word still belongs to this passage if
    # enough of its original text survives and changed boundaries are exact.
    mapped_start, mapped_end, surviving = None, None, 0
    for tag, a, z, b, y in matcher.get_opcodes():
        if tag == 'equal':
            surviving += max(0, min(z,end)-max(a,start))
            if a <= start < z:
                mapped_start = b + start - a
            if a < end <= z:
                mapped_end = b + end - a
        elif tag in ('replace','delete'):
            if a == start and z < end:
                mapped_start = b
            if a > start and z == end:
                mapped_end = y
    if (surviving >= max(1,min(8,len(quote)//4)) and
            mapped_start is not None and mapped_end is not None and mapped_start < mapped_end):
        return mapped_start, mapped_end
    # A moved exact quote is accepted only with unique surrounding context.
    return (supported[0], supported[0] + len(quote)) if len(supported) == 1 else None
