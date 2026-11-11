import unittest,subprocess,sys,json,tempfile,io
from unittest.mock import patch
from contextlib import redirect_stdout
from pathlib import Path

class CLITests(unittest.TestCase):
    def run_cli(self,*args,data=None):
        return subprocess.run([sys.executable,'-m','savedex_extractor',*args],input=data,text=True,encoding='utf-8',capture_output=True,timeout=20)
    def test_version(self):
        r=self.run_cli('--version','--json')
        self.assertEqual(r.returncode,0)
        self.assertIn('3.0.0',json.loads(r.stdout)['supported_content_schema_versions'])
    def test_invalid_stdin_and_mixed_modes_are_safe_json(self):
        for args,data in [(('extract','--request','-'),'{not json'),(('extract','--url','https://www.instagram.com/p/DfbNjF_tqQo/','--request','-'),'{}')]:
            with self.subTest(args=args):
                r=self.run_cli(*args,data=data)
                self.assertEqual(r.returncode,64)
                body=json.loads(r.stdout);self.assertEqual(body['status'],'error')
                self.assertNotIn('Traceback',r.stdout)
    def test_missing_model_is_explicit(self):
        r=self.run_cli('extract','--url','https://www.instagram.com/p/DfbNjF_tqQo/','--model-dir',str(Path('does-not-exist').resolve()))
        self.assertEqual(r.returncode,69)
        self.assertEqual(json.loads(r.stdout)['status'],'error')
    def test_bad_worker_json_is_internal_not_user_error(self):
        from savedex_extractor.cli import main
        with tempfile.TemporaryDirectory() as d:
            model=Path(d)/'model';model.mkdir()
            for name in ['model.bin','config.json','tokenizer.json','vocabulary.txt']:(model/name).touch()
            def fake(command,job,*args):
                (job/'result.json').write_text('{invalid',encoding='utf-8');return 0
            out=io.StringIO()
            with patch('savedex_extractor.cli.text_ready',return_value=True),patch('savedex_extractor.cli.run_supervised',side_effect=fake),redirect_stdout(out):
                code=main(['extract','--url','https://www.instagram.com/p/DfbNjF_tqQo/','--model-dir',str(model),'--work-dir',d])
            self.assertEqual(code,70)
            self.assertEqual(json.loads(out.getvalue())['issues'][0]['code'],'VALIDATION_FAILED')
    def test_file_stdin_and_url_modes_normalize_same_request(self):
        value={'schema_version':'3.0.0','request_id':'parity','url':'https://www.instagram.com/p/DfbNjF_tqQo/?tracking=x','instructions':'Only names','output_language':'en'}
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'request with spaces.json';file.write_text(json.dumps(value),encoding='utf-8')
            common=['--model-dir',str(Path(d)/'absent')]
            runs=[self.run_cli('extract','--request','-',*common,data=json.dumps(value)),self.run_cli('extract','--request',str(file),*common),self.run_cli('extract','--url',value['url'],'--request-id','parity','--instructions','Only names','--output-language','en',*common)]
            bodies=[json.loads(r.stdout) for r in runs]
            self.assertTrue(all(r.returncode==69 for r in runs))
            self.assertTrue(all(b['request_id']=='parity' and b['source']['input_url']=='https://www.instagram.com/p/DfbNjF_tqQo/' and b['request_context']['instructions']=='Only names' for b in bodies))
    def test_stdin_without_eof_has_a_deadline(self):
        p=subprocess.Popen([sys.executable,'-m','savedex_extractor','extract','--request','-','--timeout-seconds','.2'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            p.wait(timeout=10)
            self.assertEqual(p.returncode,75)
            self.assertEqual(json.loads(p.stdout.read().decode())['issues'][0]['code'],'RESOURCE_LIMIT')
        finally:
            if p.poll() is None:p.kill();p.wait()
            for stream in [p.stdin,p.stdout,p.stderr]:stream.close()

if __name__=='__main__':unittest.main()
