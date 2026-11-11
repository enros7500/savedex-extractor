"""Implementation behind install.cmd. Never invoked by normal extraction."""
import argparse
from contextlib import contextmanager
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
MEDIUM_REVISION = '08e178d48790749d25932bbc082711ddcfdfbc4f'
ASR_REQUIRED = ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt')
TEXT_MODEL = 'qwen2.5:3b'

def make_plan(root):
    return {'project':str(root), 'environment':str(root/'work/asr-venv'), 'models':['medium',TEXT_MODEL]}

def run_checked(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)

def install_environment(root, base_python, ollama):
    (root/'outputs').mkdir(parents=True,exist_ok=True)
    python = root/'work/asr-venv/Scripts/python.exe'
    if not python.is_file():
        print('[1/4] Creating the local Python environment.', flush=True)
        run_checked([base_python,'-m','venv',str(root/'work/asr-venv')],cwd=root)
    else:
        print('[1/4] Reusing the local Python environment.', flush=True)
    print('[2/4] Installing the CLI and local OCR dependencies.', flush=True)
    run_checked([str(python),'-m','pip','install',str(root)+'[ocr]'],cwd=root)
    run_checked([str(python),str(root/'scripts/setup_environment.py'),'--provision','--ollama',ollama],cwd=root)

def medium_ready(root):
    try:
        record=json.loads((root/'work/asr-model-download-medium.json').read_text(encoding='utf-8-sig'))
        sizes={f['name']:f['bytes'] for f in record['files']}
        target=root/'work/models/faster-whisper-medium'
        return record['revision']==MEDIUM_REVISION and all((target/name).is_file() and (target/name).stat().st_size==sizes[name]>0 for name in ASR_REQUIRED)
    except (OSError,ValueError,KeyError,TypeError):
        return False

def tags(port):
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
    try:
        conn.request('GET','/api/tags')
        response=conn.getresponse()
        if response.status!=200:raise RuntimeError('The private Ollama runtime did not return its local models.')
        return json.loads(response.read(4_000_000))['models']
    finally:
        conn.close()

@contextmanager
def private_runtime(root, ollama):
    from savedex_extractor.supervisor import WindowsJob, terminate_tree
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
    env={**os.environ,'OLLAMA_HOST':f'127.0.0.1:{port}','OLLAMA_NO_CLOUD':'1','OLLAMA_KEEP_ALIVE':'0','OLLAMA_NUM_PARALLEL':'1','OLLAMA_MAX_LOADED_MODELS':'1'}
    (root/'work').mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='setup-',dir=root/'work') as temporary:
        with (Path(temporary)/'ollama.log').open('wb') as stderr:
            owned=WindowsJob();process=None
            try:
                process=subprocess.Popen([ollama,'serve'],env=env,stdout=subprocess.DEVNULL,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                owned.assign(process)
                for _ in range(120):
                    if process.poll() is not None:raise RuntimeError('The private Ollama runtime could not start.')
                    try:tags(port);break
                    except (OSError,ValueError,RuntimeError):time.sleep(.25)
                else:raise RuntimeError('The private Ollama runtime did not become ready.')
                yield port,env
            finally:
                if process is not None:
                    terminate_tree(process)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
                owned.close()

def provision_qwen(root, ollama):
    (root/'work').mkdir(parents=True,exist_ok=True)
    with private_runtime(root,ollama) as (port,env):
        current=tags(port)
        if not any(m.get('name',m.get('model'))==TEXT_MODEL for m in current):
            print('[4/4] Downloading Qwen2.5 3B locally. This can take several minutes.',flush=True)
            run_checked([ollama,'pull',TEXT_MODEL],env=env,cwd=root)
            current=tags(port)
        else:
            print('[4/4] Reusing the installed local Qwen2.5 3B model.',flush=True)
        match=next((m for m in current if m.get('name',m.get('model'))==TEXT_MODEL),None)
        if match is None:raise RuntimeError('Qwen2.5 3B is still missing after provisioning.')
        (root/'work/setup-qwen.json').write_text(json.dumps({'model':TEXT_MODEL,'digest':match.get('digest')},indent=2)+'\n',encoding='utf-8')

def check_ready(root):
    python=root/'work/asr-venv/Scripts/python.exe'
    cli=root/'work/asr-venv/Scripts/savedex-extractor.exe'
    if not python.is_file() or not cli.is_file():raise RuntimeError('The CLI environment is missing; run install.cmd.')
    completed=run_checked([str(python),'-m','savedex_extractor','doctor','--json','--model-dir',str(root/'work/models/faster-whisper-medium'),'--work-dir',str(root/'work/cli-jobs')],cwd=root,capture_output=True,text=True,encoding='utf-8')
    result=json.loads(completed.stdout)
    if result.get('status')!='ready' or not result.get('checks',{}).get('ocr'):raise RuntimeError('The environment is not ready, including OCR; rerun install.cmd.')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result

def main(argv=None):
    parser=argparse.ArgumentParser(description='Prepare or check the local extraction environment.')
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--check',action='store_true')
    modes.add_argument('--dry-run',action='store_true')
    modes.add_argument('--provision',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--ollama')
    args=parser.parse_args(argv)
    try:
        if args.dry_run:print(json.dumps(make_plan(ROOT),indent=2));return 0
        if args.check:check_ready(ROOT);return 0
        if not args.ollama:raise RuntimeError('Use install.cmd so Python and Ollama prerequisites are checked first.')
        if not args.provision:
            install_environment(ROOT,sys.executable,args.ollama)
            return 0
        if medium_ready(ROOT):print('[3/4] Reusing the pinned local Whisper medium weights.',flush=True)
        else:
            print('[3/4] Downloading pinned Whisper medium weights.',flush=True)
            run_checked([sys.executable,str(ROOT/'scripts/download_asr_model.py')],cwd=ROOT)
        provision_qwen(ROOT,args.ollama)
        check_ready(ROOT)
        print('Ready. Run: .\\savedex-extractor summary "REEL_URL"',flush=True)
        return 0
    except KeyboardInterrupt:
        print('Setup interrupted; rerun install.cmd to resume.',file=sys.stderr)
        return 130
    except Exception as error:
        print('Setup failed: '+str(error),file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())
