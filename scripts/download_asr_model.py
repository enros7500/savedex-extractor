"""Provision pinned Whisper weights explicitly; extraction never downloads them."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
MEDIUM_REVISION = '08e178d48790749d25932bbc082711ddcfdfbc4f'
REQUIRED = ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt')

def main(argv=None):
    parser = argparse.ArgumentParser(description='Download the pinned Whisper medium model from Hugging Face.')
    parser.add_argument('--dry-run', action='store_true', help='Print the plan without network access or filesystem changes')
    args = parser.parse_args(argv)
    target = ROOT/'work/models/faster-whisper-medium'
    plan = {'model': 'medium', 'repo': 'Systran/faster-whisper-medium', 'revision': MEDIUM_REVISION, 'destination': str(target)}
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['HF_HUB_DISABLE_XET'] = '1'
    os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
    os.environ['HF_HOME'] = str(ROOT/'work/hf-cache')
    started = time.perf_counter()
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=plan['repo'], revision=plan['revision'], local_dir=str(target), token=False, allow_patterns=list(REQUIRED))
        missing = [name for name in REQUIRED if not (target/name).is_file() or not (target/name).stat().st_size]
        if missing:
            print('Download incomplete; missing or empty required files: '+', '.join(missing), file=sys.stderr)
            return 1
        files = [{'name': name, 'bytes': (target/name).stat().st_size} for name in REQUIRED]
        record = {**plan, 'download_seconds': time.perf_counter()-started, 'files': files, 'bytes': sum(f['bytes'] for f in files)}
        record_path = ROOT/'work/asr-model-download-medium.json'
        record_path.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(record, indent=2))
        return 0
    except ImportError:
        print('Install the CLI dependencies first: python -m pip install .', file=sys.stderr)
        return 69
    except Exception as error:
        print('Model download failed: '+str(error), file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
