"""
ime_indicator.pyw  (v4)
-----------------------
Windows IME 상태 표시 오버레이 유틸리티

IME 상태 감지 순서:
  1. ImmGetDefaultIMEWnd → SendMessage(WM_IME_CONTROL, IMC_GETCONVERSIONMODE)
     IME 창에 직접 메시지를 보내 변환 모드를 쿼리.
     어떤 키/수단으로 전환했든 IME 내부 상태를 읽음 (키 매핑 무관).
  2. ImmGetContext → ImmGetConversionStatus (IMM 기반 앱 보조)
  3. GetKeyState(VK_HANGUL) 토글 (최후 폴백)
"""

import tkinter as tk
import ctypes
import ctypes.wintypes

# ── Win32 상수 ──────────────────────────────────────────────────────────────
IME_CMODE_NATIVE    = 0x0001
WM_IME_CONTROL      = 0x0283
IMC_GETCONVERSIONMODE = 0x0001
VK_HANGUL           = 0x15
GWL_EXSTYLE         = -20
WS_EX_LAYERED       = 0x00080000
WS_EX_TRANSPARENT   = 0x00000020
WS_EX_NOACTIVATE    = 0x08000000
WS_EX_TOOLWINDOW    = 0x00000080
LWA_ALPHA           = 0x00000002

# ── 구조체 ──────────────────────────────────────────────────────────────────
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

# ── Win32 함수 바인딩 ────────────────────────────────────────────────────────
user32   = ctypes.windll.user32
imm32    = ctypes.windll.imm32
kernel32 = ctypes.windll.kernel32

_GetForegroundWindow = user32.GetForegroundWindow
_GetForegroundWindow.restype = ctypes.wintypes.HWND

_GetWindowThreadProcessId = user32.GetWindowThreadProcessId
_GetWindowThreadProcessId.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)]
_GetWindowThreadProcessId.restype  = ctypes.wintypes.DWORD

_GetCurrentThreadId = kernel32.GetCurrentThreadId
_GetCurrentThreadId.restype = ctypes.wintypes.DWORD

_AttachThreadInput = user32.AttachThreadInput
_AttachThreadInput.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.BOOL]
_AttachThreadInput.restype  = ctypes.wintypes.BOOL

_GetFocus = user32.GetFocus
_GetFocus.restype = ctypes.wintypes.HWND

# ── IME 창 직접 쿼리 (핵심) ──────────────────────────────────────────────────
_ImmGetDefaultIMEWnd = imm32.ImmGetDefaultIMEWnd
_ImmGetDefaultIMEWnd.argtypes = [ctypes.wintypes.HWND]
_ImmGetDefaultIMEWnd.restype  = ctypes.wintypes.HWND

_SendMessage = user32.SendMessageW
_SendMessage.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
]
_SendMessage.restype = ctypes.wintypes.LPARAM

# ── ImmGetContext 계열 (보조) ─────────────────────────────────────────────────
_ImmGetContext = imm32.ImmGetContext
_ImmGetContext.argtypes = [ctypes.wintypes.HWND]
_ImmGetContext.restype  = ctypes.wintypes.HANDLE

_ImmGetConversionStatus = imm32.ImmGetConversionStatus
_ImmGetConversionStatus.argtypes = [
    ctypes.wintypes.HANDLE,
    ctypes.POINTER(ctypes.wintypes.DWORD),
    ctypes.POINTER(ctypes.wintypes.DWORD),
]
_ImmGetConversionStatus.restype = ctypes.wintypes.BOOL

_ImmReleaseContext = imm32.ImmReleaseContext
_ImmReleaseContext.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HANDLE]
_ImmReleaseContext.restype  = ctypes.wintypes.BOOL

# ── 마우스·키 ────────────────────────────────────────────────────────────────
_GetCursorPos = user32.GetCursorPos
_GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
_GetCursorPos.restype  = ctypes.wintypes.BOOL

_GetKeyState = user32.GetKeyState
_GetKeyState.argtypes = [ctypes.c_int]
_GetKeyState.restype  = ctypes.c_short

# ── Win32 스타일 ─────────────────────────────────────────────────────────────
_GetWindowLongW = user32.GetWindowLongW
_GetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
_GetWindowLongW.restype  = ctypes.c_long

_SetWindowLongW = user32.SetWindowLongW
_SetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_long]
_SetWindowLongW.restype  = ctypes.c_long

_SetLayeredWindowAttributes = user32.SetLayeredWindowAttributes
_SetLayeredWindowAttributes.argtypes = [
    ctypes.wintypes.HWND, ctypes.wintypes.COLORREF,
    ctypes.c_byte, ctypes.wintypes.DWORD,
]
_SetLayeredWindowAttributes.restype = ctypes.wintypes.BOOL

