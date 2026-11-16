"""Create local secret files with private permissions before writing any secret bytes."""
import csv
import os
import subprocess
from pathlib import Path


def _windows():
    return os.name == 'nt'


def _create_windows_file(path, sid):
    """Attach the protected DACL atomically with CREATE_NEW; never inherit broad grants."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class SecurityAttributes(ctypes.Structure):
        _fields_ = [('length', wintypes.DWORD), ('descriptor', wintypes.LPVOID), ('inherit', wintypes.BOOL)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    security = ctypes.WinDLL('advapi32', use_last_error=True)
    convert = security.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.DWORD)]
    convert.restype = wintypes.BOOL
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(SecurityAttributes),
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    kernel.LocalFree.argtypes = [wintypes.LPVOID]
    kernel.LocalFree.restype = wintypes.LPVOID
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    descriptor = wintypes.LPVOID()
    # Only the creating user and SYSTEM; P prevents inherited ACEs from being merged.
    if not convert(f'D:P(A;;FA;;;{sid})(A;;FA;;;SY)', 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        attributes = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
        handle = create(str(path.resolve()), 0x40000000, 0, ctypes.byref(attributes), 1, 0x80, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(handle)
            path.unlink(missing_ok=True)
            raise
    finally:
        kernel.LocalFree(descriptor)


def create_private_file(path):
    """Return an exclusive writable descriptor; fail closed if Windows ACL setup fails.

    Windows creation supplies the protected DACL in the creation call itself,
    so there is no inherited-permission window before a later chmod/icacls call.
    Existing files are never replaced or modified by this function.
    """
    path = Path(path)
    if _windows():
        identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'],
                                  capture_output=True, text=True, check=True)
        sid = next(csv.reader(identity.stdout.strip().splitlines()))[1]
        if not sid.startswith('S-1-') or not all(part.isdecimal() for part in sid[2:].split('-')):
            raise RuntimeError('Cannot determine the local secret owner')
        return _create_windows_file(path, sid)
    return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)


def write_private_file(path, text, *, encoding='utf-8'):
    descriptor = create_private_file(path)
    with os.fdopen(descriptor, 'w', encoding=encoding, newline='\n') as output:
        output.write(text)
