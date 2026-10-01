#!/usr/bin/env python3
"""Local file/config helpers. Extraction and privacy rewriting stay with the agent."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata
import uuid

FP_LOOSE = re.compile(r'<!--\s*fp:.*?-->')
FP_ID = re.compile(r'<!--\s*fp:([A-Za-z0-9_-]+)\s*-->')
SR = re.compile(r'<!--\s*SR:.*?-->')
# Cards stay on one physical line; the example is shown on the next display line after U+2028.
LINE_SEPARATOR = '\u2028'
EXAMPLE_LABEL = 'Example:'
UNSAFE_LINE_CHARACTERS = '\r\n\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029'
CHUNK_LENGTHS = {'短い': 'collocations and stock phrases', '標準': 'short expressions that are easy to reuse at work', '長め': 'expressions with surrounding context'}
LEVELS = {'やさしい': 'A2-B1', '標準': 'B1-B2', '高度': 'B2-C1'}
DEFAULT_CHUNK_LENGTH = DEFAULT_LEVEL = '標準'


def config_path():
    """Where settings are saved: always the new name."""
    directory = os.environ.get('FLASHPOCKET_CONFIG_DIR') or os.environ.get('FLASHPOCKET_TRANSCRIPT_CONFIG_DIR')
    return (Path(directory).expanduser() if directory else Path.home() / '.config/flashpocket') / 'config.json'


def read_config_path():
    """Where settings are read: the saved path, or the old path only when no override is set and the new file is absent."""
    path = config_path()
    if os.environ.get('FLASHPOCKET_CONFIG_DIR') or os.environ.get('FLASHPOCKET_TRANSCRIPT_CONFIG_DIR') or path.exists():
        return path
    return Path.home() / '.config/flashpocket-transcript/config.json'


def valid_folder(path):
    return path.is_dir() and bool(path.stat().st_mode & 0o222) and os.access(path, os.W_OK | os.X_OK)


def output_folder():
    try:
        data = json.loads(read_config_path().read_text())
        path = Path(data['output_directory'])
        if not path.is_absolute() or not valid_folder(path):
            raise ValueError('output_directory is unavailable or not writable')
        return path.resolve()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError('needs_output_directory: ' + str(error)) from error


def configure(directory):
    path = Path(directory).expanduser().resolve()
    if not valid_folder(path):
        raise ValueError('Choose an existing writable directory')
    destination = config_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_replace(destination, (json.dumps({'output_directory': str(path)}, ensure_ascii=False) + '\n').encode())
    return {'output_directory': str(path)}


def atomic_replace(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.fp-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def key(chunk):
    text = unicodedata.normalize('NFKC', chunk).replace('\u2019', "'").replace('\u2018', "'").lower()
    return ' '.join(text.split()).strip().rstrip('.!?。！？').strip()


def separator(line):
    """First :: outside matching inline backtick runs, as in FlashPocket v1.2."""
    delimiter = None
    index = 0
    while index < len(line):
        if line[index] == '`':
            end = index
            while end < len(line) and line[end] == '`':
                end += 1
            length = end - index
            if delimiter is None:
                delimiter = length
            elif delimiter == length:
                delimiter = None
            index = end
            continue
        if delimiter is None and line.startswith('::', index):
            count = 3 if line.startswith(':::', index) else 2
            return index, count
        index += 1
    return None


def resolve_settings(length=None, level=None):
    """Fixed choices only; an omitted setting uses the default without asking again."""
    length = DEFAULT_CHUNK_LENGTH if length is None else length
    level = DEFAULT_LEVEL if level is None else level
    if length not in CHUNK_LENGTHS:
        raise ValueError('chunk length must be one of: ' + ', '.join(CHUNK_LENGTHS))
    if level not in LEVELS:
        raise ValueError('level must be one of: ' + ', '.join(LEVELS))
    return {'chunk_length': length, 'level': level, 'cefr': LEVELS[level]}


def parse_existing(text):
    # FlashPocket splits on LF only (after CRLF/CR); str.splitlines() would also cut at U+2028.
    lines = re.split(r'\r\n|\r|\n', text)
    if any(line == '##' or line.startswith('## ') for line in lines):
        raise ValueError('H2 format is outside chunk comparison')
    rows = []
    fence = False
    for line in lines:
        if line.strip().startswith('```'):
            fence = not fence
            continue
        if fence or line == '#' or line.startswith('# '):
            continue
        ids = FP_ID.findall(line)
        clean = SR.sub('', FP_LOOSE.sub('', line))
        split = separator(clean)
        if split is None:
            continue
        index, count = split
        question = re.sub(r'^\s*(?:[-*+]\s+|[0-9]+\.\s+)', '', clean[:index]).strip()
        answer = clean[index + count:].strip()
        if not question or not answer:
            raise ValueError('Empty question or answer')
        chunk = re.split(' — |' + LINE_SEPARATOR, answer, maxsplit=1)[0]
        rows.append({'key': key(chunk), 'id': ids[0] if ids else None, 'id_count': len(ids), 'count': 2 if count == 3 else 1})
    if fence:
        raise ValueError('Unclosed code fence')
    if not rows:
        raise ValueError('No one-line cards')
    return rows


def scan(folder):
    keys, warnings = set(), []
    for path in sorted(folder.rglob('*.md')):
        relative = path.relative_to(folder)
        if any(part.startswith('.') for part in relative.parts[:-1]):
            continue
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(folder):
                raise ValueError('Symbolic links are outside chunk comparison')
            rows = parse_existing(path.read_text(encoding='utf-8'))
            keys.update(row['key'] for row in rows)
        except (OSError, UnicodeError, ValueError) as error:
            warnings.append({'file': str(relative), 'reason': str(error)})
    return keys, warnings


def field(value, name):
    if not isinstance(value, str) or not value.strip() or any(token in value for token in (*UNSAFE_LINE_CHARACTERS, '::', '<!--', '-->', '`')):
        raise ValueError('Invalid single-line ' + name)
    return value.strip()


def load_append_target(supplied, folder):
    """The one definition of an appendable deck, shared by write --append and list-targets."""
    supplied = Path(supplied).expanduser()
    target = supplied.resolve()
    if supplied.is_symlink() or not target.is_relative_to(folder) or target.suffix != '.md':
        raise ValueError('Append target must be a Markdown file inside the output directory')
    original = target.read_bytes()
    rows = parse_existing(original.decode('utf-8'))
    ids = [row['id'] for row in rows]
    if any(row['id_count'] != 1 for row in rows) or any(value is None for value in ids) or len(set(ids)) != len(ids):
        raise ValueError('Append target needs exactly one valid, unique ID per card line')
    return target, original, rows


def list_targets(prefer=None, limit=5):
    """Appendable one-line decks, newest first; an appendable --prefer deck goes first."""
    folder = output_folder()
    found = []
    for path in folder.rglob('*.md'):
        relative = path.relative_to(folder)
        if any(part.startswith('.') for part in relative.parts[:-1]):
            continue
        try:
            target, _, rows = load_append_target(path, folder)
            found.append((-target.stat().st_mtime, str(relative), target, rows))
        except (OSError, UnicodeError, ValueError):
            continue
    found.sort(key=lambda item: item[:2])
    if prefer:
        try:
            target, _, rows = load_append_target(prefer, folder)
            if any(part.startswith('.') for part in target.relative_to(folder).parts[:-1]):
                raise ValueError('Hidden directories are not listed')
            found =[(0, '', target, rows)] + [item for item in found if item[2] != target]
        except (OSError, UnicodeError, ValueError):
            pass
    return {'targets': [{'file': str(target), 'name': target.name, 'cards': sum(row['count'] for row in rows),
                         'modified': datetime.datetime.fromtimestamp(target.stat().st_mtime).isoformat(timespec='seconds')}
                        for _, _, target, rows in found[:limit]]}


def write_cards(date, name, candidates, append=None, limit=20, length=None, level=None):
    settings = resolve_settings(length, level)
    date = datetime.date.today().isoformat() if date is None else date
    datetime.date.fromisoformat(date)
    if not isinstance(limit, int) or limit < 1:
        raise ValueError('limit must be positive')
    name = field(name, 'deck name')
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'deck'
    folder = output_folder()
    known, warnings = scan(folder)
    original, target, used_ids, existing_count = b'', None, set(), 0
    if append:
        target, original, rows = load_append_target(append, folder)
        ids = [row['id'] for row in rows]
        known.update(row['key'] for row in rows)
        used_ids = set(ids)
        existing_count = sum(row['count'] for row in rows)
    if not isinstance(candidates, list):
        raise ValueError('Candidates must be a JSON array')
    added, duplicates, omitted, count = [], 0, 0, existing_count
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError('Each candidate must be an object')
        meaning = field(candidate.get('meaning'), 'meaning')
        if re.match(r'^#{1,2}(?:\s|$)', meaning):
            raise ValueError('Meaning cannot start with an H1/H2 heading')
        chunk = field(candidate.get('chunk'), 'chunk')
        example = candidate.get('example')
        if example is not None:
            example = field(example, 'example')
        if ' — ' in chunk:
            raise ValueError('Chunk cannot contain the example separator')
        bidirectional = candidate.get('bidirectional', False)
        if not isinstance(bidirectional, bool):
            raise ValueError('bidirectional must be boolean')
        compare = key(chunk)
        if not compare:
            raise ValueError('Chunk comparison key is empty')
        if compare in known:
            duplicates += 1
            continue
        weight = 2 if bidirectional else 1
        if count + weight > limit:
            omitted += 1
            continue
        identifier = uuid.uuid4().hex
        while identifier in used_ids:
            identifier = uuid.uuid4().hex
        used_ids.add(identifier)
        known.add(compare)
        added.append(f'{meaning} {":::" if bidirectional else "::"} {chunk}{f"{LINE_SEPARATOR}{EXAMPLE_LABEL} {example}" if example else ""} <!-- fp:{identifier} -->')
        count += weight
    result = {'added_cards': count - existing_count, 'duplicate_candidates': duplicates, 'omitted_for_limit': omitted, 'excluded_files': warnings, 'settings': settings}
    if not added:
        return dict(result, status='no_additions', file=None)
    payload = ('\n'.join(added) + '\n').encode('utf-8')
    if target:
        if target.read_bytes() != original:
            raise ValueError('Append target changed during processing; retry after inspecting it')
        atomic_replace(target, original + (b'' if original.endswith(b'\n') else b'\n') + payload)
    else:
        suffix = 1
        while True:
            filename = f'{date}-{slug}' + (f'-{suffix}' if suffix > 1 else '') + '.md'
            target = folder / filename
            try:
                with target.open('xb') as stream:
                    stream.write(f'# {date} {name}\n\n'.encode('utf-8') + payload)
                break
            except FileExistsError:
                suffix += 1
    return dict(result, status='written', file=str(target))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    setup = commands.add_parser('configure')
    setup.add_argument('directory')
    commands.add_parser('status')
    targets = commands.add_parser('list-targets')
    targets.add_argument('--prefer', help='An existing deck to list first when it can be appended to')
    write = commands.add_parser('write')
    write.add_argument('--date', help='YYYY-MM-DD (default: today, local)')
    write.add_argument('--name', required=True)
    write.add_argument('--cards', type=Path, required=True)
    write.add_argument('--append')
    write.add_argument('--limit', type=int, default=20)
    write.add_argument('--length', help='Chunk length: ' + ' / '.join(CHUNK_LENGTHS) + f' (default {DEFAULT_CHUNK_LENGTH})')
    write.add_argument('--level', help='Level: ' + ' / '.join(LEVELS) + f' (default {DEFAULT_LEVEL})')
    args = parser.parse_args()
    try:
        if args.command == 'configure':
            result = configure(args.directory)
        elif args.command == 'status':
            result = {'output_directory': str(output_folder())}
        elif args.command == 'list-targets':
            result = list_targets(args.prefer)
        else:
            result = write_cards(args.date, args.name, json.loads(args.cards.read_text(encoding='utf-8')), args.append, args.limit, args.length, args.level)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
