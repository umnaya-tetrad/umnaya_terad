"""Проверка целостности локального исследовательского запуска, без сети."""
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parent
sources = {}
claims = []
errors = []
for path in root.glob('sources-*.jsonl'):
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row['id'] in sources:
            errors.append('Duplicate source: ' + row['id'])
        sources[row['id']] = row
for path in root.glob('claims-*.jsonl'):
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if line.strip():
            claims.append(json.loads(line))
for row in claims:
    for sid in row['source_ids']:
        if sid not in sources:
            errors.append('Unresolved claim source: ' + sid)
report = root / 'report.md'
if not report.exists():
    errors.append('Missing report.md')
for path in [report, *root.glob('appendices/*.md')]:
    if not path.exists():
        continue
    body = path.read_text(encoding='utf-8-sig')
    cited = set(re.findall(r'\[#([^\]\s]+)\]', body))
    for sid in cited:
        if sid not in sources:
            errors.append(f'{path.name}: unresolved citation {sid}')
    if path == report:
        if not cited:
            errors.append('No citations in report')
        refs = body.split('## Sources', 1)
        if len(refs) != 2:
            errors.append('Missing Sources heading')
        else:
            for sid in cited:
                if f'[#{sid}]' not in refs[1]:
                    errors.append('Missing reference: ' + sid)
    for target in re.findall(r'\]\(([^)]+)\)', body):
        if '://' in target or target.startswith('mailto:') or target.startswith('#'):
            continue
        if not (path.parent / target.split('#')[0]).exists():
            errors.append(f'{path.name}: missing local link {target}')
print(json.dumps({'sources': len(sources), 'claims': len(claims), 'errors': errors}, ensure_ascii=False, indent=2))
raise SystemExit(bool(errors))
