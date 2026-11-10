import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

def load_checker():
    spec=importlib.util.spec_from_file_location('check_repository',Path(__file__).with_name('check_repository.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

class RepositoryHygieneTests(unittest.TestCase):
    def make_docs(self,module,root):
        for name in (*module.ACTIVE_DOCS,'LICENSE'):
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('Documentation.\n',encoding='utf-8')

    def test_portable_repository_is_accepted(self):
        module=load_checker()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.make_docs(module,root)
            with patch.object(module.subprocess,'check_output',return_value=b'README.md\0LICENSE\0'):
                self.assertEqual(module.check(root),[])

    def test_private_paths_tokens_and_broken_active_links_are_rejected(self):
        module=load_checker()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.make_docs(module,root)
            private_path='C:'+chr(92)+'Users'+chr(92)+'Example'+chr(92)+'private'
            (root/'fixture.txt').write_text(private_path+'\n'+'ghp_'+'x'*36,encoding='utf-8')
            (root/'README.md').write_text('[missing](missing.md)',encoding='utf-8')
            with patch.object(module.subprocess,'check_output',return_value=b'fixture.txt\0README.md\0'):
                errors=module.check(root)
            self.assertTrue(any('home path' in e for e in errors))
            self.assertTrue(any('GitHub token' in e for e in errors))
            self.assertTrue(any('broken local link' in e for e in errors))

if __name__=='__main__':unittest.main()
