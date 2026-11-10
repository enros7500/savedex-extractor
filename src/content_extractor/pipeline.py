import os,sys,json,time,subprocess,hashlib,gc,re
from pathlib import Path
from .contracts import empty_result,validate_result
from .extraction import validate_draft,norm,extract_patterns
from .adapters import obtain,download_asset
from .models import local_text_runtime,extract_text,CapabilityUnavailable

def operation(id,purpose,implementation,model=None,inputs=None):
    return {'id':id,'purpose':purpose,'deployment':'local','compute_target':'cpu' if purpose in ['asr','extraction','vision'] else 'not_applicable','implementation':implementation,'model':model,'version':None,'recipient':None,'input_data':inputs or []}
def fact(value=None,ids=None,reason=None):return {'value':value,'certainty':'known' if value else 'unknown','evidence_ids':ids or [] if value else [],'reason':reason if value else 'No sufficiently supported explicit value was extracted.'}
def issue(code,stage,message):return {'code':code,'stage':stage,'severity':'warning','message':message,'affected_asset_ids':[],'affected_item_ids':[],'retryable':False}
def literal_mentions(quote):
    """Only explicit field labels; no geocoding or identity inference."""
    found={}
    for field,labels in [('address_mentioned','address|dirección|direccion'),('location_mentioned','location|ubicación|ubicacion'),('brand_mentioned','brand|marca'),('price_mentioned','price|precio')]:
        m=re.search(r'\b(?:'+labels+r')\s*:\s*([^;\n]+)',quote,re.I)
        if m:found[field]=m[1].strip()
    c=re.search(r'\b(?:coordinates|coordenadas)\s*:\s*([+-]?\d{1,3}(?:\.\d+)?\s*,\s*[+-]?\d{1,3}(?:\.\d+)?)',quote,re.I)
    if c:found['coordinates_mentioned']=c[1]
    m=re.search(r'\b(?:maps?|mapa|enlace del mapa)\s*:\s*(https?://[^\s;]+)',quote,re.I)
    if m:found['maps_url_mentioned']=m[1].rstrip('.,')
    return found
