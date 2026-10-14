import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STUDY = json.loads((ROOT / 'study.json').read_text())

def utc(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)

def save(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')
    tmp.replace(path)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate_engine():
    assert digest(ROOT / 'gd_engine.py') == STUDY['engine_sha256'], 'Frozen engine changed'
    import gd_engine as e
    for name, t, lat, lon, want in [
        ('BALATL', (2026, 10, 12, 0, 20), 33.7554, -84.4008, -26.5),
        ('HOUTEN', (2026, 10, 11, 17, 0), 36.1665, -86.7713, -20.5),
    ]:
        y, m, d, h, minute = t
        got = e.evaluate(e.swe.julday(y, m, d, h + minute / 60), lat, lon)['total']
        assert got == want, f'{name}: {got} != {want}'
    return e
