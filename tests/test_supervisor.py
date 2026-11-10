import unittest,tempfile,sys,time,json,subprocess,os
from pathlib import Path
from content_extractor.supervisor import ModelLock,Busy,run_supervised

class SupervisorTests(unittest.TestCase):
    def test_same_model_is_exclusive_even_with_different_jobs(self):
        with tempfile.TemporaryDirectory() as d:
            with ModelLock(Path(d)):
                with self.assertRaises(Busy):
                    with ModelLock(Path(d)):pass
            with ModelLock(Path(d)):pass
    def test_deadline_stops_worker(self):
        with tempfile.TemporaryDirectory() as d:
            start=time.monotonic()
            with self.assertRaises(TimeoutError):run_supervised([sys.executable,'-c','import time; time.sleep(60)'],Path(d),.3)
            self.assertLess(time.monotonic()-start,8)
    def test_normal_worker_exit_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:self.assertEqual(run_supervised([sys.executable,'-c','pass'],Path(d),10),0)
    def test_only_abandoned_owned_jobs_are_reaped(self):
        from content_extractor.supervisor import reap_abandoned_jobs
        import psutil
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);stale=root/'content-extractor-stale';active=root/'content-extractor-active';foreign=root/'unrelated'
            for p in [stale,active,foreign]:p.mkdir()
            (stale/'owner.json').write_text(json.dumps({'pid':2147483647,'created_time':0}))
            (active/'owner.json').write_text(json.dumps({'pid':os.getpid(),'created_time':psutil.Process().create_time()}))
            reap_abandoned_jobs(root)
            self.assertFalse(stale.exists());self.assertTrue(active.exists());self.assertTrue(foreign.exists())
    def test_deadline_kills_descendants_and_stderr_cannot_block(self):
        import psutil,io
        from contextlib import redirect_stderr
        with tempfile.TemporaryDirectory() as d:
            marker=Path(d)/'child.txt'
            script='import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(60)'
            with self.assertRaises(TimeoutError):run_supervised([sys.executable,'-c',script,str(marker)],Path(d),1)
            self.assertTrue(marker.exists())
            pid=int(marker.read_text())
            for _ in range(30):
                if not psutil.pid_exists(pid):break
                time.sleep(.1)
            self.assertFalse(psutil.pid_exists(pid))
            capture=io.StringIO()
            with redirect_stderr(capture):self.assertEqual(run_supervised([sys.executable,'-c','import sys; sys.stderr.write("x"*1000000)'],Path(d),10),0)
            self.assertLess(len(capture.getvalue()),90000)

if __name__=='__main__':unittest.main()
