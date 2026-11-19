"""Verify this frozen photo package offline with Python 3.9+ standard library."""
import hashlib
import json
import re
import struct
import sys
from collections import Counter
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
ORDER_SHA256 = '83f4ac8edfc81b7bc77ab50975108ecdf6007697f703c0dfedd9686a870eeadf'
EXPECTED_GROUPS = {'one_photo_one_task': 20, 'one_photo_many_tasks': 48,
                   'one_task_two_photos': 4, 'mixed_two_photos': 4}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def local_file(relative):
    require(isinstance(relative, str), 'Path must be a string')
    path = PurePosixPath(relative)
    require(relative == path.as_posix() and not path.is_absolute()
            and not any(p in ('..', '.') for p in path.parts)
            and '\\' not in relative and ':' not in relative,
            'Non-portable path: ' + relative)
    resolved = (ROOT / relative).resolve(strict=True)
    require(ROOT in resolved.parents and resolved.is_file(), 'Path escapes package: ' + relative)
    return resolved


def dimensions(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        require(data[12:16] == b'IHDR', 'Invalid PNG header')
        return struct.unpack('>II', data[16:24])
    require(data.startswith(b'\xff\xd8'), 'Expected original PNG or JPEG')
    pos = 2
    while pos < len(data):
        require(data[pos] == 255, 'Invalid JPEG marker')
        while data[pos] == 255:
            pos += 1
        marker = data[pos]
        pos += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        require(marker != 0xDA, 'JPEG dimensions not found before scan')
        length = struct.unpack('>H', data[pos:pos + 2])[0]
        require(length >= 2, 'Invalid JPEG segment')
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height, width = struct.unpack('>HH', data[pos + 3:pos + 7])
            return width, height
        pos += length
    raise ValueError('JPEG dimensions missing')


def main():
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    require(manifest['schema_version'] == 'smartnote-pilot-eval-inputs/1.0', 'Unknown schema')
    cases = manifest['cases']
    require(len(cases) == 76, 'Expected exactly 76 cases')
    require(len({c['case_id'] for c in cases}) == 76, 'Duplicate case ID')
    require({c['input_id'] for c in cases} == {f'R{i:03d}' for i in range(1, 77)}, 'Input IDs differ')
    order = '\n'.join(c['case_id'] for c in cases).encode('ascii')
    require(digest(order) == ORDER_SHA256, 'Frozen case order changed')
    require(dict(Counter(c['format_group'] for c in cases)) == EXPECTED_GROUPS, 'Group counts differ')
    paths, hashes, total_bytes = [], [], 0
    for order_index, case in enumerate(cases, 1):
        require(case['input_order'] == order_index, 'Input order index differs')
        require(re.fullmatch(r'[A-Z0-9_]+', case['case_id']), 'Invalid case ID')
        photos = case['images']
        require(len(photos) in (1, 2), 'Unexpected bundle size')
        require(case['joint_evaluation_required'] == (len(photos) == 2), 'Bundle flag differs')
        for photo_index, photo in enumerate(photos, 1):
            relative = photo['path']
            require(photo['photo_index'] == photo_index, 'Photo order differs')
            require(relative in (f"inputs/{case['case_id']}/photo_{photo_index:02d}.png",
                                 f"inputs/{case['case_id']}/photo_{photo_index:02d}.jpg"), 'Photo path differs')
            path = local_file(relative)
            data = path.read_bytes()
            require(digest(data) == photo['sha256'], 'SHA256 mismatch: ' + relative)
            require(len(data) == photo['bytes'], 'Byte count mismatch: ' + relative)
            width, height = dimensions(data)
            require((width, height) == (photo['width'], photo['height']), 'Geometry mismatch: ' + relative)
            require(len(data) <= 8000000 and width * height <= 36000000 and min(width, height) >= 32,
                    'Current upload limits exceeded: ' + relative)
            require(photo['source_attribution'], 'Attribution missing: ' + relative)
            paths.append(relative)
            hashes.append(photo['sha256'])
            total_bytes += len(data)
    require(len(paths) == len(set(paths)) == 84, 'Expected 84 distinct attachment paths')
    require(len(set(hashes)) == 83, 'Expected 83 distinct image contents')
    require(total_bytes == 69642405, 'Total original image bytes differ')
    actual = {p.relative_to(ROOT).as_posix() for p in (ROOT / 'inputs').rglob('*') if p.is_file()}
    require(actual == set(paths), 'Unexpected or missing input files')
    summary = manifest['summary']
    require((summary['cases'], summary['attachments'], summary['unique_sha256'], summary['bytes'])
            == (76, 84, 83, 69642405), 'Manifest summary differs')
    require(summary['format_groups'] == EXPECTED_GROUPS, 'Manifest group summary differs')
    require({r['path'] for r in manifest['reference_files']}
            == {'reference/truth.json', 'reference/truth_errata.json'}, 'Reference file list differs')
    for reference in manifest['reference_files']:
        require(digest(local_file(reference['path']).read_bytes()) == reference['sha256'],
                'Reference SHA256 mismatch: ' + reference['path'])
    truth = json.loads(local_file('reference/truth.json').read_text(encoding='utf-8'))
    require([c['case_id'] for c in truth['cases']] == [c['case_id'] for c in cases], 'Reference order differs')
    units = [u for c in truth['cases'] for u in c['units']]
    require(len(units) == 178 and all(len(c['units']) == c['expected_unit_count'] for c in truth['cases']),
            'Expected 178 frozen reference unit appearances')
    errata = json.loads(local_file('reference/truth_errata.json').read_text(encoding='utf-8'))
    require({u['truth_id'] for u in errata['excluded_units']}
            == {'B_N07__h', 'E_N07__h', 'U_N07__h'}, 'Known N07 errata differs')
    for unit in errata['excluded_units']:
        require(digest(local_file(unit['source_image']).read_bytes()) == unit['source_sha256'],
                'Errata image hash differs')
    print('PASS: 76 ordered cases; 84 original attachments; 83 unique SHA256; 69,642,405 bytes.')
    print('PASS: image hashes/geometry, portable paths, upload limits, frozen reference and N07 errata.')
    print('Offline integrity check only; no model calls or new mathematical validation.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, TypeError, struct.error) as error:
        print('FAIL:', error, file=sys.stderr)
        sys.exit(1)
