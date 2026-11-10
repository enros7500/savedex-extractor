import sys,os,time,json
from pathlib import Path
from .contracts import empty_result,validate_result
from .models import CapabilityUnavailable

def main():
    job=Path(sys.argv[1]);config=json.loads((job/'job.json').read_text(encoding='utf-8'));request=config['request']
    for _ in range(400):
        if (job/'ready').exists():break
        time.sleep(.025)
    else:return 70
    def log(event,message):
        if config['quiet']:return
        if config['log_format']=='jsonl':line=json.dumps({'level':'info','event':event,'request_id':request['request_id'],'message':message},ensure_ascii=False)
        else:line=event+': '+message
        print(line,file=sys.stderr,flush=True)
    try:
        # Redirect library Python stdout; parent also discards all native worker stdout.
        from contextlib import redirect_stdout
        from .pipeline import run_pipeline
        def checkpoint(result):
            validate_result(result);temporary=job/'checkpoint.tmp';temporary.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');os.replace(temporary,job/'checkpoint.json')
        with redirect_stdout(sys.stderr):r=run_pipeline(request,Path(config['model_dir']),job,log,checkpoint)
        code={'success':0,'partial':2,'error':65}[r['status']]
    except CapabilityUnavailable:
        r=empty_result(request,'EXTRACTION_FAILED','extraction','A required local capability is unavailable; run doctor.');code=69
    except OSError:
        r=empty_result(request,'ACCESS_UNAVAILABLE','access','Public content could not be retrieved anonymously.');code=65
    except ValueError as e:
        r=empty_result(request,'EXTRACTION_FAILED','extraction','Local extraction could not produce an evidence-backed result.');code=65
        log('grounding_failure',str(e)[:200])
    except Exception as e:
        r=empty_result(request,'EXTRACTION_FAILED','extraction','Internal extraction error.');code=70
        log('internal_failure',type(e).__name__)
    if code not in (0,2):
        from .cli import recover_checkpoint
        error=r['issues'][0]
        recovered=recover_checkpoint(job,error['code'],error['stage'],'A later stage failed; the previously validated extraction is retained. '+error['message'])
        if recovered:r=recovered;code=2
    try:validate_result(r)
    except ValueError:r=empty_result(request,'VALIDATION_FAILED','validation','The result did not pass validation.');code=70
    tmp=job/'result.tmp';tmp.write_text(json.dumps(r,ensure_ascii=False),encoding='utf-8');os.replace(tmp,job/'result.json')
    return code
if __name__=='__main__':raise SystemExit(main())
