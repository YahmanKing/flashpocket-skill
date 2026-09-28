import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('decks', ROOT / 'flashpocket-transcript/scripts/decks.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class DeckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / 'decks'
        self.folder.mkdir()
        self.env = patch.dict(os.environ, {'FLASHPOCKET_TRANSCRIPT_CONFIG_DIR': str(self.root / 'config')})
        self.env.start()
        self.cards = json.loads((ROOT / 'examples/candidates.json').read_text())
        d.configure(self.folder)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def write(self, cards=None, **kwargs):
        return d.write_cards('2026-09-28', 'weekly-sync', self.cards if cards is None else cards, **kwargs)

    def test_first_write_and_identical_repeat(self):
        result = self.write()
        rows = d.parse_existing(Path(result['file']).read_text())
        self.assertEqual(result['added_cards'], 3)
        self.assertEqual(len({row['id'] for row in rows}), 3)
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        self.assertEqual(self.write()['status'], 'no_additions')
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.folder.iterdir()})

    def test_normalization_and_example_difference(self):
        nested = self.folder / 'nested'
        nested.mkdir()
        (nested / 'existing.md').write_text('# Old\n意味 ::: ＧＥＴ  ON THE SAME PAGE! — Different example. <!-- fp:old -->\n')
        result = self.write(self.cards[:1])
        self.assertEqual(result['duplicate_candidates'], 1)
        self.assertEqual(result['added_cards'], 0)
        self.assertEqual(d.key('It’s   time.'), d.key("it's time"))
        self.assertNotEqual(d.key('work out'), d.key('worked out'))

    def test_collision_preserves_old_file(self):
        old = self.folder / '2026-09-28-weekly-sync.md'
        old.write_text('# Existing\n旧 :: other chunk <!-- fp:stable -->\n')
        original = old.read_bytes()
        result = self.write()
        self.assertTrue(result['file'].endswith('-weekly-sync-2.md'))
        self.assertEqual(old.read_bytes(), original)

    def test_append_preserves_bytes_and_ids(self):
        target = self.folder / 'old.md'
        original = '# Old\n旧 :: other chunk <!-- fp:stable -->'.encode()
        target.write_bytes(original)
        result = self.write(append=str(target))
        self.assertEqual(result['added_cards'], 3)
        self.assertTrue(target.read_bytes().startswith(original))
        rows = d.parse_existing(target.read_text())
        self.assertEqual(rows[0]['id'], 'stable')
        self.assertEqual(len({row['id'] for row in rows}), 4)

    def test_invalid_append_never_changes_file(self):
        for content in ['# Old\nQ :: A', '# Old\nQ :: A <!-- fp:x -->\nB :: C <!-- fp:x -->', '# Old\n## Q\nA']:
            target = self.folder / 'old.md'
            target.write_text(content)
            with self.assertRaises(ValueError):
                self.write(append=str(target))
            self.assertEqual(target.read_text(), content)
        outside = self.root / 'outside.md'
        outside.write_text('Q :: A <!-- fp:x -->')
        with self.assertRaises(ValueError):
            self.write(append=str(outside))

    def test_append_always_compares_target_in_hidden_directory(self):
        hidden = self.folder / '.hidden'
        hidden.mkdir()
        target = hidden / 'old.md'
        target.write_text('意味 :: get on the same page <!-- fp:stable -->')
        original = target.read_bytes()
        self.assertEqual(self.write(self.cards[:1], append=str(target))['status'], 'no_additions')
        self.assertEqual(target.read_bytes(), original)

    def test_append_rejects_unclosed_fence(self):
        target = self.folder / 'old.md'
        target.write_text('Q :: A <!-- fp:stable -->\n```\nhidden text')
        original = target.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Unclosed code fence'):
            self.write(append=str(target))
        self.assertEqual(target.read_bytes(), original)

    def test_candidate_heading_cannot_change_parser_mode(self):
        for bad in ['## 日本語', '##', '# title']:
            with self.assertRaises(ValueError):
                self.write([dict(self.cards[0], meaning=bad)])
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_limit_counts_reverse_cards_and_existing_cards(self):
        candidate = dict(self.cards[0], bidirectional=True)
        self.assertEqual(self.write([candidate], limit=1)['status'], 'no_additions')
        result = self.write([candidate] + self.cards, limit=2)
        self.assertEqual(result['added_cards'], 2)
        self.assertEqual(self.write(self.cards[1:], append=result['file'], limit=2)['status'], 'no_additions')
        many = [dict(self.cards[0], chunk='chunk ' + str(i)) for i in range(30)]
        self.assertEqual(self.write(many)['added_cards'], 20)

    def test_exclusions_fences_inline_code_and_hidden_directories(self):
        (self.folder / 'h2.md').write_text('## Q\nA')
        (self.folder / 'invalid.md').write_text('Q ::')
        (self.folder / 'bad.md').write_bytes(b'\xff')
        hidden = self.folder / '.obsidian'
        hidden.mkdir()
        (hidden / 'ignore.md').write_text('Q :: get on the same page')
        result = self.write()
        self.assertEqual(result['added_cards'], 3)
        self.assertEqual(len(result['excluded_files']), 3)
        rows = d.parse_existing('# X\n```\nhidden::card\n```\nUse `a::b` :: real chunk <!-- fp:x --> <!--SR:ignored-->')
        self.assertEqual(rows[0]['key'], 'real chunk')
        self.assertEqual(rows[0]['id'], 'x')

    def test_setting_survives_relocation_and_invalid_settings_recover(self):
        self.assertEqual(d.output_folder(), self.folder.resolve())
        other = self.root / 'other'
        other.mkdir()
        self.folder.rmdir()
        with self.assertRaisesRegex(ValueError, 'needs_output_directory'):
            d.output_folder()
        d.configure(other)
        self.assertEqual(d.output_folder(), other.resolve())
        d.config_path().write_text('{broken')
        with self.assertRaisesRegex(ValueError, 'needs_output_directory'):
            d.output_folder()
        d.configure(other)
        other.chmod(0o555)
        try:
            with self.assertRaisesRegex(ValueError, 'needs_output_directory'):
                d.output_folder()
        finally:
            other.chmod(0o755)

    def test_candidate_format_injection_is_rejected_without_output(self):
        for bad in ['a\n## injected', 'a :: injected', 'a <!-- fp:duplicate -->']:
            with self.assertRaises(ValueError):
                self.write([dict(self.cards[0], chunk=bad)])
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_published_input_expected_output_fixtures(self):
        for case in json.loads((ROOT / 'examples/cases.json').read_text()):
            with self.subTest(case=case['case']):
                folder = self.root / case['case']
                folder.mkdir()
                d.configure(folder)
                target = folder / case['existing_name']
                target.write_text(case['existing'])
                original = target.read_bytes()
                candidates = [self.cards[i] for i in case['candidate_indices']]
                result = self.write(candidates, append=str(target) if case['append'] else None)
                actual_name = Path(result['file']).name if result['file'] else None
                self.assertEqual(actual_name, case['expected_file'])
                if result['file']:
                    rows = d.parse_existing(Path(result['file']).read_text())
                    added_rows = rows[1:] if case['append'] else rows
                    self.assertEqual([row['key'] for row in added_rows], case['expected_added_keys'])
                if case['append']:
                    self.assertTrue(target.read_bytes().startswith(original))
                else:
                    self.assertEqual(target.read_bytes(), original)

    def test_sample_contains_expected_keys_and_no_sensitive_terms(self):
        text = (ROOT / 'examples/2026-09-28-weekly-sync.md').read_text()
        self.assertEqual([r['key'] for r in d.parse_existing(text)], [d.key(c['chunk']) for c in self.cards])
        for secret in ['Mina', 'Owen', 'Northstar', 'Blue Harbor', 'Firefly', '48,000']:
            self.assertNotIn(secret, text)


if __name__ == '__main__':
    unittest.main()
