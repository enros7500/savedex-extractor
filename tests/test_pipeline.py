import unittest,tempfile,json,sys
from unittest.mock import patch
from pathlib import Path
from savedex_extractor.pipeline import assemble_result
from savedex_extractor.contracts import normalize_request,validate_result

class PipelineTests(unittest.TestCase):
    def test_literal_location_mentions_are_not_geocoded(self):
        from savedex_extractor.pipeline import literal_mentions
        text='Demo Cafe; Address: Calle de muestra 12; Coordinates: 40.0, -3.0; Maps: https://maps.example/demo'
        fields=literal_mentions(text)
        self.assertEqual(fields['address_mentioned'],'Calle de muestra 12')
        self.assertEqual(fields['coordinates_mentioned'],'40.0, -3.0')
        self.assertEqual(fields['maps_url_mentioned'],'https://maps.example/demo')
        self.assertEqual(literal_mentions('Demo Cafe is lovely.'),{})
    def test_partial_list_not_padded_and_missing_url_not_gap(self):
        request=normalize_request({'schema_version':'3.0.0','request_id':'test','url':'https://www.instagram.com/p/ABCDEFGHIJK/'})
        bundle={'platform':'instagram','post_id':'ABCDEFGHIJK','canonical_url':request['url'],'author':'author','assets':[],'inventory_complete':True}
        source={'d1':{'text':'Five choices: First and Second.','kind':'author_description','asset_id':None,'start_ms':None,'end_ms':None,'language':'en'}}
        draft={'topic_category':'career','topic_label':'Choices','items':[{'type':'recommendation','name':'First','content':'First','source_id':'d1','quote':'First','url':None,'collection':'list'},{'type':'recommendation','name':'Second','content':'Second','source_id':'d1','quote':'Second','url':None,'collection':'list'}],'collections':[{'id':'list','label':'Five choices','kind':'recommendations','expected_count':5,'count_source_id':'d1','count_quote':'Five choices'}],'sufficient':True,'gaps':[]}
        r=assemble_result(request,bundle,source,draft,[],[],{})
        validate_result(r)
        self.assertEqual(r['status'],'partial');self.assertEqual(len(r['items']),2);self.assertEqual(r['collections'][0]['missing_count'],3)
        draft['collections'][0].update(expected_count=None,count_quote=None,count_source_id=None)
        draft['topic_category']='software_tools';draft['items']=draft['items'][:1];draft['items'][0].update(type='tool')
        r=assemble_result(request,bundle,source,draft,[],[],{})
        validate_result(r);self.assertEqual(r['status'],'success');self.assertIsNone(r['items'][0]['data']['url_mentioned']['value'])
        self.assertEqual(r['collections'][0]['kind'],'other')
        from savedex_extractor.cli import recover_checkpoint
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'checkpoint.json').write_text(json.dumps(r),encoding='utf-8')
            recovered=recover_checkpoint(Path(folder))
            validate_result(recovered)
            self.assertEqual(recovered['status'],'partial')
            self.assertEqual(len(recovered['items']),1)
            self.assertEqual(recovered['issues'][-1]['code'],'RESOURCE_LIMIT')
            from savedex_extractor.worker import main
            folder=Path(folder);(folder/'ready').touch()
            (folder/'job.json').write_text(json.dumps({'request':request,'model_dir':'unused','quiet':True,'log_format':'jsonl'}),encoding='utf-8')
            def failed_phase(request,model,job,log,checkpoint):
                checkpoint(r);raise ValueError('Later extraction phase failed')
            with patch.object(sys,'argv',['worker',str(folder)]),patch('savedex_extractor.pipeline.run_pipeline',side_effect=failed_phase):code=main()
            self.assertEqual(code,2)
            body=json.loads((folder/'result.json').read_text(encoding='utf-8'))
            self.assertEqual(len(body['items']),1);self.assertEqual(body['status'],'partial')

if __name__=='__main__':unittest.main()
