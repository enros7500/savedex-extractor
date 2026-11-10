"""Project-relative launcher for the installed CLI."""
from pathlib import Path
import subprocess
import sys

def main():
    root=Path(__file__).resolve().parent.parent
    args=sys.argv[1:]
    command='extract'
    if args and args[0]=='summary':
        command=args.pop(0)
    if not args:
        print('Usage: reel URL | reel summary URL | reel summary --result FILE',file=sys.stderr)
        return 64
    if args[0] not in ['--result','--help','-h']:
        args=['--url',args[0],*args[1:]]
    cli=root/'work/asr-venv/Scripts/content-extractor.exe'
    try:
        return subprocess.call([str(cli),command,'--model-dir',str(root/'work/models/faster-whisper-medium'),'--work-dir',str(root/'work/cli-jobs'),*args])
    except FileNotFoundError:
        print('The local CLI is not installed at the configured location.',file=sys.stderr)
        return 69
    except KeyboardInterrupt:
        return 130

if __name__=='__main__':raise SystemExit(main())
