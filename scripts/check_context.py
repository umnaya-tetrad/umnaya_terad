#!/usr/bin/env python3
"""Validate portable SmartNote context without third-party packages or network access."""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

SKILLS = ('smartnote-pilot', 'smartnote-doc-sync', 'smartnote-preflight')
SKIP_DIRS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.pytest_cache', 'dist', 'build'}
TEXT_SUFFIXES = {'.md', '.html', '.json', '.jsonl', '.py', '.js', '.ts', '.tsx', '.yaml', '.yml', '.toml', '.txt', '.mmd'}
SECRET = re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{32,}|AIza[0-9A-Za-z_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')

class AssetLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ('href', 'src', 'poster') and value:
                self.links.append(value)

def local_target(root: Path, source: Path, raw: str):
    value = raw.strip()
    if not value or value.startswith(('#', '//')):
        return None
    if value.startswith('<') and value.endswith('>'):
        value = value[1:-1]
    parsed = urlsplit(value)
    if parsed.scheme:
        if len(parsed.scheme) == 1 or parsed.scheme == 'file':
            raise ValueError('machine-local file link')
        return None
    if '${' in value:
        return None
    if value.startswith('/'):
        raise ValueError('absolute local link')
    target = (source.parent / unquote(parsed.path)).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError('link escapes repository') from None
    return target

def validate(root: Path):
    errors = []
    count = 0
    files = [p for p in root.rglob('*') if p.is_file() and not any(x in SKIP_DIRS for x in p.relative_to(root).parts[:-1])]
    for p in files:
        rel = p.relative_to(root).as_posix()
        if p.name == '.env' or (p.name.startswith('.env.') and p.name != '.env.example'):
            errors.append(f'{rel}: environment secret file is not part of context')
        if p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = p.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:
            errors.append(f'{rel}: invalid UTF-8')
            continue
        if '\ufffd' in text:
            errors.append(f'{rel}: replacement character in text')
        if SECRET.search(text):
            errors.append(f'{rel}: possible credential; value intentionally omitted')
        if p.suffix.lower() == '.md':
            # Examples inside fenced code are not live document links.
            prose = re.sub(r'^\s*(```|~~~).*?^\s*\1\s*$', '', text, flags=re.M | re.S)
            links = re.findall(r'\[[^\]\n]*\]\(([^)\n]+)\)', prose)
        elif p.suffix.lower() == '.html':
            parser = AssetLinks()
            parser.feed(text)
            links = parser.links
        else:
            continue
        for link in links:
            try:
                target = local_target(root, p, link)
                if target is not None:
                    count += 1
                    if not target.exists():
                        errors.append(f'{rel}: missing target {link}')
            except ValueError as exc:
                errors.append(f'{rel}: {exc}: {link}')

    required = ['AGENTS.md', 'README.md', 'project-context/CURRENT_STATE.md',
                'project-context/AGENT_WORKFLOW.md', 'project-context/SOURCES.md',
                'project-context/pilot/PRODUCT.md', 'project-context/pilot/DECISIONS.md',
                'project-context/pilot/QUESTIONS.md', 'project-context/pilot/IMPLEMENTATION_PLAN.md']
    required += [f'.agents/skills/{name}/SKILL.md' for name in SKILLS]
    for name in required:
        p = root / name
        if not p.is_file() or not p.read_text(encoding='utf-8').strip():
            errors.append(f'{name}: required nonempty entry missing')
    for name in SKILLS:
        p = root / '.agents/skills' / name / 'SKILL.md'
        if not p.is_file():
            continue
        text = p.read_text(encoding='utf-8')
        if not text.startswith('---\n'):
            errors.append(f'{p.relative_to(root)}: missing skill frontmatter')
        else:
            header = text.split('---', 2)[1]
            match = re.search(r'^name:\s*(\S+)\s*$', header, re.M)
            if not match or match.group(1) != name:
                errors.append(f'{name}: skill name does not match folder')
            if not re.search(r'^description:\s*\S.+$', header, re.M):
                errors.append(f'{name}: missing description')
        if re.search(r'\bTODO\b|\[INSERT', text):
            errors.append(f'{name}: unfinished skill scaffold')
        agents = root / 'AGENTS.md'
        if agents.exists() and f'.agents/skills/{name}/SKILL.md' not in agents.read_text(encoding='utf-8'):
            errors.append(f'{name}: no explicit route from root AGENTS.md')

    for prefix, filename in [('R', 'DECISIONS.md'), ('Q', 'QUESTIONS.md')]:
        p = root / 'project-context/pilot' / filename
        if p.exists():
            ids = [int(n) for n in re.findall(r'^\| '+prefix+r'(\d+) \|', p.read_text(encoding='utf-8'), re.M)]
            if not ids or len(ids) != len(set(ids)) or sorted(ids) != list(range(1, max(ids, default=0)+1)):
                errors.append(f'{filename}: {prefix}-IDs must be unique and continuous from 1')
    return files, count, errors

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    files, count, errors = validate(root)
    if errors:
        print(f'FAIL: {len(errors)} issue(s)')
        for error in errors:
            print('- '+error)
        return 1
    print(f'PASS: {len(files)} files, {count} local links; entry points, 3 skills and decision registers are coherent.')
    print('Scope: structural validation only; code/doc semantics require smartnote-preflight.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
