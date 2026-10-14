"""Agreement check of BT1.1-SYL-1 against Claude's prospective 2026-10-11 declarations.
The published candidates are copied verbatim from the validity log (picks C1-C4)."""
import ast, re, json
from pathlib import Path
import cmudict
from syllables import declare, engine_index
PUBLISHED = {  # word: published candidate syllables (log notation)
 'Baltimore':['ba','bo'],'Ravens':['re','ra'],'Atlanta':['a'],'Falcons':['pha','pa'],
 'Houston':['hu','hyu'],'Texans':['te'],'Tennessee':['te'],'Titans':['ti','te'],
 'Carolina':['ka'],'Hurricanes':['ha','hu'],'Philadelphia':['phi','pi'],'Flyers':['pha','pa'],
 'Vancouver':['va'],'Canucks':['ka'],'New':['nu'],'York':['yo'],'Rangers':['re','ra']}
src=(Path(__file__).parent/'gd_engine.py').read_text()
table=ast.literal_eval(re.search(r'^SYL = (\{.*?\n\})',src,re.S|re.M).group(1))
idx=engine_index(table); cmu=cmudict.dict(); rows=[]; full=0
for word,pub in PUBLISHED.items():
    want={t for b in pub for t in idx.get(b,())}
    got=set(declare(word,table,cmu)['words'].get(word,[]))
    ok=want<=got; full+=ok
    rows.append({'word':word,'published_engine_tokens':sorted(want),'rule_tokens':sorted(got),'covers_published':ok,'missing':sorted(want-got),'extra':sorted(got-want)})
print(json.dumps({'words':len(rows),'rule_covers_published':full,'rows':rows},indent=1))
