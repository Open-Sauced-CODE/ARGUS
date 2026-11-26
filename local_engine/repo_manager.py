"""Local Git repository shallow-clone helper, safe AWS CLI profile reader, and Windows native file/folder pickers."""

from __future__ import annotations

import configparser
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from local_engine.paths import get_data_dir

_SCP_GIT_RE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:[A-Za-z0-9._/-]+(?:\.git)?$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,128}$")
_UNSAFE_URL_CHARS = re.compile(r'[\s\x00-\x1f;&|`$<>()"\']')
_DIALOG_LOCK = threading.Lock()


def _win_no_window_kwargs() -> Dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}


def validate_git_url(repo_url: str) -> str:
    """Validate an HTTPS / SSH / git@ / file:// repository URL safely (rejecting flag injection)."""
    raw = (repo_url or "").strip()
    if not raw:
        raise ValueError("Repository URL is required.")
    if raw.startswith("-") or _UNSAFE_URL_CHARS.search(raw):
        raise ValueError("Invalid repository URL: contains disallowed whitespace or characters.")

    if _SCP_GIT_RE.fullmatch(raw):
        return raw

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme == "file":
        if not parsed.path:
            raise ValueError("Invalid file:// git URL.")
        return raw
    if scheme in ("https", "ssh"):
        segments = [seg for seg in parsed.path.split("/") if seg]
        if not parsed.netloc or not segments:
            raise ValueError(f"Incomplete git repository URL: {raw}")
        if (parsed.hostname or "").lower() in ("github.com", "gitlab.com", "bitbucket.org") and len(segments) < 2:
            raise ValueError(f"Incomplete git repository URL (expected owner/repo): {raw}")
        return raw
    if scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"):
        return raw

    raise ValueError(
        "Unsupported git URL scheme. Use https://github.com/org/repo.git, ssh://, git@github.com:org/repo.git, or file://."
    )


def _find_git_binary() -> Optional[str]:
    git_bin = shutil.which("git")
    if git_bin:
        return git_bin
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "cmd" / "git.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Git" / "cmd" / "git.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "cmd" / "git.exe",
        ]
        for c in candidates:
            if c.exists() and c.is_file():
                return str(c)
    return None


def _normalize_github_browser_url(
    clean_url: str,
    branch: Optional[str],
    subpath: Optional[str],
) -> tuple[str, Optional[str], Optional[str]]:
    """Support pasting GitHub browser URLs like https://github.com/org/repo/tree/main/infra."""
    parsed = urlparse(clean_url)
    if (parsed.scheme or "").lower() == "https" and (parsed.hostname or "").lower() == "github.com":
        segs = [s for s in parsed.path.split("/") if s]
        if len(segs) >= 4 and segs[2] == "tree":
            owner, repo = segs[0], segs[1]
            url_branch = segs[3]
            url_sub = "/".join(segs[4:]) if len(segs) > 4 else None
            base_repo = f"https://github.com/{owner}/{repo}.git"
            return base_repo, (branch or url_branch), (subpath or url_sub)
    return clean_url, branch, subpath


