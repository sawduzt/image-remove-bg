"""Remove BG worker. Silent on success, loud (one dialog + log) on failure.

Usage: pythonw remove_bg.py <image> [model]
Codes: RBG-W05 no input, W10 missing file, W11 unreadable, W15 rembg broken,
       W20 model load/download, W25 processing, W30 cannot save, W99 unexpected.
Set RBG_NO_DIALOG=1 to suppress the popup (logs still written).
"""

import os
import sys
import time
import traceback

DEFAULT_MODEL = "u2net"  # Balanced
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "removebg.log")
MAX_LOG = 512 * 1024


def _log(line: str) -> None:
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > MAX_LOG:
            with open(LOG, "rb") as f:
                f.seek(-(MAX_LOG // 2), os.SEEK_END)
                tail = f.read()
            with open(LOG, "wb") as f:
                f.write(b"...trimmed...\n" + tail)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line))
    except Exception:
        pass  # logging must never be the thing that breaks


def _dialog(code: str, human: str) -> None:
    if os.environ.get("RBG_NO_DIALOG"):
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            "Remove BG could not finish.\n\n"
            "Error code:  RBG-%s\n\n%s\n\n"
            "Details were saved to:\n%s\n\n"
            "Send the error code to whoever gave you this tool." % (code, human, LOG),
            "Remove BG  -  error RBG-%s" % code,
            0x10,  # MB_ICONERROR
        )
    except Exception:
        pass


def fail(code: str, human: str, exc: bool = False):
    _log("FAIL RBG-%s  %s" % (code, human))
    if exc:
        _log(traceback.format_exc().strip())
    _dialog(code, human)
    digits = "".join(c for c in code if c.isdigit())
    sys.exit(int(digits) if digits else 1)


def process(path: str, model: str = DEFAULT_MODEL) -> str:
    t0 = time.time()
    if not os.path.isfile(path):
        fail("W10", "This file could not be found:\n%s" % path)

    base, _ = os.path.splitext(path)
    # rembg always returns PNG (alpha) bytes, so the output is always .png.
    out_path = base + "_bgremoved.png"

    try:
        from rembg import remove, new_session
    except Exception:
        fail("W15", "The rembg library is missing or damaged.\nRe-run the installer.", exc=True)

    try:
        session = new_session(model)
    except Exception:
        fail("W20", "Could not load the '%s' model.\nThe first use of each quality "
                    "setting needs an internet connection." % model, exc=True)

    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        fail("W11", "This image could not be read.\nIt may be locked by another program.", exc=True)

    try:
        result = remove(data, session=session)
    except Exception:
        fail("W25", "This image could not be processed.\nIt may be corrupt or an "
                    "unsupported format.", exc=True)

    try:
        with open(out_path, "wb") as f:
            f.write(result)
    except Exception:
        fail("W30", "The result could not be saved.\nThe folder may be read-only "
                    "or the disk full.", exc=True)

    _log("ok  model=%s  %.1fs  in=%s  out=%s" % (model, time.time() - t0, path, out_path))
    return out_path


if __name__ == "__main__":
    try:
        if len(sys.argv) < 2:
            fail("W05", "No image file was passed to the tool.")
        process(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL)
    except SystemExit:
        raise
    except Exception:
        fail("W99", "An unexpected error occurred.", exc=True)
