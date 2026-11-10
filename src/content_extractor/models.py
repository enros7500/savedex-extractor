import os,json,time,socket,subprocess,http.client,shutil
from pathlib import Path
from contextlib import contextmanager

class CapabilityUnavailable(RuntimeError):pass
def ollama_request(port,path,payload=None,timeout=120):
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=timeout)
    try:
        conn.request('POST' if payload is not None else 'GET',path,body=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json'})
        r=conn.getresponse();body=r.read(4_000_000)
        if r.status!=200:raise CapabilityUnavailable('Local text runtime request failed')
        return json.loads(body)
    finally:conn.close()
@contextmanager
def local_text_runtime(job):
    binary=shutil.which('ollama')
    if not binary:
        known=Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe'
        if known.is_file():binary=str(known)
    if not binary:raise CapabilityUnavailable('Ollama is not installed locally')
    with socket.socket() as reserve:reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
    env={**os.environ,'OLLAMA_HOST':f'127.0.0.1:{port}','OLLAMA_NO_CLOUD':'1','OLLAMA_KEEP_ALIVE':'0','OLLAMA_NUM_PARALLEL':'1','OLLAMA_MAX_LOADED_MODELS':'1'}
    stderr=(Path(job)/'text-runtime.log').open('wb')
    process=subprocess.Popen([binary,'serve'],env=env,stdout=subprocess.DEVNULL,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        for _ in range(80):
            if process.poll() is not None:raise CapabilityUnavailable('Local runtime could not start')
            try:tags=ollama_request(port,'/api/tags',timeout=1);break
            except (OSError,CapabilityUnavailable):time.sleep(.25)
        else:raise CapabilityUnavailable('Local runtime did not become ready')
        model='qwen2.5:3b'
        if not any(m.get('name',m.get('model'))==model for m in tags.get('models',[])):raise CapabilityUnavailable('Preinstalled local qwen2.5:3b model is required; no download performed')
        yield port,model
    finally:
        import psutil
        try:
            parent=psutil.Process(process.pid);children=parent.children(recursive=True)
            for child in reversed(children):
                try:child.terminate()
                except psutil.Error:pass
            parent.terminate();psutil.wait_procs([parent,*children],timeout=3)
            for p in [parent,*children]:
                try:
                    if p.is_running():p.kill()
                except psutil.Error:pass
        except psutil.Error:pass
        stderr.close()
def extract_text(port,model,sources,instructions,language,feedback=None):
    import copy
    from .extraction import SYSTEM,draft_schema,validate_draft
    prompt=json.dumps({'output_language':language,'request':instructions or 'Extract the useful main-topic information.','sources':sources,'validation_feedback':feedback},ensure_ascii=False)
    if len(prompt)>24000:raise CapabilityUnavailable('Text exceeds the configured local extraction context budget')
    constrained=copy.deepcopy(draft_schema)
    item=constrained['properties']['items']['items']['properties']
    item['source_id']={'enum':list(sources)}
    item['quote']={'enum':list(dict.fromkeys(sources.values()))}
    item['context_source_ids']['items']={'enum':list(sources)}
    import re
    from .extraction import NUMBERS
    count_values=[]
    number_words='|'.join(NUMBERS)
    announcement=re.compile(r'\b(\d+|'+number_words+r')\s+(?:companies|things|tips|steps|recommendations|restaurants|places|options|souvenirs|empresas|cosas|consejos|pasos|recomendaciones|restaurantes|sitios|opciones)\b',re.I)
    for source in sources.values():
        for m in announcement.finditer(source):
            n=int(m[1]) if m[1].isdigit() else NUMBERS[m[1].lower()]
            if 1<=n<=100:count_values.append(n)
    constrained['properties']['collections']['items']['properties']['expected_count']={'enum':[None,*sorted(set(count_values))]}
    response=ollama_request(port,'/api/generate',{'model':model,'system':SYSTEM,'prompt':prompt,'format':constrained,'stream':False,'keep_alive':0,'options':{'num_gpu':0,'num_thread':6,'num_ctx':8192,'num_predict':2800,'temperature':0,'seed':42}},timeout=300)
    draft=json.loads(response['response']);validate_draft(draft,sources)
    return draft