def clone_terraform_repo(
    repo_url: str,
    *,
    branch: Optional[str] = None,
    subpath: Optional[str] = None,
    dest_root: Optional[Path] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Shallow-clone a git repository locally on-device and verify Terraform files exist."""
    clean_url = validate_git_url(repo_url)
    clean_url, branch, subpath = _normalize_github_browser_url(clean_url, branch, subpath)

    clean_branch: Optional[str] = None
    if branch and branch.strip():
        b = branch.strip()
        if b.startswith("-") or ".." in b or not _BRANCH_RE.fullmatch(b):
            raise ValueError(f"Invalid git branch name: {branch!r}")
        clean_branch = b

    git_bin = _find_git_binary()
    if not git_bin:
        raise RuntimeError("Git executable not found on PATH. Install Git for Windows to clone repositories.")

    repos_root = Path(dest_root) if dest_root else (get_data_dir() / "repos")
    repos_root.mkdir(parents=True, exist_ok=True)

    tail = clean_url.rstrip("/").split("/")[-1].split(":")[-1]
    if tail.endswith(".git"):
        tail = tail[:-4]
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", tail).strip("-") or "terraform-repo"
    clone_dir = repos_root / f"{slug}-{int(time.time() * 1000)}"

    cmd = [git_bin, "clone", "--depth", "1"]
    if clean_branch:
        cmd.extend(["--branch", clean_branch])
    cmd.extend(["--", clean_url, str(clone_dir)])

    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"

    proc = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        **_win_no_window_kwargs(),
    )
    if proc.returncode != 0:
        shutil.rmtree(clone_dir, ignore_errors=True)
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"git clone failed: {err or f'exit code {proc.returncode}'}")

    scan_dir = clone_dir.resolve()
    clean_sub = (subpath or "").strip().strip("/\\")
    if clean_sub:
        candidate = (clone_dir / clean_sub).resolve()
        if not candidate.is_relative_to(clone_dir.resolve()):
            shutil.rmtree(clone_dir, ignore_errors=True)
            raise ValueError("Subdirectory must stay inside the cloned repository.")
        if not candidate.exists() or not candidate.is_dir():
            shutil.rmtree(clone_dir, ignore_errors=True)
            raise ValueError(f"Subdirectory not found inside cloned repo: {clean_sub}")
        scan_dir = candidate

    tf_files = [
        p
        for p in scan_dir.rglob("*")
        if p.is_file()
        and (p.suffix == ".tf" or p.name.endswith(".tf.json"))
        and ".terraform" not in p.parts
        and ".git" not in p.parts
    ]
    if not tf_files:
        shutil.rmtree(clone_dir, ignore_errors=True)
        raise ValueError(
            f"No .tf or .tf.json files found in cloned repository{f' ({clean_sub})' if clean_sub else ''}."
        )

    commit_sha = ""
    try:
        rev = subprocess.run(
            [git_bin, "-C", str(clone_dir), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            **_win_no_window_kwargs(),
        )
        if rev.returncode == 0:
            commit_sha = rev.stdout.strip()
    except Exception:
        pass

    return {
        "repo_url": clean_url,
        "branch": clean_branch,
        "subpath": clean_sub,
        "clone_dir": str(clone_dir),
        "scan_dir": str(scan_dir),
        "commit": commit_sha,
        "tf_count": len(tf_files),
    }


def list_aws_cli_profiles(aws_dir: Optional[Path] = None) -> List[str]:
    """Read profile names ONLY from ~/.aws/credentials & ~/.aws/config (never returning secret keys)."""
    base = Path(aws_dir) if aws_dir else (Path.home() / ".aws")
    profiles: set[str] = set()

    creds_path = base / "credentials"
    if creds_path.exists() and creds_path.is_file():
        cp = configparser.RawConfigParser()
        try:
            cp.read(creds_path, encoding="utf-8")
            for sec in cp.sections():
                name = sec.strip()
                if name:
                    profiles.add(name)
        except Exception:
            pass

    cfg_path = base / "config"
    if cfg_path.exists() and cfg_path.is_file():
        cp = configparser.RawConfigParser()
        try:
            cp.read(cfg_path, encoding="utf-8")
            for sec in cp.sections():
                s = sec.strip()
                if s == "default":
                    profiles.add("default")
                elif s.startswith("profile "):
                    name = s[len("profile ") :].strip()
                    if name:
                        profiles.add(name)
        except Exception:
            pass

    return sorted(profiles, key=lambda p: (0 if p == "default" else 1, p.lower()))


def _resolve_initial_dir(mode: str, initial_dir: Optional[str]) -> Optional[str]:
    if initial_dir:
        try:
            p = Path(initial_dir).expanduser()
            if p.is_file():
                p = p.parent
            if p.exists() and p.is_dir():
                return str(p.resolve())
        except OSError:
            pass
    if mode == "gguf":
        for cand in (
            Path(r"D:\ARGUS"),
            Path(r"C:\ARGUS"),
            Path.home() / "Downloads",
            Path.home(),
        ):
            try:
                if cand.exists() and cand.is_dir():
                    if cand.name == "ARGUS" and not any(cand.glob("*.gguf")):
                        continue
                    return str(cand.resolve())
            except OSError:
                continue
    return str(Path.home())


def _pick_win32_native(mode: str, init_dir: Optional[str], timeout: float = 180.0) -> Optional[str]:
    """Open a topmost native Win32 OpenFileNameW / SHBrowseForFolderW dialog in an STA thread."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    comdlg32 = ctypes.windll.comdlg32
    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32

    WS_EX_TOPMOST = 0x00000008
    WS_EX_TOOLWINDOW = 0x00000080
    COINIT_APARTMENTTHREADED = 0x2
    BFFM_INITIALIZED = 1
    BFFM_SETSELECTIONW = 0x0400 + 103
    BIF_RETURNONLYFSDIRS = 0x0001
    BIF_EDITBOX = 0x0010
    BIF_NEWDIALOGSTYLE = 0x0040
    BIF_NONEWFOLDERBUTTON = 0x0200
    HWND_TOPMOST = -1
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_SHOWWINDOW = 0x0040

    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
    ]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]

    BFFCALLBACK = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.UINT, wintypes.LPARAM, wintypes.LPARAM)

    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", ctypes.c_void_p),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", ctypes.c_void_p),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    class BROWSEINFOW(ctypes.Structure):
        _fields_ = [
            ("hwndOwner", wintypes.HWND),
            ("pidlRoot", ctypes.c_void_p),
            ("pszDisplayName", wintypes.LPWSTR),
            ("lpszTitle", wintypes.LPCWSTR),
            ("ulFlags", wintypes.UINT),
            ("lpfn", BFFCALLBACK),
            ("lParam", wintypes.LPARAM),
            ("iImage", ctypes.c_int),
        ]

    comdlg32.GetOpenFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]
    comdlg32.GetOpenFileNameW.restype = wintypes.BOOL
    shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFOW)]
    shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
    shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR]
    shell32.SHGetPathFromIDListW.restype = wintypes.BOOL

    result_box: Dict[str, Optional[str]] = {"path": None}
    owner_box: List[int] = []

    def _run_sta() -> None:
        hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        owner = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW, "STATIC", "ARGUS Picker",
            0, 120, 120, 1, 1, None, None, None, None,
        )
        if owner:
            owner_box.append(owner)
        try:
            if owner:
                user32.SetForegroundWindow(owner)
            if mode == "gguf":
                flt_buf = ctypes.create_unicode_buffer(
                    "GGUF Model (*.gguf)\0*.gguf\0All Files (*.*)\0*.*\0\0"
                )
                buf = ctypes.create_unicode_buffer(4096)
                ofn = OPENFILENAMEW()
                ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
                ofn.hwndOwner = owner
                ofn.lpstrFilter = ctypes.cast(flt_buf, wintypes.LPCWSTR)
                ofn.nFilterIndex = 1
                ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
                ofn.nMaxFile = len(buf)
                ofn.lpstrInitialDir = init_dir
                ofn.lpstrTitle = "Select ARGUS-M1 Quantized GGUF Model"
                # EXPLORER | FILEMUSTEXIST | PATHMUSTEXIST | NOCHANGEDIR
                ofn.Flags = 0x00080000 | 0x00001000 | 0x00000800 | 0x00000008
                if comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
                    val = buf.value.strip()
                    result_box["path"] = val or None
            else:
                init_buf = ctypes.create_unicode_buffer(init_dir) if init_dir else None
                init_ptr = ctypes.cast(init_buf, ctypes.c_void_p).value if init_buf is not None else 0

                def _browse_cb(hwnd: Any, msg: int, _lp: Any, _data: Any) -> int:
                    if msg == BFFM_INITIALIZED:
                        if init_ptr:
                            user32.SendMessageW(hwnd, BFFM_SETSELECTIONW, 1, init_ptr)
                        user32.SetWindowPos(
                            hwnd, wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
                        )
                        user32.SetForegroundWindow(hwnd)
                    return 0

                cb = BFFCALLBACK(_browse_cb)
                disp = ctypes.create_unicode_buffer(4096)
                bi = BROWSEINFOW()
                bi.hwndOwner = owner
                bi.pszDisplayName = ctypes.cast(disp, wintypes.LPWSTR)
                bi.lpszTitle = "Select Terraform Infrastructure Folder for ARGUS Local Scan"
                bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE | BIF_EDITBOX | BIF_NONEWFOLDERBUTTON
                bi.lpfn = cb
                pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
                if pidl:
                    try:
                        out = ctypes.create_unicode_buffer(4096)
                        if shell32.SHGetPathFromIDListW(pidl, out):
                            val = out.value.strip()
                            result_box["path"] = val or None
                    finally:
                        ole32.CoTaskMemFree(pidl)
        finally:
            if owner:
                user32.DestroyWindow(owner)
            if hr in (0, 1):
                ole32.CoUninitialize()

    t = threading.Thread(target=_run_sta, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive() and owner_box:
        try:
            WM_CLOSE = 0x0010
            GW_OWNER = 4
            user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetWindow.restype = wintypes.HWND
            user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            owner_hwnd = owner_box[0]

            @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def _close_owned(hwnd: Any, _lp: Any) -> bool:
                if user32.GetWindow(hwnd, GW_OWNER) == owner_hwnd:
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                return True

            user32.EnumWindows(_close_owned, 0)
            t.join(timeout=1.0)
        except Exception:
            pass
    return result_box["path"]


def pick_local_path(mode: str = "folder", *, initial_dir: Optional[str] = None) -> Optional[str]:
    """Open a native OS Folder or .gguf File picker safely from local desktop mode."""
    if mode not in ("folder", "gguf"):
        raise ValueError(f"Unsupported picker mode: {mode!r}")

    if os.environ.get("ARGUS_HEADLESS") == "1":
        return None

    if not _DIALOG_LOCK.acquire(blocking=False):
        return None

    try:
        resolved_init = _resolve_initial_dir(mode, initial_dir)
        if os.name == "nt":
            try:
                return _pick_win32_native(mode, resolved_init, timeout=180.0)
            except Exception:
                return None

        # Non-Windows fallback using tkinter if DISPLAY exists
        if not os.environ.get("DISPLAY"):
            return None
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            if mode == "folder":
                sel = filedialog.askdirectory(title="Select Terraform Folder", initialdir=resolved_init)
            else:
                sel = filedialog.askopenfilename(
                    title="Select GGUF Model",
                    initialdir=resolved_init,
                    filetypes=[("GGUF Model", "*.gguf"), ("All Files", "*.*")],
                )
            root.destroy()
            return sel or None
        except Exception:
            return None
    finally:
        _DIALOG_LOCK.release()
