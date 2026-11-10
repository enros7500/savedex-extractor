"""Repository hygiene checks; not a comprehensive secret scanner."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PERSONAL_PATH = re.compile(r'(?i)(?:[a-z]:[\\/]+Users[\\/]+[^\\/\s"<>]+|/(?:Users|home)/[^/\s"<>]+)')
SECRET_PATTERNS = {
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'GitHub token': re.compile(r'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}'),
    'API key': re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}'),
    'AWS access key': re.compile(r'\bAKIA[A-Z0-9]{16}\b'),
}
ACTIVE_DOCS = ('README.md', 'ROADMAP.md', 'CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md', 'docs/README.md', 'docs/CLI.md', 'docs/CI.md', 'examples/README.md')

def check(root=ROOT):
    output = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root)
    files = sorted(set(output.decode('utf-8').split('\0')) - {''})
    errors = []
    for name in files:
        p = root/name
        if not p.is_file():continue
        if name.startswith(('work/', 'outputs/')) or p.suffix.lower() in {'.bin', '.onnx', '.gguf', '.safetensors', '.whl', '.zip', '.bundle'}:
            errors.append(f'{name}: generated runtime/model/distribution file should not be versioned')
        if p.stat().st_size > 2_000_000:errors.append(f'{name}: file exceeds the 2 MB publication budget')
        try:text = p.read_text(encoding='utf-8-sig')
        except UnicodeError:continue
        if PERSONAL_PATH.search(text):errors.append(f'{name}: machine-specific home path')
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):errors.append(f'{name}: possible {label}; inspect before publishing')
    for name in ACTIVE_DOCS:
        p = root/name
        if not p.is_file():
            errors.append(f'{name}: missing active documentation');continue
        text = p.read_text(encoding='utf-8-sig')
        if text.count('```') % 2:errors.append(f'{name}: unclosed code fence')
        for target in re.findall(r'\]\(([^)]+)\)', text):
            if target.startswith(('https://', 'http://', '#', 'mailto:')):continue
            path = target.partition('#')[0]
            if not (p.parent/path).exists():errors.append(f'{name}: broken local link: {target}')
    if not (root/'LICENSE').is_file():errors.append('LICENSE is missing')
    return errors

def main():
    errors = check()
    if errors:
        print('\n'.join(errors), file=sys.stderr);return 1
    print('Repository checks passed: published files, basic secret/path patterns, active documentation links, and license.')
    return 0

if __name__ == '__main__':raise SystemExit(main())
