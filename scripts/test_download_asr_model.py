import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('download_asr_model.py')

class DownloadTests(unittest.TestCase):
    def load_script(self):
        spec = importlib.util.spec_from_file_location('download_asr_model', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_dry_run_is_offline_and_anchored_to_project_not_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            result = subprocess.run([sys.executable, str(SCRIPT), '--dry-run'], cwd=d, capture_output=True, text=True, encoding='utf-8', timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan['repo'], 'Systran/faster-whisper-medium')
        self.assertEqual(plan['revision'], '08e178d48790749d25932bbc082711ddcfdfbc4f')
        self.assertEqual(Path(plan['destination']), SCRIPT.parent.parent/'work/models/faster-whisper-medium')

    def test_download_is_pinned_anonymous_and_checks_required_files(self):
        module = self.load_script()
        calls = []
        with tempfile.TemporaryDirectory() as d:
            def download(**kwargs):
                calls.append(kwargs)
                target = Path(kwargs['local_dir']); target.mkdir(parents=True)
                for name in module.REQUIRED: (target/name).write_bytes(b'test model file')
                return str(target)
            with patch.object(module, 'ROOT', Path(d)), patch.dict(sys.modules, {'huggingface_hub': types.SimpleNamespace(snapshot_download=download)}), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main([]), 0)
            self.assertEqual(calls[0]['revision'], '08e178d48790749d25932bbc082711ddcfdfbc4f')
            self.assertIs(calls[0]['token'], False)
            record = json.loads((Path(d)/'work/asr-model-download-medium.json').read_text())
            self.assertEqual(len(record['files']), len(module.REQUIRED))

    def test_incomplete_download_is_not_reported_as_ready(self):
        module = self.load_script()
        with tempfile.TemporaryDirectory() as d:
            def download(**kwargs):
                target = Path(kwargs['local_dir']); target.mkdir(parents=True)
                (target/'config.json').write_text('{}')
                return str(target)
            with patch.object(module, 'ROOT', Path(d)), patch.dict(sys.modules, {'huggingface_hub': types.SimpleNamespace(snapshot_download=download)}), contextlib.redirect_stderr(io.StringIO()):
                self.assertNotEqual(module.main([]), 0)
            self.assertFalse((Path(d)/'work/asr-model-download-medium.json').exists())

if __name__ == '__main__': unittest.main()
