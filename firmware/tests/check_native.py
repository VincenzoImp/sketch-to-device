#!/usr/bin/env python3
"""Compile the actual C runtime and compare parsing with the trusted host parser."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from runtime.validation import ValidationError, parse_app


def main():
    cjson = ROOT / '.tools/esp-idf-v5.5.5/components/json/cJSON'
    if not (cjson / 'cJSON.c').is_file():
        raise SystemExit('Download the pinned ESP-IDF source first.')
    with tempfile.TemporaryDirectory(prefix='sketch-native-') as temporary:
        binary = Path(temporary) / 'core-test'
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-I', str(ROOT / 'firmware/main'), '-I', str(cjson),
                        str(ROOT / 'firmware/tests/core_test.c'),
                        str(ROOT / 'firmware/main/app_spec.c'), str(cjson / 'cJSON.c'),
                        '-o', str(binary)], check=True)
        fixtures = [ROOT / 'contracts/fixtures/tap-sprint.json',
                    ROOT / 'contracts/fixtures/focus-timer.json']
        subprocess.run([str(binary)] + [str(path) for path in fixtures], check=True)
        cases = [path.read_bytes() for path in fixtures]
        original = json.loads(cases[0])
        locations = [(), ('target',), ('theme',), ('state',), ('screens', 0),
                     ('screens', 1, 'widgets', 0), ('screens', 1, 'widgets', 1),
                     ('screens', 1, 'widgets', 2),
                     ('screens', 0, 'widgets', 1, 'on_press', 0)]
        for location in locations:
            node = original
            for key in location:
                node = node[key]
            for field in list(node) + ['unsupported_field']:
                for value in (None, True, False, {}, [], 0, '', 1.5, 2147483648):
                    changed = copy.deepcopy(original)
                    target = changed
                    for key in location:
                        target = target[key]
                    target[field] = value
                    cases.append(json.dumps(changed, separators=(',', ':')).encode())
        compact = json.dumps(original, separators=(',', ':')).encode()
        cases += [compact.replace(b'"version":1', b'"version":1.0', 1),
                  compact.replace(b'"version":1', b'"version":01', 1),
                  compact.replace(b'"version":1', b'"version":1e0', 1),
                  compact.replace(b'"version":1', b'"version":1,"version":1', 1),
                  compact.replace(b'tap_sprint', b'tap_sprint\\u0000hidden', 1),
                  b'[' * 13 + b']' * 13, compact + b'false',
                  compact + b' ' * 65536]
        path = Path(temporary) / 'candidate.json'
        for index, raw in enumerate(cases):
            try:
                parse_app(raw)
                expected = True
            except ValidationError:
                expected = False
            path.write_bytes(raw)
            result = subprocess.run([str(binary), '--validate', str(path)],
                                    capture_output=True, timeout=3)
            if result.returncode not in (0, 1) or (result.returncode == 0) != expected:
                raise AssertionError('Native/host validation mismatch at synthetic case {}'.format(index))
        print('PASS: {} native/host parser comparisons'.format(len(cases)))


if __name__ == '__main__':
    main()
