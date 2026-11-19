"""Windows suspend and resume notifications for the Qt application."""

from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

WM_POWERBROADCAST = 0x0218
PBT_APMRESUMEAUTOMATIC = 0x0012


class WindowsWakeFilter(QAbstractNativeEventFilter):
    def __init__(self, on_resume):
        super().__init__()
        self.on_resume = on_resume

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_POWERBROADCAST and msg.wParam == PBT_APMRESUMEAUTOMATIC:
                self.on_resume()
        return False, 0