# ── 설정 ────────────────────────────────────────────────────────────────────
POLL_MS     = 10
OFFSET_X    = 16
OFFSET_Y    = 20
ALPHA       = 215
FONT_FAMILY = "맑은 고딕"
FONT_SIZE   = 11

COLOR_KO_BG = "#1a6fe8"
COLOR_KO_FG = "#ffffff"
COLOR_EN_BG = "#606060"
COLOR_EN_FG = "#ffffff"

# ── IME 상태 감지 ────────────────────────────────────────────────────────────

def _get_focused_hwnd() -> int:
    """AttachThreadInput → GetFocus() 로 실제 포커스 컨트롤 HWND 반환."""
    hwnd_fg = _GetForegroundWindow()
    our_tid = _GetCurrentThreadId()
    fg_tid  = _GetWindowThreadProcessId(hwnd_fg, None)

    if fg_tid == 0 or fg_tid == our_tid:
        return hwnd_fg

    attached = _AttachThreadInput(our_tid, fg_tid, True)
    try:
        hwnd_focus = _GetFocus()
    finally:
        if attached:
            _AttachThreadInput(our_tid, fg_tid, False)

    return hwnd_focus if hwnd_focus else hwnd_fg


def is_korean_mode() -> bool:
    hwnd = _get_focused_hwnd()

    # ── 방법 1: IME 창에 직접 WM_IME_CONTROL 메시지로 변환 모드 쿼리 ──────────
    # ImmGetDefaultIMEWnd: 해당 창의 스레드에 연결된 IME 창 핸들 반환
    # SendMessage(WM_IME_CONTROL, IMC_GETCONVERSIONMODE): 변환 모드 정수 반환
    # → 키 매핑/물리 키와 무관하게 IME 내부 상태 직접 조회
    ime_wnd = _ImmGetDefaultIMEWnd(hwnd)
    if ime_wnd:
        result = _SendMessage(ime_wnd, WM_IME_CONTROL, IMC_GETCONVERSIONMODE, 0)
        # result == -1 이면 실패 (일부 앱), 아니면 변환 플래그
        if result != -1:
            return bool(result & IME_CMODE_NATIVE)

    # ── 방법 2: ImmGetContext → ImmGetConversionStatus (IMM 계열 앱 보조) ──────
    himc = _ImmGetContext(hwnd)
    if himc:
        conv = ctypes.wintypes.DWORD(0)
        sent = ctypes.wintypes.DWORD(0)
        ok   = _ImmGetConversionStatus(himc, ctypes.byref(conv), ctypes.byref(sent))
        _ImmReleaseContext(hwnd, himc)
        if ok:
            return bool(conv.value & IME_CMODE_NATIVE)

    # ── 방법 3: VK_HANGUL 토글 (최후 폴백) ───────────────────────────────────
    return bool(_GetKeyState(VK_HANGUL) & 0x0001)


def get_mouse_pos():
    pt = POINT(0, 0)
    _GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

# ── 메인 오버레이 클래스 ──────────────────────────────────────────────────────

class ImeIndicator:
    def __init__(self):
        self.root = tk.Tk()
        self._setup_window()
        self._setup_label()
        self._apply_win32_style()
        self._last_korean = None
        self._update()

    def _setup_window(self):
        r = self.root
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.attributes("-alpha", ALPHA / 255)
        r.configure(bg=COLOR_EN_BG)
        r.geometry("30x22+0+0")
        r.resizable(False, False)

    def _apply_win32_style(self):
        self.root.update_idletasks()
        hwnd = self.root.winfo_id()
        ex = _GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        _SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
        _SetLayeredWindowAttributes(hwnd, 0, ALPHA, LWA_ALPHA)

    def _setup_label(self):
        self.lbl = tk.Label(
            self.root,
            text="e",
            font=(FONT_FAMILY, FONT_SIZE, "bold"),
            fg=COLOR_EN_FG,
            bg=COLOR_EN_BG,
            padx=4,
            pady=1,
        )
        self.lbl.pack(fill="both", expand=True)

    def _refresh_style(self, korean: bool):
        if korean:
            bg, fg, text = COLOR_KO_BG, COLOR_KO_FG, "한"
        else:
            bg, fg, text = COLOR_EN_BG, COLOR_EN_FG, "e"
        self.lbl.config(text=text, bg=bg, fg=fg)
        self.root.configure(bg=bg)

    def _update(self):
        try:
            korean = is_korean_mode()
            x, y   = get_mouse_pos()

            if korean != self._last_korean:
                self._refresh_style(korean)
                self._last_korean = korean

            self.root.geometry(f"+{x + OFFSET_X}+{y + OFFSET_Y}")
        except Exception:
            pass

        self.root.after(POLL_MS, self._update)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ImeIndicator().run()
