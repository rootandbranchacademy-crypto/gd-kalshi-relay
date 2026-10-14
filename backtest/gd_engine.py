"""Gambler's Dharma scoring engine — method version GD-C1.0 (Claude cohort), frozen 2026-10-10.

Implements, as literally as the text allows, the techniques of S. Chokoisky, Gambler's Dharma (2017):
victory houses, SKY/PKY, D1 cusp contacts (+stolen cusps), D9 cusp contacts, D9 combos,
KP 1st/7th sublord scoring (Table 6.3), sublord array, MC navamsha syllable (lookup only;
name matching is declared by hand per game), fixed-star contacts, timing exclusions.
Sign convention: + favors the favorite (ascendant), - favors the underdog (descendant).
Every magnitude that the book leaves discretionary is an IMPLEMENTATION CHOICE and is marked [IC].
"""
import sys, math, datetime as dt
from zoneinfo import ZoneInfo
import os
if os.environ.get('GD_SWE_PATH'): sys.path.insert(0, os.environ['GD_SWE_PATH'])   # folder holding the built swisseph*.so
import swisseph as swe

EPHE = os.environ.get('GD_EPHE', './ephe')   # folder with sepl_18.se1, semo_18.se1, seas_18.se1, sefstars.txt
swe.set_ephe_path(EPHE)
swe.set_sid_mode(swe.SIDM_KRISHNAMURTI)
FLG = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

SIGNS = ['Ari', 'Tau', 'Gem', 'Can', 'Leo', 'Vir', 'Lib', 'Sco', 'Sag', 'Cap', 'Aqu', 'Pis']
SIGN_LORD = ['Ma', 'Ve', 'Me', 'Mo', 'Su', 'Me', 'Ve', 'Ma', 'Ju', 'Sa', 'Sa', 'Ju']
DASHA_SEQ = ['Ke', 'Ve', 'Su', 'Mo', 'Ma', 'Ra', 'Ju', 'Sa', 'Me']
DASHA_YRS = {'Ke': 7, 'Ve': 20, 'Su': 6, 'Mo': 10, 'Ma': 7, 'Ra': 18, 'Ju': 16, 'Sa': 19, 'Me': 17}
BODIES = {'Su': swe.SUN, 'Mo': swe.MOON, 'Ma': swe.MARS, 'Me': swe.MERCURY, 'Ju': swe.JUPITER,
          'Ve': swe.VENUS, 'Sa': swe.SATURN, 'Ra': swe.MEAN_NODE, 'Ur': swe.URANUS, 'Ne': swe.NEPTUNE,
          'Pl': swe.PLUTO, 'Ce': swe.CERES, 'Ch': swe.CHIRON}
NINE = ['Su', 'Mo', 'Ma', 'Me', 'Ju', 'Ve', 'Sa', 'Ra', 'Ke']
VISIBLE = ['Su', 'Mo', 'Ma', 'Me', 'Ju', 'Ve', 'Sa']
INVISIBLE = ['Ra', 'Ke', 'Ur', 'Ne', 'Pl', 'Ce', 'Ch', 'Uk']
MALEFICS = ['Su', 'Ma', 'Sa', 'Ra', 'Ke']
BENEFICS = ['Mo', 'Me', 'Ju', 'Ve']
EXALT = {'Su': 0, 'Mo': 1, 'Me': 5, 'Ve': 11, 'Ma': 9, 'Ju': 3, 'Sa': 6}
DEBIL = {'Su': 6, 'Mo': 7, 'Me': 11, 'Ve': 5, 'Ma': 3, 'Ju': 9, 'Sa': 0}
OWN = {'Su': [4], 'Mo': [3], 'Me': [2, 5], 'Ve': [1, 6], 'Ma': [0, 7], 'Ju': [8, 11], 'Sa': [9, 10]}
DIGBALA = {'Su': 10, 'Ma': 10, 'Mo': 4, 'Ve': 4, 'Me': 1, 'Ju': 1, 'Sa': 7}
FAV_VH, DOG_VH = {1, 3, 6, 10, 11}, {7, 9, 12, 4, 5}

