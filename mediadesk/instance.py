"""Keep an exclusive application lock alive until its file descriptor closes."""
import os


def acquire(path):
    fd=os.open(path,os.O_CREAT|os.O_RDWR,0o600)
    try:
        if os.name=='nt':
            import msvcrt
            if os.fstat(fd).st_size==0:os.write(fd,b'\0')
            os.lseek(fd,0,os.SEEK_SET)
            try:msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
            except OSError as exc:raise BlockingIOError('MediaDesk 已在运行') from exc
        else:
            import fcntl
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd);raise
