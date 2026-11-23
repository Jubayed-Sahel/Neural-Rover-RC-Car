"""Choose which enrolled people send a Telegram message when identified."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GALLERY = ROOT / 'faces.local.json'
WATCH = ROOT / 'alert_people.local.json'


def enrolled_names():
    if not GALLERY.exists():
        return []
    document = json.loads(GALLERY.read_text(encoding='utf-8'))
    if not isinstance(document, dict):
        raise ValueError('Unrecognized face gallery format. Re-enroll in the dashboard.')
    people = document.get('people')
    if document.get('version') != 2 or not isinstance(people, dict):
        raise ValueError('Old face gallery. Re-enroll photos in 00_START_NEURAL_ROVER.bat first.')
    return sorted(people)


def load_watch_names(path=None):
    path = Path(path) if path is not None else WATCH
    if not path.exists():
        return set()
    try:
        document = json.loads(path.read_text(encoding='utf-8'))
        names = document['names']
        if document.get('version') != 1 or not isinstance(names, list):
            raise ValueError
        if not all(isinstance(name, str) and name.strip() for name in names):
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        print('Alert person list is invalid. Run 12_MARK_ALERT_PEOPLE.bat again.')
        return set()
    return set(names)


def save_watch_names(names, path=None):
    path = Path(path) if path is not None else WATCH
    pending = path.with_name('alert_people.pending.local.json')
    pending.write_text(json.dumps({'version': 1, 'names': sorted(names)}, indent=2) + '\n', encoding='utf-8')
    pending.replace(path)


def require_enrolled(requested, names):
    missing = [name for name in requested if name not in names]
    if missing:
        known = ', '.join(names) if names else 'none'
        raise ValueError(f'Not enrolled: {", ".join(missing)}. Enrolled people: {known}.')
    return set(requested)


def show(names, selected):
    print('Enrolled people. ALERT sends a Telegram message when that person is identified.')
    if not names:
        print('No one is enrolled yet. Run 08_ENROLL_TAPO_FACE.bat first.')
        return
    for index, name in enumerate(names, start=1):
        state = 'ALERT' if name in selected else 'quiet'
        print(f'  {index}. {name}  [{state}]')
    marked = [name for name in names if name in selected]
    print('Marked: ' + (', '.join(marked) if marked else 'nobody'))


COMMANDS = """\
Commands:
  help                 show every command
  ?                    show every command
  list                 show enrolled people and who is marked
  show                 show enrolled people and who is marked
  1                    mark person 1
  1 2                  mark several people
  sahel                mark that enrolled name
  on 1                 mark person 1
  mark sahel           mark that enrolled name
  add 1                add a mark and keep the others
  all                  mark every enrolled person
  off 1                remove the mark from person 1
  remove sahel         remove the mark from that name
  unmark 1             remove the mark from person 1
  none                 remove every mark
  clear                remove every mark
  save                 write the current marks again
  done                 close this window
  quit                 close this window
  exit                 close this window
  q                    close this window

Terminal commands:
  alert_people.py --commands
  alert_people.py --list
  alert_people.py --set sahel mira
  alert_people.py --add sahel
  alert_people.py --remove sahel
  alert_people.py --all
  alert_people.py --clear
"""

ON_VERBS = {'on', 'mark', 'add'}
OFF_VERBS = {'off', 'remove', 'unmark'}
EXIT_VERBS = {'done', 'quit', 'exit', 'q'}


def print_commands():
    print(COMMANDS, end='' if COMMANDS.endswith('\n') else '\n')


def resolve_name(names, token):
    if token.isdigit() and 1 <= int(token) <= len(names):
        return names[int(token) - 1]
    for name in names:
        if name.casefold() == token.casefold():
            return name
    return None


def resolve_targets(names, text):
    whole = resolve_name(names, text)
    if whole is not None:
        return [whole]
    tokens = [token for token in text.replace(',', ' ').split() if token]
    if not tokens:
        return None
    chosen = []
    for token in tokens:
        name = resolve_name(names, token)
        if name is None:
            return None
        chosen.append(name)
    return chosen


def parse_command(names, selected, raw):
    text = raw.strip()
    folded = text.casefold()
    if folded in {'help', '?'}:
        return 'help', selected
    if folded in {'list', 'show'}:
        return 'list', selected
    if folded == 'save':
        return 'save', selected
    if folded in EXIT_VERBS:
        return 'exit', selected
    if folded == 'all':
        return 'update', set(names)
    if folded in {'none', 'clear'}:
        return 'update', set()
    verb = 'on'
    rest = text
    first, separator, tail = text.partition(' ')
    key = first.casefold()
    if key in ON_VERBS or key in OFF_VERBS:
        if not separator or not tail.strip():
            return 'bad', selected
        verb = 'off' if key in OFF_VERBS else 'on'
        rest = tail.strip()
    chosen = resolve_targets(names, rest)
    if not chosen:
        return 'bad', selected
    selected = set(selected)
    for name in chosen:
        if verb == 'off':
            selected.discard(name)
        else:
            selected.add(name)
    return 'update', selected


def choose(names, selected):
    selected = set(selected)
    show(names, selected)
    if not names:
        return selected
    print()
    print('A mark is saved immediately and stays on until you remove it.')
    print_commands()
    while True:
        raw = input('> ').strip()
        if not raw:
            show(names, selected)
            continue
        action, selected = parse_command(names, selected, raw)
        if action == 'help':
            print_commands()
        elif action == 'list':
            show(names, selected)
        elif action == 'save':
            save_watch_names(selected)
            show(names, selected)
            print('Saved.')
        elif action == 'exit':
            return selected
        elif action == 'bad':
            print('Unknown command. Type help to see every command.')
        else:
            save_watch_names(selected)
            show(names, selected)
            print('Saved. The mark stays on until you remove it.')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter, epilog=COMMANDS)
    parser.add_argument('--commands', action='store_true', help='Show every command')
    parser.add_argument('--list', action='store_true', help='Show enrolled people and who is marked')
    parser.add_argument('--set', nargs='+', metavar='NAME', help='Mark only these enrolled people')
    parser.add_argument('--add', nargs='+', metavar='NAME', help='Add marks and keep the current ones')
    parser.add_argument('--remove', nargs='+', metavar='NAME', help='Remove marks and keep the others')
    parser.add_argument('--all', action='store_true', help='Mark every enrolled person')
    parser.add_argument('--clear', action='store_true', help='Remove every mark')
    args = parser.parse_args()
    chosen = [args.commands, args.list, bool(args.set), bool(args.add), bool(args.remove), args.all, args.clear]
    if sum(bool(item) for item in chosen) > 1:
        parser.error('Use one of --commands, --list, --set, --add, --remove, --all, or --clear')
    if args.commands:
        print_commands()
        return
    names = enrolled_names()
    stored = load_watch_names() & set(names)
    if args.list:
        show(names, stored)
        return
    if args.clear or args.all or args.set or args.add or args.remove:
        if args.clear:
            selected = set()
        elif args.all:
            selected = set(names)
        elif args.set:
            selected = require_enrolled(args.set, names)
        elif args.add:
            selected = stored | require_enrolled(args.add, names)
        else:
            selected = stored - require_enrolled(args.remove, names)
        save_watch_names(selected)
        show(names, selected)
        print('Saved.')
        return
    selected = choose(names, stored)
    marked = ', '.join(sorted(selected & set(names))) if selected else 'nobody'
    print(f'Telegram alerts stay on for: {marked}.')
    print('Open 09_RECOGNIZE_TAPO_FACES.bat. A marked person sends one message, then waits 60 seconds.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f'Alert people: {error}')
