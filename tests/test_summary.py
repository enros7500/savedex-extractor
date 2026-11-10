import copy,json,subprocess,sys,tempfile,unittest
from pathlib import Path

class SummaryTests(unittest.TestCase):
    def fixture(self):
        return json.loads((Path(__file__).parent/'fixtures/companies.result.json').read_text(encoding='utf-8-sig'))

    def run_saved(self,result):
        with tempfile.TemporaryDirectory(prefix='summary with spaces ') as d:
            p=Path(d)/'result.json';p.write_text(json.dumps(result),encoding='utf-8-sig')
            return subprocess.run([sys.executable,'-m','content_extractor','summary','--result',str(p)],capture_output=True,text=True,encoding='utf-8',timeout=15)

    def test_default_language_and_error_metadata_are_english(self):
        from content_extractor.contracts import normalize_request,empty_result
        req=normalize_request({'schema_version':'3.0.0','request_id':'test','url':'https://www.instagram.com/p/DfbNjF_tqQo/'})
        self.assertEqual(req['output_language'],'en')
        self.assertEqual(empty_result()['topic']['label'],'Unknown topic')

    def test_render_does_not_change_result_or_claim_full_video_coverage(self):
        from content_extractor.presentation import render_summary
        r=self.fixture();r['coverage']['examined_asset_ids']=[];r['coverage']['unexamined_asset_ids']=['asset1'];r['coverage']['transcript_ranges']=[];r['coverage']['visual_positions']=[]
        r['evidence']=[e for e in r['evidence'] if e['source_type']=='author_description']
        before=copy.deepcopy(r);out=render_summary(r)
        self.assertEqual(r,before)
        self.assertIn('Description only',out)
        self.assertIn('not reviewed',out)
        self.assertIn('does not confirm full video coverage',out)
        self.assertIn('GitLab',out)
        self.assertNotIn('100%',out)

    def test_saved_result_works_offline_and_preserves_partial_code(self):
        r=self.fixture();r['status']='partial';r['coverage']['sufficiency']='insufficient';r['coverage']['missing_information']=['An announced item is missing.']
        r['issues']=[{'code':'EXTRACTION_FAILED','stage':'extraction','severity':'warning','message':'An announced item is missing.','affected_asset_ids':[],'affected_item_ids':[],'retryable':False}]
        out=self.run_saved(r)
        self.assertEqual(out.returncode,2,out.stderr)
        self.assertIn('An announced item is missing.',out.stdout)
        self.assertIn('Conclusion:',out.stdout)
        self.assertNotIn('schema_version',out.stdout)

    def test_saved_success_lists_entities_and_counts(self):
        out=self.run_saved(self.fixture())
        self.assertEqual(out.returncode,0,out.stderr)
        self.assertIn('10 of 10',out.stdout)
        self.assertIn('Anduril',out.stdout)

    def test_saved_error_and_invalid_result_are_readable(self):
        from content_extractor.contracts import empty_result
        out=self.run_saved(empty_result(message='Test failure.'))
        self.assertEqual(out.returncode,65,out.stderr)
        self.assertIn('Test failure.',out.stdout)
        out=self.run_saved({'status':'success'})
        self.assertEqual(out.returncode,64,out.stderr)
        self.assertIn('Invalid request',out.stdout)

    def test_json_extraction_remains_machine_readable(self):
        out=subprocess.run([sys.executable,'-m','content_extractor','extract','--url','bad'],capture_output=True,text=True,encoding='utf-8',timeout=15)
        self.assertEqual(out.returncode,64)
        self.assertEqual(json.loads(out.stdout)['status'],'error')

    def test_summary_invalid_arguments_are_readable(self):
        out=subprocess.run([sys.executable,'-m','content_extractor','summary','--unknown'],capture_output=True,text=True,encoding='utf-8',timeout=15)
        self.assertEqual(out.returncode,64)
        self.assertIn('Conclusion:',out.stdout)
        self.assertNotIn('schema_version',out.stdout)

    def test_missing_model_live_summary_is_readable(self):
        out=subprocess.run([sys.executable,'-m','content_extractor','summary','--url','https://www.instagram.com/p/DfbNjF_tqQo/','--model-dir','absent-model-for-test'],capture_output=True,text=True,encoding='utf-8',timeout=15)
        self.assertEqual(out.returncode,69)
        self.assertIn('Local medium model weights are unavailable',out.stdout)
        self.assertIn('Conclusion:',out.stdout)

    def test_saved_limitations_are_not_hidden_by_success(self):
        from content_extractor.presentation import render_summary
        r=self.fixture();warning='Speech recognition confidence is low; proper names may be wrong.'
        r['coverage']['limitations']=[warning]
        out=render_summary(r)
        self.assertIn(warning,out)
        self.assertIn('Limitations:',out)

if __name__=='__main__':unittest.main()
