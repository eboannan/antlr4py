"""Regenerate bundled Unicode categories using Python with Unicode 15.0.0."""
import json
from pathlib import Path
import unicodedata

if unicodedata.unidata_version != '15.0.0':
    raise SystemExit('This data requires unicodedata 15.0.0 (Python 3.12)')
categories = {}
for code in range(0x110000):
    category = unicodedata.category(chr(code))
    ranges = categories.setdefault(category, [])
    if ranges and ranges[-1][1] == code - 1:
        ranges[-1][1] = code
    else:
        ranges.append([code, code])
target = Path(__file__).resolve().parents[1] / 'src/antlr4_generator/unicode15.json'
target.write_text(json.dumps({'unicode_version': '15.0.0', 'categories': categories}, separators=(',', ':'))+'\n')
