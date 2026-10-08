# SPDX-License-Identifier: GPL-3.0-or-later
import ctypes
import os
from PyQt5.QtCore import QObject
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

_HOLD = None
_PIPE = "CampusTerminal.window."


def pipe_name():
    return _PIPE + os.environ.get("USERNAME", "current")


def claim_primary():
    """True when this process is the only interface. The handle is kept open."""
    global _HOLD
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetLastError.argtypes = [ctypes.c_uint32]
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    kernel.SetLastError(0)
    handle = kernel.CreateMutexW(None, False, "Local\\CampusTerminal.App")
    error = ctypes.get_last_error()
    if not handle:
        return True
    if error == 183:
        kernel.CloseHandle(handle)
        return False
    _HOLD = handle
    return True


def ping(reveal):
    """Ask the running interface to show itself. Silent autostart sends 0 and stays quiet."""
    sock = QLocalSocket()
    sock.connectToServer(pipe_name())
    if not sock.waitForConnected(600):
        return False
    sock.write(b"1" if reveal else b"0")
    sock.flush()
    sock.waitForBytesWritten(300)
    sock.disconnectFromServer()
    return True


class SingleInstance(QObject):
    def __init__(self, show, parent=None):
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.newConnection.connect(lambda: self._activate(show))
        self.name = pipe_name()

    def acquire(self):
        if self.server.listen(self.name):
            return True
        client = QLocalSocket(self)
        client.connectToServer(self.name)
        if client.waitForConnected(400):
            client.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.name)
        return self.server.listen(self.name)

    def _activate(self, show):
        reveal = False
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            if client.waitForReadyRead(300):
                data = bytes(client.readAll())
            else:
                data = bytes(client.readAll())
            # Only an explicit "1" opens the panel. Empty or "0" is a silent duplicate.
            if b"1" in data:
                reveal = True
            client.disconnectFromServer()
            client.deleteLater()
        if reveal:
            show()
