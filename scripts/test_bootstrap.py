import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('powershell.exe'),'Windows PowerShell is required')
class BootstrapTests(unittest.TestCase):
    def test_powershell_bootstrap_parses_without_errors(self):
        command="$errors=$null; [System.Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$null,[ref]$errors) | Out-Null; if($errors){$errors | Out-String | Write-Error; exit 1}"
        # Pass the path as an argument to a script block rather than interpolate it.
        with tempfile.TemporaryDirectory() as d:
            probe=Path(d)/'parse.ps1';probe.write_text(command,encoding='utf-8')
            r=subprocess.run(['powershell.exe','-NoProfile','-File',str(probe),str(ROOT/'scripts/install.ps1')],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_public_entry_point_dry_run_works_from_another_directory(self):
        with tempfile.TemporaryDirectory(prefix='setup cwd with spaces ') as d:
            r=subprocess.run([str(ROOT/'install.cmd'),'-DryRun'],cwd=d,capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(r.returncode,0,r.stderr)
        plan=json.loads(r.stdout)
        self.assertEqual(Path(plan['project']),ROOT)
        self.assertFalse(plan['networkUsed'])
        self.assertEqual(plan['models'],['medium','qwen2.5:3b'])

if __name__=='__main__':unittest.main()
