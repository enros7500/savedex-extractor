import argparse,sys,os,json,uuid,tempfile,time,queue,threading,shutil
from pathlib import Path
from . import __version__
from .contracts import normalize_request,empty_result,validate_result
from .supervisor import ModelLock,Busy,run_supervised,clean_job,reap_abandoned_jobs

class UsageError(ValueError):pass
class Parser(argparse.ArgumentParser):
    def error(self,message):raise UsageError('Invalid command line; use --help')
def emit(result,code,readable=False):
    from .presentation import render_summary
    validate_result(result)
    print(render_summary(result) if readable else json.dumps(result,ensure_ascii=False),flush=True)
    return code
def parser():
    p=Parser(prog='content-extractor',description='Extract publication content locally, or print a readable summary.');p.add_argument('--version',action='store_true');p.add_argument('--json',action='store_true')
    sub=p.add_subparsers(dest='command',parser_class=Parser)
    for name in ['extract','summary','doctor']:
        s=sub.add_parser(name);s.add_argument('--model-dir',default=os.environ.get('CONTENT_EXTRACTOR_MODEL_DIR',str(Path(__file__).resolve().parents[1]/'models/medium')))
        s.add_argument('--work-dir',default=os.environ.get('CONTENT_EXTRACTOR_WORK_DIR',str(Path(tempfile.gettempdir())/'content-extractor')))
        if name=='doctor':s.add_argument('--json',action='store_true');continue
        modes=s.add_mutually_exclusive_group(required=True);modes.add_argument('--request');modes.add_argument('--url')
        if name=='summary':modes.add_argument('--result',help='Summarize a saved result JSON without processing media again')
        for flag in ['request-id','instructions','output-language','visual-processing']:s.add_argument('--'+flag)
        s.add_argument('--timeout-seconds',type=float,default=600);s.add_argument('--log-format',choices=['text','jsonl'],default='text');s.add_argument('--quiet',action='store_true')
    return p
def model_ready(path):return all((path/name).is_file() for name in ['model.bin','config.json','tokenizer.json','vocabulary.txt'])
def text_ready():
    binary=shutil.which('ollama') or str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe')
    weights=Path(os.environ.get('OLLAMA_MODELS',str(Path.home()/'.ollama/models')))
    return Path(binary).is_file() and (weights/'manifests/registry.ollama.ai/library/qwen2.5/3b').is_file()
def doctor(args):
    import importlib.util
    model=Path(args.model_dir).resolve();root=Path(args.work_dir).resolve();writable=False
    try:
        root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryFile(dir=root):writable=True
    except OSError:pass
    checks={'asr_model':model_ready(model),'asr_runtime':importlib.util.find_spec('faster_whisper') is not None,'text_model_and_runtime':text_ready(),'work_dir':writable,'ocr':importlib.util.find_spec('rapidocr_onnxruntime') is not None,'visual_understanding':False}
    ready=all(checks[k] for k in ['asr_model','asr_runtime','text_model_and_runtime','work_dir'])
    result={'diagnostic_version':'1.0.0','status':'ready' if ready else 'unavailable','checks':checks,'issues':['Non-textual visual understanding is not configured; OCR alone cannot identify unlabeled objects.']}
    print(json.dumps(result,ensure_ascii=False) if args.json else '\n'.join(k+': '+str(v) for k,v in checks.items()))
    return 0 if ready else 69
def read_stdin(timeout):
    q=queue.Queue()
    def read():
        try:
            chunks=[];size=0
            while True:
                b=os.read(sys.stdin.fileno(),4096)
                if not b:break
                size+=len(b)
                if size>65536:raise ValueError('Request is too large')
                chunks.append(b)
            q.put(b''.join(chunks))
        except BaseException as e:q.put(e)
    threading.Thread(target=read,daemon=True).start()
    try:value=q.get(timeout=timeout)
    except queue.Empty:raise TimeoutError('Input deadline exceeded')
    if isinstance(value,BaseException):raise ValueError('Cannot read input')
    return value
def recover_checkpoint(job,code='RESOURCE_LIMIT',stage='extraction',message=None):
    if job is None:return None
    try:
        r=json.loads((job/'checkpoint.json').read_text(encoding='utf-8'));validate_result(r)
        if not r['items']:return None
        r['status']='partial';r['coverage']['sufficiency']='insufficient'
        reason=message or 'The deadline expired; only previously validated, evidence-backed information is retained.'
        r['coverage']['missing_information'].append(reason)
        r['follow_up']['extraction_gaps'].append({'id':'deadline','item_id':None,'field':None,'kind':'unread_content','reason':reason,'required_for_request':True,'evidence_ids':[],'asset_ids':[]})
        r['issues'].append({'code':code,'stage':stage,'severity':'warning','message':reason,'affected_asset_ids':[],'affected_item_ids':[],'retryable':code=='RESOURCE_LIMIT'})
        validate_result(r);return r
    except (OSError,ValueError,KeyError):return None
