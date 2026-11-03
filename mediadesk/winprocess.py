"""Windows child processes contained in a kill-on-close Job Object."""
import ctypes as C
from ctypes import wintypes as W
import subprocess
import time

kernel=C.WinDLL('kernel32',use_last_error=True)
nt=C.WinDLL('ntdll')

def api(dll,name,result,args):
    fn=getattr(dll,name);fn.restype=result;fn.argtypes=args;return fn

close=api(kernel,'CloseHandle',W.BOOL,[W.HANDLE])
create_job=api(kernel,'CreateJobObjectW',W.HANDLE,[C.c_void_p,W.LPCWSTR])
set_job=api(kernel,'SetInformationJobObject',W.BOOL,[W.HANDLE,C.c_int,C.c_void_p,W.DWORD])
query_job=api(kernel,'QueryInformationJobObject',W.BOOL,[W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.c_void_p])
assign=api(kernel,'AssignProcessToJobObject',W.BOOL,[W.HANDLE,W.HANDLE])
terminate=api(kernel,'TerminateJobObject',W.BOOL,[W.HANDLE,W.UINT])
open_process=api(kernel,'OpenProcess',W.HANDLE,[W.DWORD,W.BOOL,W.DWORD])
is_member=api(kernel,'IsProcessInJob',W.BOOL,[W.HANDLE,W.HANDLE,C.POINTER(W.BOOL)])
suspend=api(nt,'NtSuspendProcess',W.LONG,[W.HANDLE])
resume=api(nt,'NtResumeProcess',W.LONG,[W.HANDLE])

class BasicLimits(C.Structure):
    _fields_=[('PerProcessUserTimeLimit',C.c_int64),('PerJobUserTimeLimit',C.c_int64),('LimitFlags',W.DWORD),('MinimumWorkingSetSize',C.c_size_t),('MaximumWorkingSetSize',C.c_size_t),('ActiveProcessLimit',W.DWORD),('Affinity',C.c_size_t),('PriorityClass',W.DWORD),('SchedulingClass',W.DWORD)]

class IO(C.Structure):
    _fields_=[(name,C.c_uint64) for name in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]

class ExtendedLimits(C.Structure):
    _fields_=[('BasicLimitInformation',BasicLimits),('IoInfo',IO),('ProcessMemoryLimit',C.c_size_t),('JobMemoryLimit',C.c_size_t),('PeakProcessMemoryUsed',C.c_size_t),('PeakJobMemoryUsed',C.c_size_t)]

def checked(value):
    if not value:raise C.WinError(C.get_last_error())
    return value

class Process(subprocess.Popen):
    def __init__(self,args,**kwargs):
        kwargs.pop('start_new_session',None)
        self.job=checked(create_job(None,None));self.suspended={}
        try:
            limits=ExtendedLimits();limits.BasicLimitInformation.LimitFlags=0x2000
            checked(set_job(self.job,9,C.byref(limits),C.sizeof(limits)))
            kwargs['creationflags']=kwargs.get('creationflags',0)|subprocess.CREATE_NO_WINDOW|0x4
            super().__init__(args,**kwargs)
            try:
                checked(assign(self.job,int(self._handle)))
                if resume(int(self._handle))<0:raise OSError('无法启动 Windows 下载进程')
            except BaseException:
                self.kill();self.wait(timeout=3)
                raise
        except BaseException:
            close(self.job);self.job=None
            raise

    def pids(self):
        if not self.job:return []
        count=64
        while count<=65536:
            # JOBOBJECT_BASIC_PROCESS_ID_LIST has two DWORDs then ULONG_PTRs.
            buffer=C.create_string_buffer(8+count*C.sizeof(C.c_size_t))
            if query_job(self.job,3,buffer,len(buffer),None):
                size=C.cast(buffer,C.POINTER(W.DWORD))[1]
                return list((C.c_size_t*size).from_buffer(buffer,8))
            error=C.get_last_error()
            if error!=234:raise C.WinError(error)
            count*=2
        raise OSError('Windows 下载进程树过大')

    def pause_tree(self):
        try:
            # Suspend every existing member, then recheck for children born during the snapshot.
            for _ in range(32):
                pending=set(self.pids())-self.suspended.keys()
                if not pending:return
                for pid in pending:
                    handle=open_process(0x0800|0x1000,False,pid)
                    if not handle:
                        if pid not in self.pids():continue
                        raise C.WinError(C.get_last_error())
                    member=W.BOOL()
                    if not is_member(handle,self.job,C.byref(member)) or not member.value:
                        close(handle);continue
                    if suspend(handle)<0:
                        close(handle)
                        if pid not in self.pids():continue
                        raise OSError('无法暂停 Windows 下载进程')
                    self.suspended[pid]=handle
            raise OSError('Windows 下载进程树持续变化，暂停未完成')
        except BaseException:
            self.resume_tree();raise

    def resume_tree(self):
        failed=False
        for pid,handle in list(self.suspended.items()):
            if resume(handle)<0 and pid in self.pids():failed=True;continue
            close(handle);del self.suspended[pid]
        if failed:raise OSError('无法恢复 Windows 下载进程')

    def terminate_tree(self):
        if self.job:checked(terminate(self.job,1))

    def finish_tree(self):
        self.terminate_tree()
        code=self.wait(timeout=3)
        end=time.monotonic()+3
        while self.pids():
            if time.monotonic()>=end:raise OSError('Windows 下载子进程尚未退出')
            time.sleep(.02)
        for handle in self.suspended.values():close(handle)
        self.suspended.clear()
        if self.job:close(self.job);self.job=None
        return code
