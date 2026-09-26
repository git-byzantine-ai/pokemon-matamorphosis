"""Windows process ownership and per-data-directory locking."""
import ctypes
from ctypes import wintypes as w
import msvcrt


class DataLock:
    def __init__(self,path):
        self.file=open(path,'a+b')
        try:
            self.file.seek(0,2)
            if not self.file.tell():self.file.write(b'0');self.file.flush()
            self.file.seek(0)
            msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            self.file.close();raise RuntimeError('Another Metamorphosis launcher is already using this data folder.')

    def close(self):
        self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1);self.file.close()


class Basic(ctypes.Structure):
    _fields_=[('ProcessTime',ctypes.c_int64),('JobTime',ctypes.c_int64),('Flags',w.DWORD),
              ('MinWorking',ctypes.c_size_t),('MaxWorking',ctypes.c_size_t),('ActiveLimit',w.DWORD),
              ('Affinity',ctypes.c_size_t),('Priority',w.DWORD),('Scheduling',w.DWORD)]


class IO(ctypes.Structure):
    _fields_=[(n,ctypes.c_uint64) for n in ('ReadOps','WriteOps','OtherOps','ReadBytes','WriteBytes','OtherBytes')]


class Extended(ctypes.Structure):
    _fields_=[('Basic',Basic),('IO',IO),('ProcessMem',ctypes.c_size_t),('JobMem',ctypes.c_size_t),
              ('PeakProcess',ctypes.c_size_t),('PeakJob',ctypes.c_size_t)]


class ChildJob:
    """Closing the launcher cleans up its companion and any GPU subprocess."""
    def __init__(self,process):
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateJobObjectW.restype=w.HANDLE
        self.kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR]
        self.kernel.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
        self.kernel.CloseHandle.argtypes=[w.HANDLE]
        self.handle=self.kernel.CreateJobObjectW(None,None)
        info=Extended();info.Basic.Flags=0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.kernel.SetInformationJobObject(self.handle,9,ctypes.byref(info),ctypes.sizeof(info)) or not self.kernel.AssignProcessToJobObject(self.handle,w.HANDLE(int(process._handle))):
            self.close();process.terminate();process.wait();raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None
