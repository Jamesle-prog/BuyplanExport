"""Screenshot helper - captures PO Extractor Chrome window using PrintWindow API."""
import ctypes
import ctypes.wintypes as W
from PIL import Image
import sys, os

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

def find_window(partial_title):
    found = []
    def enum_cb(hwnd, lp):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if partial_title in buf.value:
                found.append((hwnd, buf.value))
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, W.LPARAM, W.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return found

def capture_window(hwnd, out_path):
    rect = W.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top

    hdc = user32.GetDC(hwnd)
    mhdc = gdi32.CreateCompatibleDC(hdc)
    hbmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mhdc, hbmp)

    PW_RENDERFULLCONTENT = 0x00000002
    user32.PrintWindow(hwnd, mhdc, PW_RENDERFULLCONTENT)

    import struct
    bmi = ctypes.create_string_buffer(40)
    bmi[:40] = struct.pack('IiiHHIIiiII', 40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    data = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mhdc, hbmp, 0, h, data, bmi, 0)

    img = Image.frombytes('RGBA', (w, h), bytes(data), 'raw', 'BGRA').convert('RGB')
    img.save(out_path, 'JPEG', quality=92)

    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(mhdc)
    user32.ReleaseDC(hwnd, hdc)
    return w, h

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'screenshot.jpg'
    windows = find_window('PO Extractor')
    if not windows:
        print('ERROR: PO Extractor window not found')
        sys.exit(1)
    hwnd, title = windows[0]
    w, h = capture_window(hwnd, out)
    print(f'Saved {w}x{h} -> {out}')