SYL = {  # Table 7.1 (p.142), navamsha 1..9 per sign
 'Ari': ['cu', 'ce', 'co', 'la', 'li', 'lu', 'le', 'lo', 'a'],
 'Tau': ['i', 'u', 'e', 'o', 'va', 'vi', 'vu', 've', 'vo'],
 'Gem': ['ka', 'ki', 'ku', 'gha', 'nga/pha', 'cha', 'ke', 'ko', 'ha'],
 'Can': ['hi', 'hu', 'he', 'ho', 'da(retroflex)', 'di(r)', 'du(r)', 'de(r)', 'do(r)'],
 'Leo': ['ma', 'mi', 'mu', 'me', 'mo', 'ta(r)', 'ti(r)', 'tu(r)', 'te(r)'],
 'Vir': ['to(r)', 'pa', 'pi', 'pu', 'da(r)', 'na(r)', 'tha(r)', 'pe', 'po'],
 'Lib': ['ra', 'ri', 'ru', 're', 'ro', 'ta', 'ti', 'tu', 'te'],
 'Sco': ['to', 'na', 'ni', 'nu', 'ne', 'no', 'ya', 'yi', 'yu'],
 'Sag': ['ye', 'yo', 'ba', 'bi', 'bu', 'dha', 'bha', 'dha(r)', 'be'],
 'Cap': ['bo', 'ja/sha', 'ji/shi', 'ju/shu', 'je/she', 'jo/sho', 'jha/sha', 'ga', 'gi'],
 'Aqu': ['gu', 'ge', 'go', 'sa', 'si', 'su', 'se', 'so', 'da'],
 'Pis': ['di', 'du', 'kha/jha', 'nga', 'tha', 'de', 'do', 'ca(cha)', 'ci(chi)'],
}

# Fixed stars with a scored win/loss effect in ch.8. (swe name or fixed book longitude, effect, tier)
STARS = [
 ('Pollux', 'Pollux', +1, 2), ('Regulus', 'Regulus', +1, 2), ('Zuben Elgenubi', 'Zuben Elgenubi', +1, 2),
 ('Vega', 'Vega', +1, 2), ('Betelgeuse', 'Betelgeuse', -1, 2), ('Spica', 'Spica', -1, 2),
 ('Alcyone', 'Alcyone', +1, 1), ('Altair', 'Altair', +1, 1), ('Zosma', 'Zosma', -1, 1),
 ('Denebola', 'Denebola', -1, 1),
 ('Mrigashira pt (book 29Tau45)', 59.75, +1, 1), ('Shatabhisha pt (book 17Aqu45)', 317.75, +1, 1),
]
HYADES = (41.0, 43.0)  # book: 11-13 Taurus, first-tier +
WASAT = 'Wasat'       # "like Saturn": - on 1/7, + on 4/10


