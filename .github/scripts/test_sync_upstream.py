"""Exercise the real sync script in disposable repositories without networking."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name('sync-upstream.sh').resolve()


class SyncUpstreamTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='clash-sync-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.env = os.environ.copy()
        # Tests must not inherit Actions' worktree, index, or user Git settings.
        for key in list(self.env):
            if key.startswith('GIT_'):
                self.env.pop(key)
        self.env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Sync test')
        self.git('config', 'user.email', 'sync-test@example.invalid')
        self.write('Clash/kclash.ini', 'base config\n')
        self.write('Clash/example.list', 'base rule\n')
        self.write('.github/workflows/sync-upstream.yml', 'personal workflow\n')
        self.write('.github/scripts/sync-upstream.sh', SCRIPT.read_text())
        self.commit('base')
        self.git('branch', 'upstream')
        self.write('Clash/kclash.ini', 'personal emoji and manual groups\n')
        self.write('personal.txt', 'personal addition\n')
        self.commit('personal changes')
        self.personal_head = self.git('rev-parse', 'HEAD')
        # Execute a stable copy, like the workflow does.
        self.runner = self.root / 'run-sync.sh'
        shutil.copyfile(SCRIPT, self.runner)

    def git(self, *args):
        return subprocess.run(
            ['git', *args], cwd=self.repo, env=self.env,
            text=True, check=True, capture_output=True,
        ).stdout.strip()

    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-m', message)

    def upstream_changes(self, changes):
        self.git('checkout', 'upstream')
        for name, content in changes.items():
            if content is None:
                (self.repo / name).unlink()
            else:
                self.write(name, content)
        self.commit('upstream update')
        self.upstream_head = self.git('rev-parse', 'HEAD')
        self.git('checkout', 'main')

    def sync(self):
        return subprocess.run(
            ['bash', str(self.runner), 'upstream'], cwd=self.repo,
            env=self.env, text=True, capture_output=True,
        )

    def assert_preserved(self):
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual((self.repo / 'Clash/kclash.ini').read_text(),
                         'personal emoji and manual groups\n')
        self.assertEqual((self.repo / 'personal.txt').read_text(), 'personal addition\n')
        self.assertEqual(self.git('diff', self.personal_head, 'HEAD', '--',
                                  '.github/workflows', '.github/scripts', 'Clash/kclash.ini'), '')

    def test_conflicting_configuration_and_new_workflow_are_protected(self):
        self.upstream_changes({
            'Clash/kclash.ini': 'upstream groups\n',
            'Clash/example.list': 'new rule\n',
            '.github/workflows/sync-upstream.yml': 'upstream workflow\n',
            '.github/workflows/new.yml': 'new upstream workflow\n',
            '.github/scripts/sync-upstream.sh': 'upstream script\n',
        })
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_preserved()
        self.assertEqual((self.repo / 'Clash/example.list').read_text(), 'new rule\n')
        self.assertFalse((self.repo / '.github/workflows/new.yml').exists())
        self.git('merge-base', '--is-ancestor', self.upstream_head, 'HEAD')
        synced_head = self.git('rev-parse', 'HEAD')
        self.assertEqual(self.sync().returncode, 0)
        self.assertEqual(self.git('rev-parse', 'HEAD'), synced_head)

    def test_nonconflicting_configuration_edits_are_also_protected(self):
        # Git could merge this added line without a conflict; still keep ours.
        self.git('checkout', 'upstream')
        self.write('Clash/kclash.ini', 'base config\n' + '\n' * 20 + 'tail\n')
        self.commit('expanded base')
        self.git('checkout', 'main')
        self.git('merge', '-s', 'ours', '--no-edit', 'upstream')
        self.write('Clash/kclash.ini', 'personal emoji and manual groups\n' + '\n' * 20 + 'tail\n')
        self.commit('expanded personal config')
        self.personal_head = self.git('rev-parse', 'HEAD')
        self.upstream_changes({'Clash/kclash.ini': 'base config\n' + '\n' * 20 + 'upstream tail\n'})
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.git('diff', self.personal_head, 'HEAD', '--', 'Clash/kclash.ini'), '')

    def test_unprotected_conflict_aborts_without_a_commit(self):
        self.write('Clash/example.list', 'personal rule\n')
        self.commit('personal rule')
        self.personal_head = self.git('rev-parse', 'HEAD')
        self.upstream_changes({'Clash/example.list': 'upstream rule\n'})
        result = self.sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Clash/example.list', result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.personal_head)
        self.assert_preserved()
        self.assertEqual((self.repo / 'Clash/example.list').read_text(), 'personal rule\n')
        self.assertFalse((self.repo / '.git/MERGE_HEAD').exists())

    def test_upstream_deletion_keeps_personal_configuration(self):
        self.upstream_changes({'Clash/kclash.ini': None, 'Clash/example.list': 'new rule\n'})
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_preserved()

    def test_fast_forward_still_protects_configuration(self):
        self.git('branch', '-f', 'upstream', 'main')
        self.upstream_changes({'Clash/kclash.ini': 'upstream overwrite\n'})
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_preserved()
        self.git('merge-base', '--is-ancestor', self.upstream_head, 'HEAD')

    def test_clean_update_keeps_local_changes_in_other_files(self):
        self.write('Clash/example.list', 'personal rule\n' + '\n' * 20 + 'tail\n')
        self.commit('personal rule expansion')
        self.personal_head = self.git('rev-parse', 'HEAD')
        self.upstream_changes({'upstream.txt': 'new upstream file\n'})
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_preserved()
        self.assertTrue((self.repo / 'Clash/example.list').read_text().startswith('personal rule\n'))
        self.assertEqual((self.repo / 'upstream.txt').read_text(), 'new upstream file\n')

    def test_dirty_worktree_is_rejected(self):
        self.upstream_changes({'upstream.txt': 'new upstream file\n'})
        self.write('Clash/kclash.ini', 'uncommitted change\n')
        result = self.sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('working tree must be clean', result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.personal_head)
        self.assertEqual((self.repo / 'Clash/kclash.ini').read_text(), 'uncommitted change\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)