def assemble_result(request,bundle,sources,draft,operations,processed,metrics,extra_gaps=None,visual_positions=None):
    validate_draft(draft,{key:v['text'] for key,v in sources.items()})
    r=empty_result(request);r['issues']=[];r['status']='success'
    assets=[{k:a[k] for k in ['id','index','kind','duration_ms','available','processed']} for a in bundle['assets']]
    for a in assets:a['processed']=a['id'] in processed
    r['source'].update(canonical_url=bundle['canonical_url'],platform=bundle['platform'],post_id=bundle['post_id'],publisher_author=bundle['author'],assets=assets,inventory_complete=bundle['inventory_complete'] and bool(assets),asset_count=len(assets) if assets and bundle['inventory_complete'] else None,media_kind=('carousel' if len(assets)>1 and all(a['kind']=='image' for a in assets) else 'mixed' if len(assets)>1 else assets[0]['kind'] if assets else 'unknown'))
    pattern_only=not metrics.get('llm_calls')
    r['processing']['operations']=[operation('op_access','acquisition','anonymous-platform-adapter',inputs=['url']),*operations,operation('op_extract','extraction','grounded-patterns-v1' if pattern_only else 'grounded-patterns-and-ollama','qwen2.5:3b' if not pattern_only else None,['description','transcript'])]
    r['evidence']=[]
    for id,s in sources.items():
        loc={'kind':'post','asset_id':None,'time':None} if s['kind']=='author_description' else {'kind':'video_time' if s['start_ms'] is not None else 'image_asset','asset_id':s['asset_id'],'time':{'start_ms':s['start_ms'],'end_ms':s['end_ms']} if s['start_ms'] is not None else None}
        r['evidence'].append({'id':id,'source_type':s['kind'],'method':{'author_description':'adapter','transcript':'local_asr','image_text':'local_ocr'}[s['kind']],'excerpt':s['text'],'language':s.get('language'),'locator':loc,'region':None,'asset_sha256':s.get('sha256'),'operation_id':s.get('operation_id','op_access')})
    r['items']=[];mapping={};seen=set()
    for index,d in enumerate(draft['items'],1):
        duplicate=(d['type'],norm(d['name'] or d['content']))
        if duplicate in seen:continue
        seen.add(duplicate);id='item'+str(index);eid=d['source_id'];eids=list(dict.fromkeys([eid,*d.get('context_source_ids',[])]))
        name=fact(d['name'],eids);content=fact(d['content'],eids,reason='Paraphrase of the cited evidence.');unknown=fact()
        if d['type']=='tool':data={'name':name,'purpose':content,'url_mentioned':fact(d['url'],eids)}
        elif d['type']=='place':data={'name':name,'location_mentioned':fact(),'address_mentioned':fact(),'coordinates_mentioned':fact(),'maps_url_mentioned':fact(d['url'],eids) if d['url'] and any(x in d['url'].lower() for x in ['maps.','/maps','goo.gl/maps']) else fact()}
        elif d['type']=='recommendation':data={'action':content,'audience':fact(),'rationale':fact()}
        elif d['type']=='step':data={'action':content,'prerequisites':fact()}
        elif d['type']=='travel_option':data={'label':name if d['name'] else content,'description':content,'location_mentioned':fact(),'exact_place_identified':False}
        elif d['type']=='product':data={'name_or_description':name if d['name'] else content,'brand_mentioned':fact(),'price_mentioned':fact()}
        else:data={'label':d['name'] or 'Information','content':content}
        for key,value in literal_mentions(d['quote']).items():
            if key in data:data[key]=fact(value,[eid],reason='Literal mention from the content; not externally verified.')
        r['items'].append({'id':id,'type':d['type'],'title':d['name'] or d['content'],'summary':d['content'],'attribution':{'publisher_author':bundle['author'],'speaker':None,'basis':'publisher_only','evidence_ids':[]},'evidence_ids':eids,'uncertainties':[],'data':data})
        mapping.setdefault(d['collection'],[]).append(id)
        if d['type']=='tool' and d['name'] and not d['url']:
            r['follow_up']['research_opportunities'].append({'id':'research_'+id,'item_id':id,'kind':'official_website','reason':'No URL was extracted; the consumer may research it separately.','evidence_ids':eids})
        if d['type']=='place' and d['name']:
            r['follow_up']['research_opportunities'].append({'id':'research_'+id,'item_id':id,'kind':'geolocation','reason':'The consuming application may research identity or location without changing the original mention.','evidence_ids':eids})
    r['collections']=[];gaps=list(extra_gaps or [])
    for c in draft['collections']:
        itemids=mapping.get(c['id'],[])
        if not itemids:continue
        expected=c['expected_count'];missing=max(0,expected-len(itemids)) if expected else None
        types={i['type'] for i in r['items'] if i['id'] in itemids}
        kind={'step':'ordered_steps','recommendation':'recommendations','place':'places','travel_option':'choices','product':'products','tool':'other','custom':'other'}.get(next(iter(types)),'other') if len(types)==1 else 'other'
        r['collections'].append({'id':c['id'],'label':c['label'],'kind':kind,'item_ids':itemids,'expected_count':expected,'expected_count_evidence_ids':[c['count_source_id']] if expected else [],'order_semantics':'procedure' if kind=='ordered_steps' else 'presentation','missing_count':missing})
        if missing:gaps.append({'kind':'missing_announced_item','reason':str(missing)+' announced items were not recovered.','evidence_ids':[c['count_source_id']],'asset_ids':[]})
    for gap in draft['gaps']:
        if not any(x in gap.casefold() for x in ['url','website','dirección','coordenad','price','precio','map','official link']):gaps.append({'kind':'transcription_uncertain','reason':gap,'evidence_ids':[],'asset_ids':[]})
    if not draft['sufficient'] and not gaps:gaps.append({'kind':'transcription_uncertain','reason':'The reviewed sources do not sufficiently support the request.','evidence_ids':[],'asset_ids':[]})
    if any(d['type'] in ['tool','place'] and not d['name'] for d in draft['items']):gaps.append({'kind':'ambiguous_identity','reason':'The entity name was not identified in the content.','evidence_ids':[],'asset_ids':[]})
    r['follow_up']['extraction_gaps']=[{'id':'gap'+str(i),'item_id':None,'field':None,'kind':g['kind'],'reason':g['reason'],'required_for_request':True,'evidence_ids':g['evidence_ids'],'asset_ids':g['asset_ids']} for i,g in enumerate(gaps,1)]
    used=list(dict.fromkeys(eid for i in r['items'] for eid in i['evidence_ids'])) or list(sources)[:1]
    r['topic']={'category':draft['topic_category'],'label':draft['topic_label'] or 'Undetermined topic','basis':'inferred' if used else 'unknown','certainty':'uncertain' if used else 'unknown','evidence_ids':used,'reason':'Local classification of the reviewed content; not external verification.'}
    transcript_ranges=[{'asset_id':a['id'],'time':{'start_ms':0,'end_ms':a['duration_ms']}} for a in assets if a['id'] in processed and a['kind']=='video' and any(s['kind']=='transcript' and s['asset_id']==a['id'] for s in sources.values())]
    r['coverage'].update(scope='reviewed_sources_only',sufficiency='insufficient' if gaps else 'sufficient',examined_asset_ids=[a['id'] for a in assets if a['processed']],unexamined_asset_ids=[a['id'] for a in assets if not a['processed']],transcript_ranges=transcript_ranges,visual_positions=visual_positions or [],missing_information=[g['reason'] for g in gaps],limitations=['Reviewed sources only; identities, locations, and links have not been verified.'])
    r['extensions']={'runtime:metrics':metrics}
    if gaps:
        r['status']='partial' if r['items'] else 'error'
        r['issues']=[issue('INCOMPLETE_COLLECTION' if any(g['kind']=='missing_announced_item' for g in gaps) else 'EXTRACTION_FAILED','extraction','; '.join(g['reason'] for g in gaps)[:1000])]
        if not r['items']:r['issues'][0]['severity']='error'
    validate_result(r);return r

