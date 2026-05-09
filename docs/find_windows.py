# Enumerate all visible top-level windows and their sizes
import ctypes, ctypes.wintypes as W, sys

user32 = ctypes.windll.user32

def enum_all():
    results = []
    def cb(hwnd, lp):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 10:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                rect = W.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                if w > 500 and h > 400:  # Only large windows
                    try:
                        results.append((hwnd, w, h, buf.value[:80]))
                    except Exception:
                        pass
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, W.LPARAM, W.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return results

for hwnd, w, h, title in sorted(enum_all(), key=lambda x: -x[1]*x[2]):
    print(f"HWND={hwnd:10d}  {w:4d}x{h:4d}  {title}")