def norm(x): return x % 360.0
def sgn(lon): return int(norm(lon) // 30)
def fmt(lon):
    lon = norm(lon); s = int(lon // 30); d = lon - 30 * s; dd = int(d); m = int(round((d - dd) * 60))
    if m == 60: dd += 1; m = 0
    return f"{dd:02d}:{m:02d} {SIGNS[s]}"
def sep(a, b):
    d = abs(norm(a) - norm(b)); return min(d, 360 - d)
def nak_lord(lon): return DASHA_SEQ[int(norm(lon) // (360 / 27)) % 9]
def sub_lord(lon):
    span = 360 / 27; lon = norm(lon); n = int(lon // span); pos = lon - n * span
    start = n % 9; acc = 0.0
    for k in range(9):
        p = DASHA_SEQ[(start + k) % 9]; w = span * DASHA_YRS[p] / 120.0
        if pos < acc + w - 1e-12: return p
        acc += w
    return DASHA_SEQ[(start + 8) % 9]


def jd_from_local(y, mo, d, h, mi, s, tz):
    t = dt.datetime(y, mo, d, h, mi, int(s), tzinfo=ZoneInfo(tz)) if isinstance(tz, str) else \
        dt.datetime(y, mo, d, h, mi, int(s), tzinfo=dt.timezone(dt.timedelta(hours=tz)))
    u = t.astimezone(dt.timezone.utc)
    return swe.julday(u.year, u.month, u.day, u.hour + u.minute / 60 + u.second / 3600), u


def chart(jd, lat, lon):
    P = {}; R = {}
    for k, b in BODIES.items():
        x, _ = swe.calc_ut(jd, b, FLG); P[k] = x[0]; R[k] = x[3] < 0
    P['Ke'] = norm(P['Ra'] + 180); R['Ke'] = True; R['Ra'] = True
    P['Uk'] = norm(P['Su'] - 30); R['Uk'] = False   # Upaketu = Sun - 30 deg (matches every printed chart)
    cusps, ascmc = swe.houses_ex(jd, lat, lon, b'P', swe.FLG_SIDEREAL)
    return {'P': P, 'R': R, 'cusps': list(cusps), 'asc': ascmc[0], 'mc': ascmc[1],
            'ayan': swe.get_ayanamsa_ut(jd), 'jd': jd}


def ws_house(lon, asc): return (sgn(lon) - sgn(asc)) % 12 + 1
def plac_house(lon, cusps):
    for i in range(12):
        a = cusps[i]; b = cusps[(i + 1) % 12]
        if norm(lon - a) < norm(b - a): return i + 1
    return 12


def victory_houses(c, on_cusp=()):
    P, R, asc = c['P'], c['R'], c['asc']; rows = []; tot = 0.0
    for p in ['Su', 'Ma', 'Sa', 'Me', 'Ju', 'Ve', 'Mo']:
        h = ws_house(P[p], asc); s = sgn(P[p])
        side = +1 if h in FAV_VH else (-1 if h in DOG_VH else 0)
        if side == 0: continue
        if p in on_cusp:   # [IC] p.72: a planet within orb of a scored D1 cusp is judged by the cusp table, not as a victory-house planet
            rows.append((p, h, 0.0, 'on a scored D1 cusp — judged by cusp table only (p.72)')); continue
        ex = EXALT[p] == s; deb = DEBIL[p] == s; own = s in OWN[p]; dig = DIGBALA[p] == h; ret = R[p]
        if p in MALEFICS:
            pts = 2.0 if deb else 2.5 + 0.5 * (ex + own + dig)
            rows.append((p, h, side * pts, f"malefic{' exalted' if ex else ''}{' debil' if deb else ''}{' own-sign' if own else ''}{' digbala' if dig else ''}"))
            tot += side * pts
        elif p in ('Me', 'Ju', 'Ve'):
            if ex or ret:   # [IC] strict reading p.135: benefic must be exalted or retrograde
                extra = (own + dig + (ex and ret))
                pts = 2.0 if deb else 2.5 + 0.5 * extra
                rows.append((p, h, side * pts, f"benefic eligible ({'exalted' if ex else ''}{' retro' if ret else ''}){' own-sign' if own else ''}{' digbala' if dig else ''}"))
                tot += side * pts
            elif own or nak_lord(P[p]) == p:
                rows.append((p, h, 0.0, "benefic in own sign/nakshatra — discretionary, UNSCORED [IC]"))
        elif p == 'Mo':
            ph = norm(P['Mo'] - P['Su'])
            if ex or own or abs(ph - 180) < 45:
                rows.append((p, h, 0.0, f"Moon strong-ish (phase {ph:.0f} deg{' exalted' if ex else ''}{' own' if own else ''}) — author normally omits; UNSCORED [IC]"))
    hr, hk = ws_house(P['Ra'], asc), ws_house(P['Ke'], asc)
    rows.append(('Ra/Ke', f"{hr}/{hk}", 0.0, "nodes always offset (p.35 fn) — net 0"))
    return tot, rows


def kartari(c):
    P, asc = c['P'], c['asc']; out = []; tot = 0.0
    occ = {h: [p for p in NINE if ws_house(P[p], asc) == h] for h in range(1, 13)}
    for side, (ha, hb), label in ((+1, (12, 2), 'favorite'), (-1, (6, 8), 'underdog')):
        A, B = occ[ha], occ[hb]
        benA = [p for p in A if p in BENEFICS]; benB = [p for p in B if p in BENEFICS]
        hard = [p for p in A + B if p in ('Su', 'Ma', 'Sa')]; nodes = [p for p in A + B if p in ('Ra', 'Ke')]
        hardA = [p for p in A if p in ('Su', 'Ma', 'Sa')]; hardB = [p for p in B if p in ('Su', 'Ma', 'Sa')]
        malA = [p for p in A if p in MALEFICS]; malB = [p for p in B if p in MALEFICS]
        if benA and benB:  # SKY
            nm = len(hard) + len(nodes)
            if nm == 0: pts = 8
            elif nm >= 2 and len(hard) >= 1 and (len(hard) >= 2 or nodes): pts = 0 if len(hard) >= 2 else 4
            elif hard == ['Su'] or (not hard and nodes): pts = 6
            else: pts = 4
            out.append((label, f"SKY h{ha}:{A} h{hb}:{B}; marring hard={hard} nodes={nodes}", side * pts)); tot += side * pts
        elif malA and malB and not (benA or benB):  # PKY, no benefic relief
            if hardA and hardB: pts = 6 + (1 if nodes else 0)
            else: pts = 3   # node-only on one flank = half effect (p.38)
            out.append((label, f"PKY h{ha}:{A} h{hb}:{B}", -side * pts)); tot += -side * pts
        elif malA and malB:
            out.append((label, f"mixed hemming h{ha}:{A} h{hb}:{B} — no rule, UNSCORED", 0.0))
    return tot, out


def cusp_effect_d1(p, axis, retro):
    """axis in '17','410','612'. returns sign for the team owning the cusp, or None if unscored."""
    T = {'Su': (-1, -1, -1), 'Mo': (-1, -1, -1), 'Ma': (1, -1, 1), 'Ra': (1, 1, 1), 'Ju': (1, 1, 1),
         'Sa': (-1, 1, 1), 'Me': (None, None, 1), 'Ke': (-1, -1, -1), 'Ve': (1, 1, 1),
         'Pl': (-1, 1, -1), 'Uk': (-1, -1, -1)}
    i = {'17': 0, '410': 1, '612': 2}[axis]
    if p in T: return T[p][i]
    if p in ('Ur', 'Ce', 'Ch'): return -1 if retro else 1
    if p == 'Ne': return 1 if retro else -1
    return None


def d1_pts(p, orb):
    base = 9 if p in VISIBLE else 7
    if p == 'Mo': base = 7       # [IC] "not as strong as the other planets"
    if p == 'Ve': base = 8       # [IC] "mild"
    lim = 2.5 if p in VISIBLE else 2.0
    if orb <= 0.5: base += 1     # [IC] author gave +1 for a very tight orb (p.136)
    elif orb > lim - 0.5: base -= 1   # [IC] outer edge "a bit less" (p.132)
    return base


def cusp_role(n, c):
    """Return (owner_side, axis, note, factor) for Placidus cusp n after stolen-cusp logic, or None."""
    asc = c['asc']; H = ws_house(c['cusps'][n - 1], asc)
    power = {1: (+1, '17'), 7: (-1, '17'), 10: (+1, '410'), 4: (-1, '410'), 6: (+1, '612'), 12: (-1, '612')}
    if n in power:
        if H == n: return power[n] + ('', 1.0)
        if n == 6 and H == 7: return (-1, '17', 'STOLEN power-to-power 6th cusp in WS 7th', 1.0)
        if n == 12 and H == 1: return (+1, '17', 'STOLEN power-to-power 12th cusp in WS 1st', 1.0)
        if H in (3, 5, 9, 11): return power[n] + (f'STOLEN power-to-neutral (cusp {n} in WS {H}) x0.5 [IC]', 0.5)
        if H in power: return power[H] + (f'STOLEN cusp {n} in WS {H}', 1.0)
        return None
    else:  # 3,5,9,11 (and 2,8 never used)
        if n in (3, 5, 9, 11) and H in power:
            return power[H] + (f'STOLEN neutral-to-power (cusp {n} in WS {H})', 1.0)
        return None


def d1_cusps(c):
    P, R = c['P'], c['R']; out = []; tot = 0.0; near = []
    for n in range(1, 13):
        role = cusp_role(n, c)
        if role is None: continue
        side, axis, note, fac = role
        for p in VISIBLE + INVISIBLE:
            if p == 'Ke': continue   # node axis taken as one signal via Rahu (p.61)
            orb = sep(P[p], c['cusps'][n - 1]); lim = 2.5 if p in VISIBLE else 2.0
            if orb <= lim:
                eff = cusp_effect_d1(p, axis, R[p])
                if p == 'Ra':
                    # Rahu + on its cusp == Ketu - on the opposite cusp; count once
                    pts = d1_pts(p, orb) * fac; val = side * pts
                    out.append((n, p, orb, axis, val, f"Rahu on cusp {n} (Ketu opposite) {note}")); tot += val
                elif eff is None:
                    out.append((n, p, orb, axis, 0.0, f"Mercury on {axis} axis — author does not use; UNSCORED {note}"))
                else:
                    pts = d1_pts(p, orb) * fac; val = side * eff * pts
                    out.append((n, p + ('R' if R[p] and p not in ('Ra', 'Ke') else ''), orb, axis, val, note)); tot += val
            elif orb <= 3.0:
                near.append((n, p, orb))
    return tot, out, near


def d9(lon): return norm(lon * 9.0)


def d9_cusps(c):
    P, R = c['P'], c['R']; a9 = d9(c['asc']); out = []; tot = 0.0
    eff = {'Mo': -1, 'Ma': -1, 'Ra': 1, 'Ju': 1, 'Sa': -1, 'Me': 1, 'Ke': -1, 'Ve': -1, 'Su': -1, 'Pl': -1, 'Uk': -1}
    pts = {'Su': 14, 'Mo': 14, 'Ma': 18, 'Me': 16, 'Ju': 18, 'Ve': 14, 'Sa': 17}   # [IC] within the book's 14-18
    for side, cusp, nm in ((+1, a9, 'D9-1st'), (-1, norm(a9 + 180), 'D9-7th')):
        for p in VISIBLE + INVISIBLE:
            if p == 'Ke': continue
            orb = sep(d9(P[p]), cusp); lim = 2.5 if p in VISIBLE else 2.0
            if orb <= lim:
                if p in eff: e = eff[p]
                elif p == 'Ur': e = -1 if R[p] else 1
                elif p == 'Ne': e = 1 if R[p] else -1
                elif p == 'Ch' and R[p]: e = -1
                else: e = None
                if e is None:
                    out.append((nm, p, orb, 0.0, 'no D9 rule stated (direct Chiron / Ceres) — UNSCORED'))
                else:
                    v = side * e * pts.get(p, 13); out.append((nm, p + ('R' if R[p] and p not in ('Ra',) else ''), orb, v, '')); tot += v
    return tot, out, a9


def d9_combos(c):
    P = c['P']; a9 = d9(c['asc']); out = []; tot = 0.0
    T = {frozenset(('Su', 'Ke')): -1, frozenset(('Ve', 'Ke')): 1, frozenset(('Su', 'Ju')): -1,
         frozenset(('Mo', 'Ra')): 1, frozenset(('Mo', 'Sa')): -1, frozenset(('Ve', 'Ra')): -1}
    for side, hs, nm in ((+1, sgn(a9), 'D9 1st house'), (-1, (sgn(a9) + 6) % 12, 'D9 7th house')):
        inh = [p for p in NINE if sgn(d9(P[p])) == hs]
        for k, e in T.items():
            if k <= set(inh):
                v = side * e * 5; out.append((nm, '+'.join(sorted(k)), v, f"occupants {inh}")); tot += v
    return tot, out


def significators(c):
    P, cusps = c['P'], c['cusps']; rows = []
    for n in range(1, 13):
        owner = SIGN_LORD[sgn(cusps[n - 1])]
        A = [owner]
        B = [p for p in NINE if nak_lord(P[p]) == owner]
        C = [p for p in NINE if plac_house(P[p], cusps) == n]
        D = [p for p in NINE if nak_lord(P[p]) in C]
        rows.append({'n': n, 'A': A, 'B': B, 'C': C, 'D': D})
    return rows


def sublord_score(planet, rows):
    tot = 0.0; detail = []
    for r in rows:
        n = r['n']; pop = {k for k in 'ABCD' if r[k]}
        if pop == {'A'}: w = {'A': 4}
        elif pop == {'A', 'B'}: w = {'A': 2, 'B': 4}
        elif pop == {'A', 'C'}: w = {'A': 1, 'C': 3}
        else: w = {'A': 1, 'B': 2, 'C': 3, 'D': 4}
        pol = 1.0 if n in (1, 3, 6, 10, 11) else (0.5 if n == 2 else -1.0)
        for k in 'DCBA':
            if planet in r[k]:
                v = pol * w.get(k, 0); tot += v; detail.append(f"h{n}{k}{v:+g}")
    return tot, detail


def sublords(c):
    rows = significators(c); s1 = sub_lord(c['cusps'][0]); s7 = sub_lord(c['cusps'][6])
    v1, d1 = sublord_score(s1, rows); v7, d7 = sublord_score(s7, rows)
    diff = v1 if s1 == s7 else v1 - v7
    return diff, {'s1': s1, 'v1': v1, 'd1': d1, 's7': s7, 'v7': v7, 'd7': d7, 'same': s1 == s7, 'rows': rows}


def sublord_array(c):
    subs = [sub_lord(x) for x in c['cusps']]
    hs = [ws_house(c['P'][s], c['asc']) for s in subs]   # [IC] whole-sign residence, per the book's own example
    fav = sum(h in (1, 3, 6, 10, 11) for h in hs); dog = sum(h in (4, 5, 7, 9, 12) for h in hs); neu = 12 - fav - dog
    # [IC] full array = none on the opposing side and at most 2 of 12 in the neutral 2nd/8th (book example: 11 + 1 neutral)
    val = 7 if (dog == 0 and fav >= 10) else (-7 if (fav == 0 and dog >= 10) else 0)
    t = [ws_house(c['P'][subs[i]], c['asc']) for i in (0, 6, 9)]
    v3 = 'fav' if all(h in (1, 3, 6, 8, 10, 11) for h in t) else ('dog' if all(h in (2, 4, 5, 7, 9, 12) for h in t) else 'split')
    return val, {'subs': subs, 'houses': hs, 'fav': fav, 'dog': dog, 'neutral': neu, 'v1710': v3}


def mc_syllable(c):
    mc = c['cusps'][9]; s = sgn(mc); n = int((norm(mc) - 30 * s) // (10 / 3)); return SYL[SIGNS[s]][n], n + 1


def star_lon(name, jd):
    if isinstance(name, (int, float)): return float(name)
    x = swe.fixstar2_ut(name, jd, swe.FLG_SWIEPH | swe.FLG_SIDEREAL)
    return x[0][0]


def stars(c):
    P, asc, jd = c['P'], c['asc'], c['jd']; out = []; tot = 0.0
    s1 = sgn(asc)
    lords = {'L1': SIGN_LORD[s1], 'L10': SIGN_LORD[(s1 + 9) % 12], 'L7': SIGN_LORD[(s1 + 6) % 12], 'L4': SIGN_LORD[(s1 + 3) % 12]}
    pts_side = {'L1': +1, 'L10': +1, 'L7': -1, 'L4': -1}
    if lords['L4'] == lords['L1']: lords.pop('L4')      # p.162 dual-lordship rule
    if 'L10' in lords and lords['L10'] == lords['L7']: lords.pop('L10')   # [IC] mirror case
    cusp_pts = {'cusp1': (c['cusps'][0], +1, '17'), 'cusp10': (c['cusps'][9], +1, '410'),
                'cusp7': (c['cusps'][6], -1, '17'), 'cusp4': (c['cusps'][3], -1, '410')}
    def val(tier, orb): return (8 if orb <= 0.5 else 7) if tier == 2 else 3
    for nm, key, eff, tier in STARS:
        L = star_lon(key, jd)
        for cn, (cl, side, ax) in cusp_pts.items():
            o = sep(L, cl)
            if o <= 1.0:
                v = side * eff * val(tier, o); out.append((nm, fmt(L), cn, o, v, f"tier {tier}")); tot += v
        if nm == 'Spica': continue   # lords: "more research needed" — unscored
        if nm == 'Vega': continue    # "no graha ever transits this star" — cusps only [IC]
        hits = []; seen = set()
        for ln in ('L1', 'L7', 'L10', 'L4'):
            if ln not in lords: continue
            pl = lords[ln]
            if pl in seen: continue          # one planet counted once, in its senior role
            o = sep(L, P[pl])
            if o <= 1.0: hits.append((ln, pl, o)); seen.add(pl)
        sides = {pts_side[h[0]] for h in hits}
        if len(sides) == 2:   # rulers of both teams on the same star: lagna lord outranks 10th/4th lord; else closer wins (p.162-164)
            prim = [h for h in hits if h[0] in ('L1', 'L7')]
            pool = prim if len({pts_side[h[0]] for h in prim}) == 1 else (prim or hits)
            win = min(pool, key=lambda h: h[2]); note = ' (both sides on star: senior/closer ruler taken)'
            hits = [win]
        else: note = ''
        for ln, pl, o in hits:
            v = pts_side[ln] * eff * val(tier, o); out.append((nm, fmt(L), f"{ln}={pl}", o, v, f"tier {tier}{note}")); tot += v
    for cn, (cl, side, ax) in cusp_pts.items():
        if HYADES[0] <= norm(cl) <= HYADES[1]:
            out.append(('Hyades', '11-13 Tau', cn, 0.0, side * 3, 'tier 1')); tot += side * 3
        o = sep(star_lon(WASAT, jd), cl)
        if o <= 1.0:
            e = -1 if ax == '17' else 1; v = side * e * 6; out.append(('Wasat', fmt(star_lon(WASAT, jd)), cn, o, v, 'like Saturn, a touch less [IC 6]')); tot += v
    return tot, out


def graha_yuddha(c):
    P, asc = c['P'], c['asc']; s1 = sgn(asc); out = []
    fav = {SIGN_LORD[s1], SIGN_LORD[(s1 + 9) % 12]}; dog = {SIGN_LORD[(s1 + 6) % 12], SIGN_LORD[(s1 + 3) % 12]}
    five = ['Ma', 'Me', 'Ju', 'Ve', 'Sa']
    for i, a in enumerate(five):
        for b in five[i + 1:]:
            if sep(P[a], P[b]) <= 1.0 and ({a, b} & (fav | dog)):
                out.append(f"{a}-{b} within {sep(P[a], P[b]):.2f} deg (rulers involved) — supplemental, UNSCORED")
    return out


def evaluate(jd, lat, lon):
    c = chart(jd, lat, lon); res = {'chart': c}
    res['sky'], res['sky_rows'] = kartari(c)
    res['d1'], res['d1_rows'], res['d1_near'] = d1_cusps(c)
    on = {r[1].rstrip('R') if r[1] not in ('Ra',) else 'Ra' for r in res['d1_rows'] if r[4] != 0}
    res['vh'], res['vh_rows'] = victory_houses(c, on)
    res['d9'], res['d9_rows'], res['a9'] = d9_cusps(c)
    res['combo'], res['combo_rows'] = d9_combos(c)
    res['sub'], res['sub_info'] = sublords(c)
    res['arr'], res['arr_info'] = sublord_array(c)
    res['star'], res['star_rows'] = stars(c)
    res['syl'] = mc_syllable(c)
    res['yuddha'] = graha_yuddha(c)
    res['total'] = res['vh'] + res['sky'] + res['d1'] + res['d9'] + res['combo'] + res['sub'] + res['arr'] + res['star']
    return res


def timing_flags(jd):
    out = []
    for nm, b in BODIES.items():
        if nm in ('Su', 'Mo', 'Ra'): continue
        s0 = swe.calc_ut(jd - 3, b, FLG)[0][3]; s1 = swe.calc_ut(jd + 3, b, FLG)[0][3]
        if s0 * s1 < 0:
            lo, hi = jd - 3, jd + 3
            for _ in range(40):
                mid = (lo + hi) / 2
                if swe.calc_ut(mid, b, FLG)[0][3] * s0 > 0: lo = mid
                else: hi = mid
            out.append(f"{nm} stations within +/-3 d (station at JD {lo:.3f}, {(lo - jd):+.2f} d from event)")
    sun = swe.calc_ut(jd, swe.SUN, FLG)[0][0] % 30
    if sun >= 29 or sun < 1: out.append(f"Sun at {sun:.2f} deg of sign — sankranti zone")
    for fn, lab in ((swe.sol_eclipse_when_glob, 'solar'), (swe.lun_eclipse_when, 'lunar')):
        for back in (False, True):
            try:
                r = fn(jd, swe.FLG_SWIEPH, 0, back); t = r[1][0]
                if abs(t - jd) <= 3: out.append(f"{lab} eclipse {t - jd:+.2f} d from event")
            except Exception as e:
                out.append(f"eclipse check error {lab}: {e}")
    return out


def report(res, short=False):
    c = res['chart']; L = []
    L.append(f"Asc {fmt(c['asc'])} | MC {fmt(c['cusps'][9])} | ayanamsha {c['ayan']:.4f} | D9 asc {fmt(res['a9'])}")
    L.append("Cusps: " + ', '.join(f"{i + 1}:{fmt(x)}" for i, x in enumerate(c['cusps'])))
    order = ['Su', 'Mo', 'Ma', 'Me', 'Ju', 'Ve', 'Sa', 'Ra', 'Ke', 'Ur', 'Ne', 'Pl', 'Ce', 'Ch', 'Uk']
    L.append("D1: " + ', '.join(f"{p}{'R' if c['R'][p] and p not in ('Ra', 'Ke') else ''} {fmt(c['P'][p])}(h{ws_house(c['P'][p], c['asc'])})" for p in order))
    L.append("D9: " + ', '.join(f"{p} {fmt(d9(c['P'][p]))}" for p in order))
    L.append(f"VICTORY HOUSES {res['vh']:+.1f}: " + '; '.join(f"{a} h{b} {v:+.1f} [{n}]" for a, b, v, n in res['vh_rows']))
    L.append(f"SKY/PKY {res['sky']:+.1f}: " + ('; '.join(f"{a}: {b} => {v:+.1f}" for a, b, v in res['sky_rows']) or 'none'))
    L.append(f"D1 CUSPS {res['d1']:+.1f}: " + ('; '.join(f"cusp{n} {p} orb {o:.2f} axis {ax} => {v:+.1f} {nt}" for n, p, o, ax, v, nt in res['d1_rows']) or 'none'))
    if res['d1_near']: L.append("   near-miss (orb<=3): " + '; '.join(f"cusp{n} {p} {o:.2f}" for n, p, o in res['d1_near'] if cusp_role(n, c)))
    L.append(f"D9 CUSPS {res['d9']:+.1f}: " + ('; '.join(f"{nm} {p} orb {o:.2f} => {v:+.1f} {nt}" for nm, p, o, v, nt in res['d9_rows']) or 'none'))
    L.append(f"D9 COMBOS {res['combo']:+.1f}: " + ('; '.join(f"{nm} {k} => {v:+.1f} ({nt})" for nm, k, v, nt in res['combo_rows']) or 'none'))
    s = res['sub_info']
    L.append(f"SUBLORDS {res['sub']:+.1f}: 1st-cusp sub {s['s1']} = {s['v1']:+g} [{' '.join(s['d1'])}] vs 7th-cusp sub {s['s7']} = {s['v7']:+g} [{' '.join(s['d7'])}]{' (same sublord: score taken for favorite)' if s['same'] else ''}")
    a = res['arr_info']
    L.append(f"SUBLORD ARRAY {res['arr']:+.1f}: subs {a['subs']} in WS houses {a['houses']} (fav {a['fav']}/dog {a['dog']}/neutral {a['neutral']}); 1/7/10 variant: {a['v1710']} (unscored)")
    L.append(f"STARS {res['star']:+.1f}: " + ('; '.join(f"{nm} {lo} on {cn} orb {o:.2f} => {v:+.1f} ({t})" for nm, lo, cn, o, v, t in res['star_rows']) or 'none'))
    L.append(f"MC SYLLABLE: {res['syl'][0]} (navamsha {res['syl'][1]}) — name match scored by hand")
    if res['yuddha']: L.append("GRAHA YUDDHA: " + '; '.join(res['yuddha']))
    L.append(f"TOTAL before syllable: {res['total']:+.1f}")
    return '\n'.join(L)


if __name__ == '__main__':
    pass
