import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('setup_environment.py')

def load_setup():
    spec = importlib.util.spec_from_file_location('setup_environment', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class SetupTests(unittest.TestCase):
    def test_plan_uses_project_paths_and_does_not_create_files(self):
        module = load_setup()
        with tempfile.TemporaryDirectory(prefix='setup with spaces ') as d:
            root = Path(d)/'new project'
            plan = module.make_plan(root)
            self.assertEqual(plan['project'], str(root))
            self.assertIn('medium', plan['models'])
            self.assertIn('qwen2.5:3b', plan['models'])
            self.assertFalse(root.exists())

    def test_medium_reuse_requires_pinned_revision_and_file_sizes(self):
        module = load_setup()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d);target = root/'work/models/faster-whisper-medium';target.mkdir(parents=True)
            files=[]
            for name in module.ASR_REQUIRED:
                (target/name).write_bytes(b'model');files.append({'name':name,'bytes':5})
            record=root/'work/asr-model-download-medium.json'
            record.write_text(json.dumps({'revision':module.MEDIUM_REVISION,'files':files}))
            self.assertTrue(module.medium_ready(root))
            (target/'model.bin').write_bytes(b'broken-size')
            self.assertFalse(module.medium_ready(root))
            record.write_text(json.dumps({'revision':'wrong','files':files}))
            self.assertFalse(module.medium_ready(root))

    def test_clean_install_creates_env_installs_package_then_provisions(self):
        module = load_setup()
        with tempfile.TemporaryDirectory(prefix='install with spaces ') as d:
            root=Path(d);calls=[]
            with patch.object(module,'run_checked',side_effect=lambda args,**kwargs:calls.append(args)),contextlib.redirect_stdout(io.StringIO()):
                module.install_environment(root,'python-base','ollama-binary')
            self.assertEqual(calls[0],['python-base','-m','venv',str(root/'work/asr-venv')])
            self.assertIn('pip',calls[1]);self.assertEqual(calls[1][-1],str(root)+'[ocr]')
            self.assertIn('--provision',calls[2]);self.assertEqual(calls[2][-1],'ollama-binary')

    def test_failed_package_install_stops_before_models(self):
        module=load_setup()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);python=root/'work/asr-venv/Scripts/python.exe';python.parent.mkdir(parents=True);python.touch()
            with patch.object(module,'run_checked',side_effect=RuntimeError('pip failed')) as run,contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):module.install_environment(root,'base','ollama')
            self.assertEqual(run.call_count,1)

    def test_qwen_pull_uses_owned_loopback_environment_and_rechecks_tags(self):
        module=load_setup();exits=[]
        @contextlib.contextmanager
        def owned(*args):
            try:yield (12345,{'OLLAMA_HOST':'127.0.0.1:12345','OLLAMA_NO_CLOUD':'1'})
            finally:exits.append('closed')
        with tempfile.TemporaryDirectory() as d,patch.object(module,'private_runtime',owned),patch.object(module,'tags',side_effect=[[],[{'name':'qwen2.5:3b','digest':'sha256:test'}]]),patch.object(module,'run_checked') as run,contextlib.redirect_stdout(io.StringIO()):
            module.provision_qwen(Path(d),'ollama-binary')
            self.assertEqual(run.call_args.args[0],['ollama-binary','pull','qwen2.5:3b'])
            self.assertEqual(run.call_args.kwargs['env']['OLLAMA_HOST'],'127.0.0.1:12345')
        self.assertEqual(exits,['closed'])

    def test_qwen_download_failure_closes_owned_runtime(self):
        module=load_setup();exits=[]
        @contextlib.contextmanager
        def owned(*args):
            try:yield (12345,{})
            finally:exits.append('closed')
        with tempfile.TemporaryDirectory() as d,patch.object(module,'private_runtime',owned),patch.object(module,'tags',return_value=[]),patch.object(module,'run_checked',side_effect=RuntimeError('pull failed')),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):module.provision_qwen(Path(d),'ollama')
        self.assertEqual(exits,['closed'])

    def test_existing_qwen_is_reused_without_pull(self):
        module=load_setup()
        @contextlib.contextmanager
        def owned(*args):yield (12345,{})
        with tempfile.TemporaryDirectory() as d,patch.object(module,'private_runtime',owned),patch.object(module,'tags',return_value=[{'name':'qwen2.5:3b'}]),patch.object(module,'run_checked') as run,contextlib.redirect_stdout(io.StringIO()):
            module.provision_qwen(Path(d),'ollama');run.assert_not_called()

    def test_check_rejects_missing_environment_without_creating_it(self):
        module=load_setup()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(RuntimeError):module.check_ready(root)
            self.assertFalse((root/'work').exists())

    def test_owned_process_is_cleaned_when_provisioning_body_fails(self):
        module=load_setup()
        with tempfile.TemporaryDirectory() as d,patch('content_extractor.supervisor.WindowsJob') as job,patch('content_extractor.supervisor.terminate_tree') as terminate,patch.object(module.subprocess,'Popen') as spawn,patch.object(module,'tags',return_value=[]):
            spawn.return_value.poll.return_value=None
            with self.assertRaisesRegex(RuntimeError,'body failure'):
                with module.private_runtime(Path(d),'ollama'):
                    raise RuntimeError('body failure')
            terminate.assert_called_once_with(spawn.return_value)
            job.return_value.close.assert_called_once()
            spawn.return_value.wait.assert_called()

    def test_doctor_success_without_ocr_is_not_installation_success(self):
        module=load_setup()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);scripts=root/'work/asr-venv/Scripts';scripts.mkdir(parents=True)
            for name in ['python.exe','content-extractor.exe']:(scripts/name).touch()
            from types import SimpleNamespace
            with patch.object(module,'run_checked',return_value=SimpleNamespace(stdout='{"status":"ready","checks":{"ocr":false}}')):
                with self.assertRaisesRegex(RuntimeError,'including OCR'):module.check_ready(root)

if __name__=='__main__':unittest.main()
