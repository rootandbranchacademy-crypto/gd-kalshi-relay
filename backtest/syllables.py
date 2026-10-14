"""BT1.1-SYL: mechanical team-name syllable declarations for the GD-C1.0 sound module.

GD-C1.0 (2026-10-11 log entry) matched the MC navamsha syllable "by hand against
candidate syllables written down before the game". A retrospective replay cannot
reproduce hand judgment, so this module replaces it with a fixed, declared rule
that is applied identically to every team. It reads only canonical team names;
it never sees charts, quotes or outcomes. Declarations are written once per team,
hashed, and must be committed before any replay that uses them.

Rule (frozen as BT1.1-SYL-1):
  Words: every whitespace-separated word of the ESPN displayName, letters only,
  lower-cased. A word with no vowel letter (e.g. "St.") or containing a digit
  ("76ers") yields no candidates and is reported.
  Candidate first syllables are the union of
    (A) spelling: onset consonant letters + first vowel letter; if the first
        vowel letter is immediately followed by another vowel letter, both
        vowels are taken ("Houston" -> ho, hu);
    (B) pronunciation: onset consonants + first vowel phoneme of EVERY CMU
        Pronouncing Dictionary entry for the word (cmudict 1.0.32), using the
        book's equivalences e ~ ai and o ~ au (p.142ff.); the diphthongs AY
        and AW also give their first element a.
  Consonant mapping (book substitutions, ch.7): w -> v; f/ph -> p and ph;
  z -> jh; t and d -> dental and retroflex forms; th -> t and th; c before
  e/i/y -> s, otherwise k; ch -> c/ch; sh -> sh; q -> k; x -> no candidates.
  No other aspirate is added (b is not bh, k is not kh): the book names only
  the f -> pa/pha and z -> jha substitutions. A consonant cluster is
  reduced to its first consonant ("Flyers" -> f).
  Candidates are emitted as the exact variant strings used by gd_engine.SYL
  so that replay.syllable_score can compare them by string equality.

Remaining discretion (disclosed, not resolved by the book): the cluster
reduction, the dental/retroflex equivalence for English t/d, y as a vowel, and
taking every CMUdict pronunciation. The rule was checked for agreement with the
16 word declarations Claude published prospectively on 2026-10-11; it was not
tuned on any outcome.
"""
import json
import re
from pathlib import Path

RULE = 'BT1.1-SYL-1'
VOWELS = 'aeiou'
PHONE_VOWEL = {'AA': ['a', 'o'], 'AE': ['a'], 'AH': ['a', 'u'], 'AO': ['o'], 'AW': ['a', 'o'], 'AY': ['a', 'e'],
               'EH': ['e'], 'ER': ['a'], 'EY': ['e'], 'IH': ['i'], 'IY': ['i'], 'OW': ['o'], 'OY': ['o'],
               'UH': ['u'], 'UW': ['u']}
PHONE_CONS = {'B': 'b', 'CH': 'ch', 'D': 'd', 'DH': 'th', 'F': 'f', 'G': 'g', 'HH': 'h', 'JH': 'j', 'K': 'k',
              'L': 'l', 'M': 'm', 'N': 'n', 'NG': 'ng', 'P': 'p', 'R': 'r', 'S': 's', 'SH': 'sh', 'T': 't',
              'TH': 'th', 'V': 'v', 'W': 'w', 'Y': 'y', 'Z': 'z', 'ZH': 'z'}


def engine_index(syl_table):
    """Map plain consonant+vowel bases to the engine's variant strings."""
    index = {}
    for cells in syl_table.values():
        for cell in cells:
            for variant in cell.split('/'):
                plain = re.sub(r'\(r\)|\(retroflex\)', '', variant)
                bases = {plain}
                alt = re.match(r'^(\w+)\((\w+)\)$', plain)  # 'ca(cha)'
                if alt: bases = {alt.group(1), alt.group(2)}
                for base in bases:
                    index.setdefault(base, set()).add(variant)
    return index


def consonant_bases(onset, next_letter=''):
    """Onset letters/phoneme symbol -> engine consonant spellings."""
    if not onset: return ['']
    if onset.startswith('ph'): return ['p', 'ph']
    if onset.startswith('ch'): return ['c', 'ch']
    if onset.startswith('sh'): return ['sh']
    if onset.startswith('th'): return ['t', 'th']
    first = onset[0]
    if first == 'c': return ['s'] if next_letter in 'eiy' else ['k']
    return {'w': ['v'], 'f': ['p', 'ph'], 'z': ['jh'], 'q': ['k'], 'x': []}.get(first, [first])


def spelling_bases(word):
    """Onset consonants + first vowel letter (y is a vowel after the first letter)."""
    i = 0
    while i < len(word) and not (word[i] in VOWELS or (word[i] == 'y' and i > 0)): i += 1
    if i == len(word): return set()
    onset, v1 = word[:i], word[i]
    vowels = ['i' if v1 == 'y' else v1]
    if i + 1 < len(word) and word[i + 1] in VOWELS: vowels.append(word[i + 1])
    return {c + v for c in consonant_bases(onset, v1) for v in vowels}


def pronunciation_bases(word, cmu):
    out = set()
    for phones in cmu.get(word, []):
        onset = []
        for p in phones:
            sym = re.sub(r'\d', '', p)
            if sym in PHONE_VOWEL:
                cons = PHONE_CONS[onset[0]] if onset else ''
                out |= {c + v for c in consonant_bases(cons) for v in PHONE_VOWEL[sym]}
                break
            onset.append(sym)
    return out


def declare(display_name, syl_table, cmu):
    index = engine_index(syl_table)
    words, notes = {}, []
    for raw in display_name.split():
        word = re.sub(r'[^a-z]', '', raw.casefold())
        if re.search(r'\d', raw) or not word or not re.search(r'[aeiouy]', word):
            notes.append(f'no candidates for word {raw!r}'); continue
        bases = spelling_bases(word) | pronunciation_bases(word, cmu)
        if word not in cmu: notes.append(f'{raw!r} not in CMUdict; spelling only')
        tokens = sorted({t for b in bases for t in index.get(b, ())})
        words[raw] = tokens
    return {'rule': RULE, 'canonical_name': display_name, 'words': words, 'notes': notes}


def build(teams, syl_table):
    import cmudict
    cmu = cmudict.dict()
    return {key: declare(name, syl_table, cmu) for key, name in sorted(teams.items())}


if __name__ == '__main__':
    import argparse, sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    ap = argparse.ArgumentParser(); ap.add_argument('blind_inputs'); ap.add_argument('out')
    args = ap.parse_args()
    import ast
    src = (Path(__file__).resolve().parent / 'gd_engine.py').read_text()
    table = ast.literal_eval(re.search(r'^SYL = (\{.*?\n\})', src, re.S | re.M).group(1))
    teams = {}
    for row in json.loads(Path(args.blind_inputs).read_text()):
        for t in row['teams']: teams[row['sport'] + ':' + t['id']] = t['name']
    Path(args.out).write_text(json.dumps(build(teams, table), indent=2, sort_keys=True) + '\n')
    print(len(teams), 'teams declared')