def main(argv=None):
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr,'reconfigure'):sys.stderr.reconfigure(encoding='utf-8')
    request=None;job=None;root=None;start=time.perf_counter()
    raw_args=sys.argv[1:] if argv is None else argv
    readable=bool(raw_args and raw_args[0]=='summary')
    def respond(result,code):return emit(result,code,readable)
    try:
        args=parser().parse_args(argv)
        readable=args.command=='summary'
        if args.version:
            info={'cli_interface_version':'1.1.0','package_version':__version__,'supported_content_schema_versions':['3.0.0']}
            print(json.dumps(info) if args.json else 'content-extractor '+__version__);return 0
        if args.command=='doctor':return doctor(args)
        if args.command not in ['extract','summary']:raise UsageError('A command is required')
        if readable and args.result:
            if any(getattr(args,k) is not None for k in ['request_id','instructions','output_language','visual_processing']):raise UsageError('Saved summaries do not accept content options')
            with Path(args.result).open('rb') as handle:raw=handle.read(16*1024**2+1)
            if len(raw)>16*1024**2:raise UsageError('Saved result is too large')
            result=json.loads(raw.decode('utf-8-sig'));validate_result(result)
            return respond(result,{'success':0,'partial':2,'error':65}[result['status']])
        if not 0<args.timeout_seconds<=86400:raise UsageError('Timeout out of range')
        if args.request:
            if any(getattr(args,k) is not None for k in ['request_id','instructions','output_language','visual_processing']):raise UsageError('Do not mix request JSON and content options')
            if args.request=='-':raw=read_stdin(args.timeout_seconds)
            else:
                with Path(args.request).open('rb') as handle:raw=handle.read(65537)
            if len(raw)>65536:raise UsageError('Request too large')
            request=normalize_request(json.loads(raw.decode('utf-8')))
        else:
            value={'schema_version':'3.0.0','request_id':args.request_id or 'cli_'+uuid.uuid4().hex,'url':args.url}
            for key in ['instructions','output_language','visual_processing']:
                if getattr(args,key) is not None:value[key]=getattr(args,key)
            request=normalize_request(value)
        model=Path(args.model_dir).resolve()
        if not model_ready(model):return respond(empty_result(request,'EXTRACTION_FAILED','input','Local medium model weights are unavailable; automatic downloads are disabled.'),69)
        if not text_ready():return respond(empty_result(request,'EXTRACTION_FAILED','input','Ollama and qwen2.5:3b must already be installed locally.'),69)
        root=Path(args.work_dir).resolve();root.mkdir(parents=True,exist_ok=True)
        reap_abandoned_jobs(root)
        with ModelLock(model):
            job=Path(tempfile.mkdtemp(prefix='content-extractor-',dir=root))
            import psutil
            (job/'owner.json').write_text(json.dumps({'pid':os.getpid(),'created_time':psutil.Process().create_time()}),encoding='utf-8')
            (job/'job.json').write_text(json.dumps({'request':request,'model_dir':str(model),'quiet':args.quiet,'log_format':args.log_format}),encoding='utf-8')
            budget=args.timeout_seconds-(time.perf_counter()-start)
            if budget<=0:raise TimeoutError('Deadline exceeded')
            code=run_supervised([sys.executable,'-m','content_extractor.worker',str(job)],job,budget,args.log_format)
            path=job/'result.json'
            if not path.is_file():return respond(empty_result(request,'EXTRACTION_FAILED','extraction','The extraction process ended without a valid result.'),70)
            try:r=json.loads(path.read_text(encoding='utf-8'));validate_result(r)
            except (ValueError,KeyError):return respond(empty_result(request,'VALIDATION_FAILED','validation','The extraction process returned an invalid result.'),70)
            if code not in [0,2,65,69,70,75] or (r['status']=='success')!=(code==0) or (r['status']=='partial')!=(code==2):raise RuntimeError('Worker status mismatch')
            r.setdefault('extensions',{})['runtime:cli_wall_seconds']=time.perf_counter()-start
            return respond(r,code)
    except (UsageError,ValueError,KeyError,UnicodeError):return respond(empty_result(request,'INVALID_REQUEST','input','Invalid request or arguments; use --help and schema 3.0.0.'),64)
    except Busy:return respond(empty_result(request,'RESOURCE_LIMIT','input','Another extraction is using this model environment.'),75)
    except TimeoutError:
        partial=recover_checkpoint(job)
        return respond(partial,2) if partial else respond(empty_result(request,'RESOURCE_LIMIT','extraction','The invocation deadline expired.'),75)
    except KeyboardInterrupt:return respond(empty_result(request,'RESOURCE_LIMIT','extraction','Extraction interrupted.'),130)
    except OSError:return respond(empty_result(request,'EXTRACTION_FAILED','input','A required local resource could not be accessed.'),69)
    except Exception:return respond(empty_result(request,'EXTRACTION_FAILED','extraction','Internal extraction process failure.'),70)
    finally:
        if job and root:
            try:clean_job(job,root)
            except OSError:print('Warning: some application temporary files could not be removed.',file=sys.stderr)