def transcribe(path,model_dir,job,asset):
    output=Path(job)/(asset['id']+'-asr.json');t=time.perf_counter()
    proc=subprocess.run([sys.executable,'-m','content_extractor.asr',str(path),str(model_dir),str(output)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if proc.returncode or not output.is_file():raise CapabilityUnavailable('Local CPU transcription failed')
    result=json.loads(output.read_text(encoding='utf-8'));result['subprocess_seconds']=time.perf_counter()-t;return result

def ocr_asset(path,asset):
    from rapidocr_onnxruntime import RapidOCR
    import cv2
    engine=RapidOCR(intra_op_num_threads=4,inter_op_num_threads=1);frames=[]
    if asset['kind']=='image':
        frame=cv2.imdecode(__import__('numpy').frombuffer(Path(path).read_bytes(),dtype='uint8'),cv2.IMREAD_COLOR)
        if frame is not None:frames=[(None,frame)]
    else:
        cap=cv2.VideoCapture(str(path));duration=asset['duration_ms'] or 0
        for i in range(24):
            at=round(duration*i/24);cap.set(cv2.CAP_PROP_POS_MSEC,at);ok,frame=cap.read()
            if ok:frames.append((min(round(cap.get(cv2.CAP_PROP_POS_MSEC)),duration),frame))
        cap.release()
    texts=[];positions=[]
    for at,frame in frames:
        result,_=engine(frame);text='\n'.join(row[1] for row in result or [] if row[2]>=.65)
        positions.append({'asset_id':asset['id'],'time':None if at is None else {'start_ms':at,'end_ms':at}})
        if text:texts.append((at,text,hashlib.sha256(cv2.imencode('.png',frame)[1].tobytes()).hexdigest()))
    return texts,positions

def run_pipeline(request,model_dir,job,log,checkpoint=None):
    start=time.perf_counter();metrics={};bundle=obtain(request['url'],job);metrics['acquisition_seconds']=time.perf_counter()-start
    sources={};operations=[];processed=[];positions=[];gaps=[];remaining=250*1024**2
    if bundle['description'].strip():sources['d1']={'text':bundle['description'],'kind':'author_description','asset_id':None,'start_ms':None,'end_ms':None,'language':None}
    from contextlib import ExitStack
    with ExitStack() as stack:
        runtime=None
        log('description','Analyzing the author description')
        draft=None
        def extract():
            nonlocal runtime
            begin=time.perf_counter()
            texts={k:s['text'] for k,s in sources.items()}
            patterned=extract_patterns(texts,request['instructions'],request['output_language'],description_only=all(s['kind']=='author_description' for s in sources.values()))
            if patterned is not None:
                validate_draft(patterned,texts)
                metrics['pattern_calls']=metrics.get('pattern_calls',0)+1
                metrics['text_extraction_seconds']=metrics.get('text_extraction_seconds',0)+time.perf_counter()-begin
                return patterned
            if runtime is None:runtime=stack.enter_context(local_text_runtime(job))
            port,model=runtime
            feedback=None
            for attempt in range(2):
                try:
                    metrics['llm_calls']=metrics.get('llm_calls',0)+1
                    value=extract_text(port,model,{k:s['text'] for k,s in sources.items()},request['instructions'],request['output_language'],feedback)
                    metrics['text_extraction_seconds']=metrics.get('text_extraction_seconds',0)+time.perf_counter()-begin
                    return value
                except (ValueError,KeyError) as e:
                    feedback=str(e)+'. Use only literal source names, valid collection IDs and explicit counts, or abstain.'
                    if attempt:raise ValueError('Local extraction could not produce grounded evidence')
        if sources:
            try:draft=extract()
            except ValueError:
                log('description_insufficient','The description did not support a grounded extraction; other sources will be evaluated.')
        need_more=not draft or not draft['sufficient'] or not draft['items'] or any(c['expected_count'] and sum(i['collection']==c['id'] for i in draft['items'])<c['expected_count'] for c in draft['collections']) or (draft['topic_category']=='software_tools' and not any(i['type']=='tool' and i['name'] for i in draft['items']))
        if checkpoint and draft and draft['items']:
            checkpoint(assemble_result(request,bundle,sources,draft,operations,processed,metrics,[{'kind':'unread_content','reason':'Required sources have not finished processing.','evidence_ids':[],'asset_ids':[]}] if need_more else []))
        paths={}
        if need_more:
            for asset in bundle['assets']:
                if asset['kind']!='video':continue
                try:
                    path,size=download_asset(asset,bundle['platform'],job,remaining);remaining-=size;paths[asset['id']]=path
                    log('transcription','Transcribing audio locally with medium on CPU')
                    a=transcribe(path,model_dir,job,asset);asset['duration_ms']=a['duration_ms'];processed.append(asset['id'])
                    opid='op_asr_'+asset['id'];operations.append(operation(opid,'asr','faster-whisper','Systran/faster-whisper-medium',['audio']))
                    metrics['asr_seconds']=metrics.get('asr_seconds',0)+a['asr_seconds'];metrics['asr_load_seconds']=metrics.get('asr_load_seconds',0)+a['load_seconds']
                    for segment in a.get('sentences',a['segments']):
                        sid='t'+str(sum(s['kind']=='transcript' for s in sources.values())+1)
                        sources[sid]={'text':segment['text'],'kind':'transcript','asset_id':asset['id'],'start_ms':segment['start_ms'],'end_ms':segment['end_ms'],'language':a['language'],'operation_id':opid}
                except (OSError,ValueError,CapabilityUnavailable):gaps.append({'kind':'unread_content','reason':'A required audio track could not be retrieved or transcribed.','evidence_ids':[],'asset_ids':[asset['id']]})
            if sources:draft=extract()
            if checkpoint and draft and draft['items']:checkpoint(assemble_result(request,bundle,sources,draft,operations,processed,metrics,gaps))
        visual_needed=any(a['kind']=='image' for a in bundle['assets']) and (need_more or not draft or not draft['sufficient']) or not draft or not draft['sufficient']
        if draft and any(c['expected_count'] and sum(i['collection']==c['id'] for i in draft['items'])<c['expected_count'] for c in draft['collections']):visual_needed=True
        if visual_needed:
            if request['visual_processing']=='disabled':gaps.append({'kind':'unread_content','reason':'The content requires images, but visual processing is disabled in the request.','evidence_ids':[],'asset_ids':[a['id'] for a in bundle['assets']]})
            else:
                log('ocr','Reading on-screen text with local OCR; no non-textual visual model is configured')
                for asset in bundle['assets']:
                    try:
                        path=paths.get(asset['id'])
                        if path is None:path,size=download_asset(asset,bundle['platform'],job,remaining);remaining-=size
                        texts,pp=ocr_asset(path,asset);positions.extend(pp)
                        if asset['id'] not in processed:processed.append(asset['id'])
                        opid='op_ocr_'+asset['id'];operations.append(operation(opid,'vision','rapidocr_onnxruntime',inputs=['images']))
                        for at,text,sha in texts:
                            sid='v'+str(sum(s['kind']=='image_text' for s in sources.values())+1)
                            sources[sid]={'text':text,'kind':'image_text','asset_id':asset['id'],'start_ms':at,'end_ms':at,'language':None,'sha256':sha,'operation_id':opid}
                    except (ImportError,OSError,ValueError):gaps.append({'kind':'unread_content','reason':'A required image could not be read using local OCR.','evidence_ids':[],'asset_ids':[asset['id']]})
                if sources:draft=extract()
                if not draft or not draft['sufficient']:gaps.append({'kind':'unread_content','reason':'Non-textual visual understanding may be required; no local VLM is configured.','evidence_ids':[],'asset_ids':[a['id'] for a in bundle['assets']]})
        if not draft:raise CapabilityUnavailable('No text evidence usable for local extraction')
    metrics['total_worker_seconds']=time.perf_counter()-start
    result=assemble_result(request,bundle,sources,draft,operations,processed,metrics,gaps,positions)
    result['routing']['initial_choice']='visual_first' if all(a['kind']=='image' for a in bundle['assets']) else 'text_first' if need_more else 'description_only'
    result['routing']['steps']=[{'stage':'description','outcome':'completed' if 'd1' in sources else 'skipped','reason':'Description retrieved anonymously.' if 'd1' in sources else 'No usable description.','input_evidence_ids':['d1'] if 'd1' in sources else [],'remaining_gaps':[]}, {'stage':'transcription','outcome':'completed' if any(s['kind']=='transcript' for s in sources.values()) else 'skipped','reason':'Medium on CPU was used when audio was needed; images were skipped when textual extraction was considered sufficient.','input_evidence_ids':[k for k,s in sources.items() if s['kind']=='transcript'],'remaining_gaps':[]}, {'stage':'extraction','outcome':'completed','reason':'Local extraction with checked quotations; no research.','input_evidence_ids':list(sources),'remaining_gaps':result['coverage']['missing_information']}]
    validate_result(result);return result
