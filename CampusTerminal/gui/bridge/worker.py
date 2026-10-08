# SPDX-License-Identifier: GPL-3.0-or-later
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot


class _Worker(QObject):
    completed = pyqtSignal(str, object)

    def __init__(self, backend):
        super().__init__()
        self.backend = backend

    @pyqtSlot(str, object)
    def execute(self, method, args):
        try:
            result = getattr(self.backend, method)(*args)
        except Exception:
            result = {"ok": False, "error": "BackendRequestFailed"}
        self.completed.emit(method, result)


class BackendWorker(QObject):
    request = pyqtSignal(str, object)
    completed = pyqtSignal(str, object)

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.busy = False
        self.thread = QThread(self)
        self.worker = _Worker(backend)
        self.worker.moveToThread(self.thread)
        self.thread.finished.connect(self.worker.deleteLater)
        self.request.connect(self.worker.execute)
        self.worker.completed.connect(self._done)
        self.thread.start()

    def submit(self, method, *args):
        if self.busy:
            return False
        self.busy = True
        self.request.emit(method, args)
        return True

    def _done(self, method, result):
        self.busy = False
        self.completed.emit(method, result)

    def close(self):
        self.thread.quit()
        if not self.thread.wait(8000):
            self.thread.terminate()
            self.thread.wait(2000)
