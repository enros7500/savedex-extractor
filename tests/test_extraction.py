import unittest
from savedex_extractor.extraction import validate_draft, draft_schema

class GroundingTests(unittest.TestCase):
    def draft(self):return {'topic_category':'software_tools','topic_label':'Tool','items':[{'type':'tool','name':'RealTool','content':'Organize notes','source_id':'t1','quote':'RealTool organizes notes.','url':None,'collection':'tools'}],'collections':[{'id':'tools','label':'Tools','kind':'other','expected_count':None,'count_quote':None,'count_source_id':None}],'sufficient':True,'gaps':[]}
    def test_hallucinated_entity_or_quote_rejected(self):
        sources={'t1':'RealTool organizes notes.'}
        validate_draft(self.draft(),sources)
        d=self.draft();d['items'][0]['name']='InventedTool'
        with self.assertRaises(ValueError):validate_draft(d,sources)
        d=self.draft();d['items'][0]['quote']='This sentence was never said.'
        with self.assertRaises(ValueError):validate_draft(d,sources)
    def test_url_cannot_come_from_model_memory(self):
        d=self.draft();d['items'][0]['url']='https://realtool.example/'
        with self.assertRaises(ValueError):validate_draft(d,{'t1':'RealTool organizes notes.'})
    def test_expected_count_needs_actual_announcement(self):
        d=self.draft();d['collections'][0].update(expected_count=5,count_quote='RealTool organizes notes.',count_source_id='t1')
        with self.assertRaises(ValueError):validate_draft(d,{'t1':'RealTool organizes notes.'})
    def test_numbered_companies_are_generic_and_grounded(self):
        from savedex_extractor.extraction import extract_patterns
        sources={'d1':'Two companies to apply to now.','t1':'Here are two companies. Number one is AlphaWorks. It is remote. Number two is BetaLabs. Try this job board later.'}
        d=extract_patterns(sources)
        validate_draft(d,sources)
        self.assertEqual([i['name'] for i in d['items']],['AlphaWorks','BetaLabs'])
        self.assertEqual(d['collections'][0]['expected_count'],2)
    def test_announcement_does_not_invent_names(self):
        from savedex_extractor.extraction import extract_patterns
        d=extract_patterns({'d1':'Five companies to apply to now! #jobs'})
        self.assertEqual(d['items'],[]);self.assertFalse(d['sufficient'])
    def test_tool_steps_are_not_specific_to_either_reel(self):
        from savedex_extractor.extraction import extract_patterns
        sources={'t1':'We built NotebookX. Type your username. Choose a template. Publish it to your page.'}
        d=extract_patterns(sources);validate_draft(d,sources)
        self.assertEqual(d['items'][0]['name'],'NotebookX')
        self.assertEqual([i['type'] for i in d['items']],['tool','step','step','step'])
    def test_company_list_without_apply_intent_is_not_career_advice(self):
        from savedex_extractor.extraction import extract_patterns
        self.assertIsNone(extract_patterns({'t1':'These are two companies that went bankrupt. One is Acme. Two is Beta.'}))
    def test_patterns_respect_language_and_defer_custom_requests(self):
        from savedex_extractor.extraction import extract_patterns
        sources={'t1':'Two companies to apply to. One is Acme. Two is Beta.'}
        d=extract_patterns(sources,language='en')
        self.assertEqual(d['items'][0]['content'],'Apply to Acme.')
        self.assertIsNone(extract_patterns(sources,instructions='Only extract a tool, omit the companies.'))
    def test_github_hint_never_blocks_model_after_audio(self):
        from savedex_extractor.extraction import extract_patterns
        self.assertIsNone(extract_patterns({'t1':'On GitHub choose a template. Publish your profile.'}))
    def test_tool_procedure_preserves_source_order_and_localizes_actions(self):
        from savedex_extractor.extraction import extract_patterns
        source={'t1':'We built NotebookX. Choose a template. Type your username. Publish it.'}
        d=extract_patterns(source,language='en')
        self.assertTrue(d['items'][1]['content'].startswith('Choose'))
        self.assertTrue(d['items'][2]['content'].startswith('Type'))
        d=extract_patterns(source,language='es')
        self.assertTrue(d['items'][1]['content'].startswith('Elegir'))
        self.assertTrue(d['items'][2]['content'].startswith('Introducir'))
        self.assertTrue(d['items'][3]['content'].startswith('Publicar'))

if __name__=='__main__':unittest.main()
