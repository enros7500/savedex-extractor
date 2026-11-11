import unittest
from savedex_extractor.contracts import normalize_request, empty_result, validate_result

class ContractTests(unittest.TestCase):
    def test_defaults_and_research_rejected(self):
        r=normalize_request({'schema_version':'3.0.0','request_id':'test','url':'https://www.instagram.com/p/DfbNjF_tqQo/'})
        self.assertEqual(r['task'],'extract')
        with self.assertRaises(ValueError):normalize_request({**r,'external_fallback':{'web_enrichment':True}})
    def test_error_is_schema_valid(self):
        r=empty_result(None,'INVALID_REQUEST','input','Invalid request')
        validate_result(r)
        self.assertEqual(r['source']['input_url'],'<unavailable>')
    def test_missing_evidence_rejected(self):
        r=empty_result(None,'INVALID_REQUEST','input','Invalid request')
        r['topic']['evidence_ids']=['missing']
        with self.assertRaises(ValueError):validate_result(r)

if __name__=='__main__':unittest.main()
