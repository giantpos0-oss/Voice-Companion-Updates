"""Write voice_companion/command_phrases.txt: the fixed command phrases in Voice Companion.

When the quick recognizer hears exactly one of these on a command screen, Voice
Companion acts on it at once, without the slower dictation model's second pass
(Will, November 12, 2026: voice commands felt slow). The list comes from the
command handler itself, so it never drifts: tools/test_command_phrases.py checks it.

    python3 tools/command_phrases.py --update
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
TARGET = TOOLS.parent / 'voice_companion' / 'command_phrases.txt'
HEADER = ('# Fixed voice command phrases, made by tools/command_phrases.py from the command handler.\n'
          '# Do not edit by hand: run python3 tools/command_phrases.py --update\n')


def current():
    sys.path.insert(0, str(TOOLS))
    from routing_snapshot import command_phrases, SENTENCES
    sentences = set(SENTENCES)
    return HEADER + ''.join(phrase + '\n' for phrase in command_phrases() if phrase not in sentences)


if __name__ == '__main__':
    text = current()
    if '--update' in sys.argv:
        TARGET.write_text(text, encoding='utf-8')
        print('Wrote %d phrases to %s' % (text.count('\n') - 2, TARGET))
    else:
        same = TARGET.is_file() and TARGET.read_text(encoding='utf-8') == text
        print('command_phrases.txt is ' + ('current.' if same else 'out of date: run python3 tools/command_phrases.py --update'))
        sys.exit(0 if same else 1)
