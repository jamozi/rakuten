"""Exercise the real prepare function with a local Git fixture and fake I/O.

No production access, credentials, merchant identifiers, or publish calls.
The prefix loads on Python 3.13 as well as the repository's newer runtime;
unchanged CLI handlers below it use the newer exception-tuple syntax.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch as mock_patch
import scripts
ROOT = Path(__file__).resolve().parents[2]
BODY = '<div class="raos-editorial-v2"><section id="table">比較表</section><p>確認日：2026年8月23日</p><section id="sources">出典</section></div>'
PATCH = {'schema': 'RAOSReaderLivePatchV1', 'article_key': 'demo', 'post_id': 99, 'required_ids': ['table', 'sources'], 'required_product_ids': [], 'nav_html': '<nav id="ks-article-nav"><a href="#table">比較表</a></nav>', 'next_html': '<section id="ks-next-read"><a href="/travel/">戻る</a></section>', 'replacements': []}

class PreparePatchTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.operator = types.ModuleType('scripts.raos_wordpress_deployment_operator')
        self.operator.ROOT = self.root
        self.operator.THEME_ROOT = self.root / 'theme'
        self.operator.OperatorFailure = type('OperatorFailure', (RuntimeError,), {})
        self.operator.require_sha256 = lambda value: value
        self.registry = 'changes/wordpress-direct-publish-v1/articles.v1.json'
        self.source = 'changes/wordpress-direct-publish-v1/articles/demo.patch.json'
        self.row = {'article_key': 'demo', 'mode': 'existing', 'post_id': 99, 'post_type': 'post', 'slug': 'demo', 'title': '既存タイトル', 'patch_source': self.source}
        self.write(self.source, json.dumps(PATCH, ensure_ascii=False))
        self.write('scripts/raos_reader_live_patch.py', (ROOT / 'scripts/raos_reader_live_patch.py').read_text())
        self.write(self.registry, json.dumps({'schema': 'RAOSOwnerDirectArticlesV1', 'profile': 'owner-direct-v1', 'articles': [self.row]}))
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('add', '.')
        self.git('commit', '-qm', 'synthetic fixture')
        self.commit = self.git('rev-parse', 'HEAD').strip()
        self.baseline = {'id': 99, 'post_type': 'post', 'slug': 'demo', 'status': 'publish', 'title': '既存タイトル', 'excerpt': '既存抜粋', 'block_markup': BODY, 'taxonomies': {'category': [5]}, 'media_ids': [8], 'revision_id': 1, 'modified_gmt': 'fixture', 'content_sha256': 'a' * 64}
        self.status = {'schema': 'RAOSOwnerDirectStatusV1', 'profile': 'owner-direct-v1', 'enabled': True, 'targets': [], 'profile_sha256': 'b' * 64, 'theme': {'tree_sha256': 'c' * 64}}
        self.calls = []
        text = (ROOT / 'scripts/raos_wordpress_direct_publish.py').read_text()
        self.namespace = {'__file__': str(ROOT / 'scripts/raos_wordpress_direct_publish.py'), '__name__': 'reader_prepare_under_test'}
        with mock_patch.dict(sys.modules, {'scripts.raos_wordpress_deployment_operator': self.operator}), mock_patch.object(scripts, 'raos_wordpress_deployment_operator', self.operator, create=True):
            exec(compile(text.split('\ndef finish_batch(')[0], '<actual prepare prefix>', 'exec'), self.namespace)
        self.namespace['checkpoint_git'] = lambda *args: {'status': 'noop', 'commit': self.commit}

    def write(self, name, text):
        dest = self.root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True, text=True).stdout

    def call(self, name, body):
        self.calls.append(name)
        if name == 'status':
            return copy.deepcopy(self.status)
        if name == 'document':
            self.assertEqual(body, {'id': 99})
            return copy.deepcopy(self.baseline)
        self.fail('Unexpected network write: ' + name)

    def prepare(self):
        return self.namespace['prepare'](self.root, ['demo'], call=self.call)

    def test_compiles_live_patch_to_private_body(self):
        candidate, directory = self.prepare()
        row = candidate['articles'][0]
        self.assertIn('id="ks-article-nav"', row['document']['block_markup'])
        self.assertEqual(row['document']['taxonomies'], self.baseline['taxonomies'])
        self.assertEqual(row['document']['media_ids'], [8])
        self.assertEqual(row['body_file'], 'bodies/demo.html')
        self.assertEqual((directory / row['body_file']).read_text(), row['document']['block_markup'])
        self.assertEqual((directory / row['body_file']).stat().st_mode & 511, 384)
        self.assertNotIn('bodies/demo.html', candidate['sources'])
        self.assertIn('scripts/raos_reader_live_patch.py', candidate['sources'])
        self.assertEqual(self.calls, ['status', 'document'])
        self.assertEqual(self.namespace['load_candidate'](directory, candidate['candidate_id']), candidate)

    def test_missing_baseline_fails_closed(self):
        self.status['enabled'] = False
        with self.assertRaisesRegex(self.namespace['DirectFailure'], 'PATCH_BASELINE_REQUIRED'):
            self.prepare()

    def test_wrong_baseline_identity_fails_closed(self):
        self.baseline['id'] = 100
        with self.assertRaisesRegex(self.namespace['DirectFailure'], 'PATCH_BASELINE_MISMATCH'):
            self.prepare()

    def test_preserves_live_title_when_not_explicit(self):
        self.row.pop('title')
        self.write(self.registry, json.dumps({'schema': 'RAOSOwnerDirectArticlesV1', 'profile': 'owner-direct-v1', 'articles': [self.row]}))
        self.git('add', '.')
        self.git('commit', '-qm', 'omit title')
        self.commit = self.git('rev-parse', 'HEAD').strip()
        result, _ = self.prepare()
        self.assertEqual(result['articles'][0]['document']['title'], self.baseline['title'])

    def test_frozen_body_tampering_rejected(self):
        result, directory = self.prepare()
        (directory / result['articles'][0]['body_file']).write_text('changed')
        with self.assertRaisesRegex(self.namespace['DirectFailure'], 'SNAPSHOT_DRIFT'):
            self.namespace['load_candidate'](directory, result['candidate_id'])
if __name__ == '__main__':
    unittest.main()

class PreviewPatchTests(PreparePatchTests):

    def plan(self, candidate, directory):
        source = (ROOT / 'scripts/raos_wordpress_direct_preview.py').read_text()
        namespace = {'__file__': str(ROOT / 'scripts/raos_wordpress_direct_preview.py'), '__name__': 'reader_preview_under_test'}
        exec(compile(source.split('\ndef _private_dir(')[0], '<actual preview plan>', 'exec'), namespace)
        return namespace['preview_plan'](candidate, directory)

    def test_preview_accepts_hash_bound_merged_body(self):
        candidate, directory = self.prepare()
        result = self.plan(candidate, directory)
        self.assertEqual(result['widths'], [390, 1440])
        self.assertEqual(result['surfaces'][0]['path'], '/demo/')

    def test_preview_rejects_wrong_merged_hash(self):
        candidate, directory = self.prepare()
        candidate['articles'][0]['body_sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'BODY_CHANGED'):
            self.plan(candidate, directory)
