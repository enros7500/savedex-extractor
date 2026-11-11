import copy,json,uuid
from pathlib import Path
from datetime import datetime,timezone
from functools import lru_cache
from jsonschema import Draft202012Validator,FormatChecker

ROOT=Path(__file__).parent/'schemas'
@lru_cache()
def schema(name):
    value=json.loads((ROOT/name).read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(value)
    return value
def structural(value,name):
    errors=list(Draft202012Validator(schema(name),format_checker=FormatChecker()).iter_errors(value))
    if errors:raise ValueError('JSON does not satisfy the supported '+name)
def normalize_request(value):
    structural(value,'request.json')
    r=copy.deepcopy(value)
    for k,v in {'task':'extract','instructions':'','output_language':'en','processing_profile':'local_baseline_v1','visual_processing':'auto'}.items():r.setdefault(k,v)
    from .network import normalize_url
    r['url']=normalize_url(r['url'])[2]
    return r
def empty_result(request=None,code='EXTRACTION_FAILED',stage='extraction',message='Extraction failed'):
    r=json.loads((ROOT/'error-template.json').read_text(encoding='utf-8'))
    r['generated_at']=datetime.now(timezone.utc).isoformat()
    r['request_id']=(request or {}).get('request_id','cli_'+uuid.uuid4().hex)
    r['source']['input_url']=(request or {}).get('url','<unavailable>')
    if request:
        r['request_context']={k:request[k] for k in ['instructions','output_language','visual_processing']}
    r['issues']=[{'code':code,'stage':stage,'severity':'error','message':message,'affected_asset_ids':[],'affected_item_ids':[],'retryable':code in ['RESOURCE_LIMIT','ACCESS_UNAVAILABLE']}]
    return r
def semantic(r):
    def must(condition,message):
        if not condition:raise ValueError(message)
    def index(xs):
        must(len({x['id'] for x in xs})==len(xs),'Duplicate ID')
        return {x['id']:x for x in xs}
    assets=index(r['source']['assets']);evidence=index(r['evidence']);items=index(r['items']);ops=index(r['processing']['operations']);index(r['collections'])
    def refs(values):must(set(values)<=evidence.keys(),'Evidence reference absent')
    def position(loc):
        must(loc['asset_id'] in assets,'Asset absent')
        asset=assets[loc['asset_id']];t=loc['time']
        if t is None:must(asset['kind']=='image','Image time must be null')
        else:
            must(asset['kind']=='video' and 0<=t['start_ms']<=t['end_ms'],'Invalid video range')
            if asset['duration_ms'] is not None:must(t['end_ms']<=asset['duration_ms']+1,'Range exceeds duration')
    coverage=r['coverage'];seen=set(coverage['examined_asset_ids']);unseen=set(coverage['unexamined_asset_ids'])
    must(not seen&unseen and seen|unseen==assets.keys(),'Invalid coverage inventory')
    if r['source']['inventory_complete']:must(r['source']['asset_count']==len(assets),'Invalid inventory size')
    for p in coverage['transcript_ranges']+coverage['visual_positions']:position(p)
    for e in evidence.values():
        must(e['operation_id'] in ops,'Evidence producer absent');loc=e['locator']
        if loc['kind']!='post':
            position(loc);must(loc['asset_id'] in seen,'Evidence on unexamined asset')
            ranges=coverage['transcript_ranges'] if e['source_type']=='transcript' else coverage['visual_positions']
            must(any(p['asset_id']==loc['asset_id'] and ((p['time'] is None and loc['time'] is None) or (p['time'] and loc['time'] and p['time']['start_ms']<=loc['time']['start_ms']<=loc['time']['end_ms']<=p['time']['end_ms'])) for p in ranges),'Evidence outside coverage')
        if e['region']:
            b=e['region'];must(b['x']+b['width']<=1 and b['y']+b['height']<=1,'Invalid image region')
    refs(r['topic']['evidence_ids'])
    for signal in r['routing']['signals']:refs(signal['evidence_ids'])
    for step in r['routing']['steps']:refs(step['input_evidence_ids'])
    for item in items.values():
        refs(item['evidence_ids']);refs(item['attribution']['evidence_ids'])
        for f in item['data'].values():
            if isinstance(f,dict) and 'certainty' in f:must(set(f['evidence_ids'])<=set(item['evidence_ids']),'Fact lacks item evidence')
        for u in item['uncertainties']:must(set(u['evidence_ids'])<=set(item['evidence_ids']),'Uncertainty lacks evidence')
    for c in r['collections']:
        must(set(c['item_ids'])<=items.keys(),'Collection item absent');refs(c['expected_count_evidence_ids'])
        if c['expected_count'] is None:must(c['missing_count'] is None,'Unknown count must stay unknown')
        else:
            must(bool(c['expected_count_evidence_ids']),'Count lacks evidence')
            must(c['missing_count']==max(0,c['expected_count']-len(c['item_ids'])),'Count mismatch')
            if c['missing_count']:must(r['status']!='success','Incomplete collection called success')
        if c['kind']=='ordered_steps':must(c['order_semantics']=='procedure' and all(items[i]['type']=='step' for i in c['item_ids']),'Invalid procedure')
        if c['kind']=='recommendations':must(c['order_semantics']=='presentation' and all(items[i]['type']=='recommendation' for i in c['item_ids']),'Invalid recommendation collection')
    for op in ops.values():
        must(op['deployment']=='local' and op['recipient'] is None,'External operation prohibited')
        if op['purpose']=='asr':must(op['compute_target']=='cpu','ASR must use CPU')
    for g in r['follow_up']['extraction_gaps']:
        refs(g['evidence_ids']);must(g['item_id'] is None or g['item_id'] in items,'Gap item absent');must(set(g['asset_ids'])<=assets.keys(),'Gap asset absent')
        if g['required_for_request']:must(r['status']!='success','Required gap called success')
    for o in r['follow_up']['research_opportunities']:
        must(o['item_id'] in items,'Opportunity item absent');must(set(o['evidence_ids'])<=set(items[o['item_id']]['evidence_ids']),'Opportunity lacks evidence')
    for issue in r['issues']:must(set(issue['affected_asset_ids'])<=assets.keys() and set(issue['affected_item_ids'])<=items.keys(),'Issue reference absent')
    if r['status']=='success':must(coverage['sufficiency']=='sufficient' and not any(i['severity']=='error' for i in r['issues']),'Invalid success')
def validate_result(value):
    structural(value,'result.json');semantic(value)
