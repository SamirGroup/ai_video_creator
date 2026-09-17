"""Compare registry mirrors, translation keys and interpolation variables.

Use --strict to fail on incomplete translations (release gate).
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / 'frontend/src/i18n/locales'


def flatten(value, prefix=''):
    result = {}
    for key, item in (enumerate(value) if isinstance(value, list) else value.items()):
        path = f'{prefix}{key}'
        if isinstance(item, (dict, list)):
            result.update(flatten(item, path + '.'))
        else:
            result[path] = item
    return result


def placeholders(value):
    return set(re.findall(r'{{\s*([^{}]+?)\s*}}', value))


def inspect():
    registry = json.loads((ROOT / 'backend/core/languages.json').read_text())
    mirror = json.loads((ROOT / 'frontend/src/i18n/languages.json').read_text())
    assert registry == mirror, 'Backend and frontend language registries differ'
    assert len(registry) == len({row['code'] for row in registry}) == 30
    base = flatten(json.loads((LOCALES / 'en.json').read_text()))
    reports = []
    for language in registry:
        code = language['code']
        local = flatten(json.loads((LOCALES / f'{code}.json').read_text()))
        unknown = set(local) - set(base)
        assert not unknown, (code, 'Unknown keys', unknown)
        for key, value in local.items():
            assert isinstance(value, str) and value.strip(), (code, key, 'Empty translation')
            assert placeholders(value) == placeholders(base[key]), (code, key, 'Broken interpolation')
        reports.append({'code': code, 'translated': len(local), 'total': len(base), 'missing': sorted(set(base) - set(local))})
    return reports


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--strict', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    report = inspect()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for row in report:
            print(f"{row['code']:5} {row['translated']}/{row['total']} translations; {len(row['missing'])} missing")
    if args.strict and any(row['missing'] for row in report):
        raise SystemExit('Incomplete UI translations: release gate failed.')
