import os,time,subprocess,signal,ctypes,shutil,json,threading
from pathlib import Path
import psutil

class Busy(RuntimeError):pass
class ModelLock:
    def __init__(self,root):self.path=Path(root).resolve()/'.savedex-extractor.lock';self.handle=None
    def __enter__(self):
        self.handle=self.path.open('a+b')
        if os.fstat(self.handle.fileno()).st_size==0:self.handle.write(b'0');self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:self.handle.close();self.handle=None;raise Busy('Another extraction is using this model environment')
        return self
    def __exit__(self,*args):
        if self.handle:
            self.handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(),fcntl.LOCK_UN)
            self.handle.close()

class WindowsJob:
    def __init__(self):
        self.handle=None
        if os.name!='nt':return
        from ctypes import wintypes as W
        class Basic(ctypes.Structure):_fields_=[('per_process',ctypes.c_longlong),('per_job',ctypes.c_longlong),('flags',W.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active',W.DWORD),('affinity',ctypes.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]
        class IO(ctypes.Structure):_fields_=[(k,ctypes.c_ulonglong) for k in ['read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes']]
        class Extended(ctypes.Structure):_fields_=[('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        self.dll=ctypes.WinDLL('kernel32',use_last_error=True)
        self.dll.CreateJobObjectW.argtypes=[ctypes.c_void_p,W.LPCWSTR];self.dll.CreateJobObjectW.restype=W.HANDLE
        self.dll.SetInformationJobObject.argtypes=[W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD]
        self.dll.AssignProcessToJobObject.argtypes=[W.HANDLE,W.HANDLE]
        self.dll.CloseHandle.argtypes=[W.HANDLE]
        self.handle=self.dll.CreateJobObjectW(None,None)
        info=Extended();info.basic.flags=0x2000
        if not self.handle or not self.dll.SetInformationJobObject(self.handle,9,ctypes.byref(info),ctypes.sizeof(info)):raise OSError('Cannot create owned process job')
    def assign(self,proc):
        if self.handle and not self.dll.AssignProcessToJobObject(self.handle,int(proc._handle)):raise OSError('Cannot contain worker processes')
    def close(self):
        if self.handle:self.dll.CloseHandle(self.handle);self.handle=None
def terminate_tree(proc):
    try:
        root=psutil.Process(proc.pid);children=root.children(recursive=True)
        for p in [root,*reversed(children)]:
            try:p.terminate()
            except psutil.Error:pass
        _,alive=psutil.wait_procs([root,*children],timeout=2)
        for p in alive:
            try:p.kill()
            except psutil.Error:pass
    except psutil.Error:pass
def run_supervised(command,job_dir,timeout,log_format='text'):
    owned=WindowsJob();flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    proc=None;reader=None
    try:
        proc=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=flags,start_new_session=os.name!='nt')
        owned.assign(proc)
        (Path(job_dir)/'ready').touch()
        def drain():
            import sys
            total=0
            while chunk:=proc.stderr.readline(16384):
                if total<65536:sys.stderr.write(chunk.decode('utf-8','replace'));sys.stderr.flush()
                total+=len(chunk)
        reader=threading.Thread(target=drain,daemon=True);reader.start()
        try:
            proc.wait(timeout=timeout)
            return proc.returncode
        except subprocess.TimeoutExpired:raise TimeoutError('Invocation deadline exceeded')
    finally:
        if proc and proc.poll() is None:terminate_tree(proc)
        owned.close()
        if os.name!='nt' and proc:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        if proc:
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:terminate_tree(proc)
        if reader:reader.join(3)
        if proc and proc.stderr:proc.stderr.close()
def clean_job(path,root):
    path=Path(path).resolve();root=Path(root).resolve()
    if not path.is_relative_to(root) or not path.name.startswith('savedex-extractor-'):raise ValueError('Refusing cleanup outside owned job')
    for attempt in range(20):
        try:shutil.rmtree(path);return
        except FileNotFoundError:return
        except OSError:
            if attempt==19:raise
            time.sleep(.15)
def reap_abandoned_jobs(root):
    root=Path(root).resolve()
    for path in root.glob('savedex-extractor-*'):
        if not path.is_dir() or not path.resolve().is_relative_to(root):continue
        try:
            owner=json.loads((path/'owner.json').read_text(encoding='utf-8'))
            try:active=abs(psutil.Process(owner['pid']).create_time()-owner['created_time'])<.01
            except psutil.NoSuchProcess:active=False
            if not active:clean_job(path,root)
        except (OSError,ValueError,KeyError,psutil.AccessDenied):continue
