import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('decks', ROOT / 'flashpocket/scripts/decks.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class DeckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / 'decks'
        self.folder.mkdir()
        self.env = patch.dict(os.environ, {'FLASHPOCKET_CONFIG_DIR': str(self.root / 'config')})
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

    def test_card_is_one_physical_line_with_example_on_the_next_display_line(self):
        result = self.write()
        text = Path(result['file']).read_text(encoding='utf-8')
        card_lines = [line for line in text.split('\n') if '::' in line]
        self.assertEqual(len(card_lines), 3)
        first = self.cards[0]
        self.assertIn(f"{first['chunk']}\u2028Example: {first['example']} <!-- fp:", card_lines[0])
        self.assertNotIn(' — ', text)
        rows = d.parse_existing(text)
        self.assertEqual([row['key'] for row in rows], [d.key(c['chunk']) for c in self.cards])
        self.assertTrue(all(row['id'] and row['id_count'] == 1 for row in rows))

    def test_old_and_new_formats_are_compared_and_appended_by_chunk_only(self):
        (self.folder / 'old.md').write_text('# Old\n旧 :: get on the same page — Old example. <!-- fp:old1 -->\n')
        new = self.folder / 'new.md'
        new.write_text('# New\n旧 ::: iron out the details\u2028Example: Other. <!-- fp:new1 -->\n', encoding='utf-8')
        original = new.read_bytes()
        result = self.write(append=str(new))
        self.assertEqual(result['duplicate_candidates'], 2)
        self.assertEqual(result['added_cards'], 1)
        self.assertTrue(new.read_bytes().startswith(original))
        rows = d.parse_existing(new.read_text(encoding='utf-8'))
        self.assertEqual([row['key'] for row in rows], ['iron out the details', 'keep everyone in the loop'])
        self.assertEqual(rows[0]['id'], 'new1')
        self.assertEqual(self.write()['status'], 'no_additions')

    def test_line_separator_is_not_a_physical_line_break_and_cannot_be_injected(self):
        rows = d.parse_existing('# X\nQ :: chunk\u2028Example: e <!-- fp:x -->\r\nR :: other <!-- fp:y -->')
        self.assertEqual([row['key'] for row in rows], ['chunk', 'other'])
        for bad in ['a\u2028b', 'a\u2029b', 'a\x85b']:
            for name in ('meaning', 'chunk', 'example'):
                with self.assertRaises(ValueError):
                    self.write([dict(self.cards[0], **{name: bad})])
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_learning_settings_are_fixed_choices_with_standard_defaults(self):
        self.assertEqual(list(d.CHUNK_LENGTHS), ['短い', '標準', '長め'])
        self.assertEqual(list(d.LEVELS), ['やさしい', '標準', '高度'])
        self.assertEqual(d.resolve_settings(), {'chunk_length': '標準', 'level': '標準', 'cefr': 'B1-B2'})
        self.assertEqual(d.resolve_settings('短い', 'やさしい')['cefr'], 'A2-B1')
        self.assertEqual(d.resolve_settings('長め', '高度')['cefr'], 'B2-C1')
        for length, level in [('5', None), ('long', None), (None, 'C2'), (None, 'B1')]:
            with self.assertRaises(ValueError):
                d.resolve_settings(length, level)
        with self.assertRaises(ValueError):
            self.write(length='7語')
        self.assertEqual(list(self.folder.iterdir()), [])
        self.assertEqual(self.write()['settings']['chunk_length'], '標準')
        self.assertEqual(self.write(self.cards[:1], length='長め', level='高度')['status'], 'no_additions')

    def test_skill_documents_every_choice_and_the_input_first_order(self):
        skill = (ROOT / 'flashpocket/SKILL.md').read_text(encoding='utf-8')
        transcript = (ROOT / 'flashpocket/references/transcript.md').read_text(encoding='utf-8')
        for label in [*d.CHUNK_LENGTHS, *d.LEVELS, 'A2–B1', 'B1–B2', 'B2–C1']:
            self.assertIn(label, transcript)
        for label in ['U+2028', 'Example:', 'references/transcript.md', 'list-targets']:
            self.assertIn(label, skill)
        self.assertLess(skill.index('Ask for the input first'), skill.index('decks.py" status'))
        self.assertIn('organization-authorized', skill)
        self.assertIn('not responsible', skill)
        self.assertNotIn('Remove names', skill)

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
        self.assertEqual([r['id'] for r in d.parse_existing(text)], ['sync1', 'sync2', 'sync3'])
        for c in self.cards:
            self.assertIn(f"{c['chunk']}\u2028Example: {c['example']} <!-- fp:", text)
        for secret in ['Mina', 'Owen', 'Northstar', 'Blue Harbor', 'Firefly', '48,000']:
            self.assertNotIn(secret, text)

    def test_candidate_without_example_is_a_plain_card_that_appends_and_dedupes(self):
        plain = {'meaning': '認識を合わせる', 'chunk': 'get on the same page'}
        for candidate in (plain, dict(plain, example=None)):
            folder = self.root / ('plain%d' % id(candidate))
            folder.mkdir()
            d.configure(folder)
            result = self.write([candidate])
            line = [l for l in Path(result['file']).read_text(encoding='utf-8').split('\n') if '::' in l][0]
            self.assertRegex(line, r'^認識を合わせる :: get on the same page <!-- fp:[0-9a-f]+ -->$')
            self.assertEqual(self.write([plain])['status'], 'no_additions')
            more = self.write([plain, self.cards[1]], append=result['file'])
            self.assertEqual(more['added_cards'], 1)
            self.assertEqual(len(d.parse_existing(Path(result['file']).read_text(encoding='utf-8'))), 2)
        for bad in ['', '   ', 5, 'a :: b']:
            with self.assertRaises(ValueError):
                self.write([dict(plain, example=bad)])

    def test_date_defaults_to_today_and_slug_defaults_to_deck(self):
        class Today(d.datetime.date):
            @classmethod
            def today(cls):
                return cls(2026, 10, 1)
        with patch.object(d.datetime, 'date', Today):
            result = d.write_cards(None, 'weekly-sync', self.cards)
            self.assertEqual(Path(result['file']).name, '2026-10-01-weekly-sync.md')
        self.assertTrue(Path(result['file']).read_text(encoding='utf-8').startswith('# 2026-10-01 weekly-sync\n'))
        japanese = d.write_cards('2026-09-28', '週次の定例', [dict(self.cards[0], chunk='another chunk')])
        self.assertEqual(Path(japanese['file']).name, '2026-09-28-deck.md')
        with self.assertRaisesRegex(ValueError, 'deck name'):
            d.write_cards('2026-09-28', ' ', self.cards)
        with self.assertRaises(ValueError):
            d.write_cards('2026-13-01', 'x', self.cards)

    def test_old_config_is_read_but_new_path_wins_and_saves_go_to_new_path(self):
        home = self.root / 'home'
        legacy = home / '.config/flashpocket-transcript'
        legacy.mkdir(parents=True)
        (legacy / 'config.json').write_text(json.dumps({'output_directory': str(self.folder)}))
        env = {k: v for k, v in os.environ.items() if not k.startswith('FLASHPOCKET_')}
        with patch.dict(os.environ, env, clear=True), patch.object(d.Path, 'home', return_value=home):
            self.assertEqual(d.output_folder(), self.folder.resolve())
            self.assertEqual(d.config_path(), home / '.config/flashpocket/config.json')
            other = self.root / 'other'
            other.mkdir()
            d.configure(other)
            self.assertEqual(d.output_folder(), other.resolve())
            self.assertEqual(json.loads((legacy / 'config.json').read_text())['output_directory'], str(self.folder))
            (home / '.config/flashpocket/config.json').write_text('{broken')
            with self.assertRaisesRegex(ValueError, 'needs_output_directory'):
                d.output_folder()

    def test_config_environment_variables_do_not_fall_back_to_home(self):
        home = self.root / 'home'
        legacy = home / '.config/flashpocket-transcript'
        legacy.mkdir(parents=True)
        (legacy / 'config.json').write_text(json.dumps({'output_directory': str(self.folder)}))
        isolated = self.root / 'isolated'
        old_dir, new_dir = self.root / 'old-env', self.root / 'new-env'
        for name, value in (('FLASHPOCKET_TRANSCRIPT_CONFIG_DIR', isolated), ('FLASHPOCKET_CONFIG_DIR', isolated)):
            env = {k: v for k, v in os.environ.items() if not k.startswith('FLASHPOCKET_')}
            with patch.dict(os.environ, dict(env, **{name: str(value)}), clear=True), patch.object(d.Path, 'home', return_value=home):
                with self.assertRaisesRegex(ValueError, 'needs_output_directory'):
                    d.output_folder()
        for directory in (old_dir, new_dir):
            directory.mkdir()
            other = self.root / ('target-' + directory.name)
            other.mkdir()
            (directory / 'config.json').write_text(json.dumps({'output_directory': str(other)}))
        with patch.dict(os.environ, {'FLASHPOCKET_TRANSCRIPT_CONFIG_DIR': str(old_dir)}, clear=False):
            os.environ.pop('FLASHPOCKET_CONFIG_DIR')
            self.assertEqual(d.output_folder(), (self.root / 'target-old-env').resolve())
        with patch.dict(os.environ, {'FLASHPOCKET_TRANSCRIPT_CONFIG_DIR': str(old_dir), 'FLASHPOCKET_CONFIG_DIR': str(new_dir)}):
            self.assertEqual(d.output_folder(), (self.root / 'target-new-env').resolve())

    def test_list_targets_returns_only_appendable_one_line_decks_newest_first(self):
        def deck(name, content, age):
            path = self.folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
            os.utime(path, (1_700_000_000 + age, 1_700_000_000 + age))
            return path
        ok = lambda n: f'# T\nQ{n} :: chunk {n} <!-- fp:id{n} -->\n'
        for i in range(7):
            deck(f'ok{i}.md', ok(i), i)
        deck('nested/deep.md', ok(20), 50)
        deck('h2.md', '## Q\nA\n', 60)
        deck('noid.md', '# T\nQ :: A\n', 61)
        deck('twoid.md', '# T\nQ :: A <!-- fp:a --><!-- fp:b -->\n', 62)
        deck('dup.md', '# T\nQ :: A <!-- fp:a -->\nR :: B <!-- fp:a -->\n', 63)
        deck('empty.md', '# Only a title\n', 64)
        deck('.hidden/h.md', ok(30), 65)
        deck('note.txt', ok(31), 66)
        (self.folder / 'link.md').symlink_to(self.folder / 'ok0.md')
        outside = self.root / 'outside.md'
        outside.write_text(ok(40))
        (self.folder / 'outside-link.md').symlink_to(outside)
        names = [t['name'] for t in d.list_targets()['targets']]
        self.assertEqual(names, ['deep.md', 'ok6.md', 'ok5.md', 'ok4.md', 'ok3.md'])
        self.assertEqual(d.list_targets()['targets'][0]['cards'], 1)
        for t in d.list_targets()['targets']:
            d.load_append_target(t['file'], self.folder.resolve())
        for age in (6, 5):
            os.utime(self.folder / f'ok{age}.md', (1_700_000_100, 1_700_000_100))
        self.assertEqual([t['name'] for t in d.list_targets()['targets']][:3], ['ok5.md', 'ok6.md', 'deep.md'])

    def test_list_targets_prefer_goes_first_only_when_appendable(self):
        for i in range(3):
            path = self.folder / f'd{i}.md'
            path.write_text(f'# T\nQ :: c{i} <!-- fp:i{i} -->\n')
            os.utime(path, (1_700_000_000 + i, 1_700_000_000 + i))
        listed = d.list_targets(prefer=str(self.folder / 'd0.md'))['targets']
        self.assertEqual([t['name'] for t in listed], ['d0.md', 'd2.md', 'd1.md'])
        (self.folder / 'bad.md').write_text('## Q\nA')
        for prefer in (str(self.folder / 'bad.md'), str(self.root / 'nope.md'), str(self.root)):
            self.assertEqual([t['name'] for t in d.list_targets(prefer=prefer)['targets']], ['d2.md', 'd1.md', 'd0.md'])
        hidden = self.folder / '.h' / 'd.md'
        hidden.parent.mkdir()
        hidden.write_text('# T\nQ :: hidden <!-- fp:hid -->\n')
        self.assertEqual([t['name'] for t in d.list_targets(prefer=str(hidden))['targets']], ['d2.md', 'd1.md', 'd0.md'])

    def test_list_targets_cli_and_missing_folder(self):
        import subprocess, sys
        env = dict(os.environ, FLASHPOCKET_CONFIG_DIR=str(self.root / 'config'))
        (self.folder / 'a.md').write_text('# T\nQ :: c <!-- fp:a -->\n')
        out = subprocess.run([sys.executable, str(ROOT / 'flashpocket/scripts/decks.py'), 'list-targets'], env=env, capture_output=True, text=True)
        self.assertEqual(json.loads(out.stdout)['targets'][0]['name'], 'a.md')
        out = subprocess.run([sys.executable, str(ROOT / 'flashpocket/scripts/decks.py'), 'write', '--name', 'x', '--cards', str(ROOT / 'examples/candidates.json')], env=env, capture_output=True, text=True)
        self.assertEqual(json.loads(out.stdout)['status'], 'written')


if __name__ == '__main__':
    unittest.main()
