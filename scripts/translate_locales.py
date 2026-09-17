"""Fill missing static UI translations using a configured OpenRouter model.

Sends only repository UI strings. Never reads user records. Generated text requires
linguistic review. Interpolation/key validation is mandatory before writing files.
Existing translations are preserved. No API calls without --model and an API key.
"""
import argparse
import json
import os
import urllib.request

from check_locales import LOCALES, ROOT, flatten, placeholders


def merge_flat(target, translated):
    for key, value in translated.items():
        node = target
        parts = key.split('.')
        for index, part in enumerate(parts[:-1]):
            child_type = list if parts[index + 1].isdigit() else dict
            if isinstance(node, list):
                position = int(part)
                while len(node) <= position:
                    node.append(None)
                if node[position] is None:
                    node[position] = child_type()
                node = node[position]
            else:
                node = node.setdefault(part, child_type())
        if isinstance(node, list):
            position = int(parts[-1])
            while len(node) <= position:
                node.append(None)
            node[position] = value
        else:
            node[parts[-1]] = value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, help='Explicit OpenRouter model ID; API calls may incur provider charges')
    parser.add_argument('--locale', action='append', help='Repeat to limit locales; default: all incomplete catalogs')
    args = parser.parse_args()
    key = os.environ.get('OPENROUTER_API_KEY', '')
    if not key:
        parser.error('Set OPENROUTER_API_KEY in the environment; never pass secrets on the command line.')
    registry = json.loads((ROOT / 'backend/core/languages.json').read_text())
    known = {row['code'] for row in registry}
    if args.locale and not set(args.locale) <= known:
        parser.error('Unknown locale requested')
    base = flatten(json.loads((LOCALES / 'en.json').read_text()))
    for locale in registry:
        code = locale['code']
        if code == 'en' or (args.locale and code not in args.locale):
            continue
        path = LOCALES / f'{code}.json'
        catalog = json.loads(path.read_text())
        missing = {k: v for k, v in base.items() if k not in flatten(catalog)}
        items = list(missing.items())
        for start in range(0, len(items), 40):
            source = dict(items[start:start + 40])
            prompt = (
                f'Translate these UI strings into {locale["name"]} ({code}), using natural product language. '
                'Return only a JSON object with exactly the supplied keys. Preserve all {{interpolation}} '
                'variables, brand names, numerical values, contractual obligations and optional/required distinctions. '
                'Do not change the legal meaning of consent. Input:\n' + json.dumps(source, ensure_ascii=False)
            )
            payload = {'model': args.model, 'messages': [{'role': 'user', 'content': prompt}],
                       'temperature': 0.1, 'response_format': {'type': 'json_object'}}
            request = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',
                data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.load(response)
            translated = json.loads(result['choices'][0]['message']['content'])
            if set(translated) != set(source):
                raise ValueError(f'{code}: provider returned missing/extra keys; nothing from this batch saved')
            for name, value in translated.items():
                if not isinstance(value, str) or not value.strip() or placeholders(value) != placeholders(source[name]):
                    raise ValueError(f'{code}/{name}: invalid translation or interpolation; batch not saved')
            merge_flat(catalog, translated)
            temporary = path.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            temporary.replace(path)
            print(f'{code}: saved {min(start + 40, len(items))}/{len(items)} missing translations', flush=True)


if __name__ == '__main__':
    main()
