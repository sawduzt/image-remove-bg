"""Remove BG worker and installer. One exe, no Python needed on the machine.

Modes
  removebg.exe <image> [fast|balanced|hq]   cut the background out (menu calls this)
  removebg.exe --install [--dry-run]        write + import the right-click menu
  removebg.exe --uninstall                  take the menu back out
  removebg.exe --verify                     check the install end to end
  removebg.exe --warm [fast|balanced|hq]    download a model now, with a progress bar

Error codes (worker): RBG-W05 no input, W10 missing file, W11 unreadable,
W15 backend broken, W20 model load or download, W25 processing, W30 cannot
save, W31 another run is still working, W99 unexpected.

Set RBG_NO_DIALOG=1 to suppress the popup (the log is still written).

No rembg dependency: the model is run straight through onnxruntime, so the
alpha matting stack (scipy, scikit-image, numba, llvmlite, pymatting, about
430 MB of it) is not shipped and never imported. The maths is the same as
rembg's own session classes, and models are read from the same place rembg
kept them, so an existing download is reused.
"""

import hashlib
import io
import os
import sys
import time
import traceback
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    HERE = os.path.dirname(sys.executable)

LOG = os.path.join(HERE, "removebg.log")
MAX_LOG = 512 * 1024
LOCK = os.path.join(HERE, "running.lock")
REG_FILE = os.path.join(HERE, "remove-bg-submenu.reg")

# label -> (model key, file names on disk, url, checksum)
# fast 4.6 MB, balanced 176 MB, hq 1.02 GB. The models are the only big thing.
MODELS = {
    "fast": ("u2netp", ["u2netp.onnx"],
             "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx",
             "md5:8e83ca70e441ab06c318d82300c84806"),
    "balanced": ("u2net", ["u2net.onnx"],
                 "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
                 "md5:60024c5c889badc19c04ad937298a77b"),
    "hq": ("bria-rmbg", ["bria-rmbg-2.0.onnx"],
           "https://github.com/danielgatis/rembg/releases/download/v0.0.0/bria-rmbg-2.0.onnx",
           "sha256:5b486f08200f513f460da46dd701db5fbb47d79b4be4b708a19444bcd4e79958"),
}
DEFAULT = "balanced"

# SystemFileAssociations is Explorer's classic per-type menu.
EXTS = ["jpg", "jpeg", "png", "bmp", "gif", "webp", "tif", "tiff", "heic", "heif", "avif"]
LABELS = [("fast", "Fast"), ("balanced", "Balanced"), ("hq", "HQ")]


# ---------------------------------------------------------------- plumbing
def _log(line):
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
        pass


_SAY_SINK = None


def _report(name):
    """Dump what _say collected into a file next to the exe."""
    path = os.path.join(HERE, name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("remove bg %s\n%s\n\n%s\n" % (
                name, time.strftime("%Y-%m-%d %H:%M:%S"),
                "\n".join(_SAY_SINK or [])))
        return path
    except Exception:
        return LOG


def _say(msg=""):
    """Print for a console, and always write to the log so a windowed exe
    still leaves a record of what --install or --verify did."""
    _log(msg)
    try:
        sys.stdout.write(str(msg) + "\n")
        sys.stdout.flush()
    except Exception:
        pass
    if _SAY_SINK is not None:
        _SAY_SINK.append(str(msg))


def _dialog(title, body, icon=0x10):
    if os.environ.get("RBG_NO_DIALOG"):
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, body, title, icon)
    except Exception:
        pass


def fail(code, human, exc=False):
    _log("FAIL RBG-%s  %s" % (code, human))
    if exc:
        _log(traceback.format_exc().strip())
    _dialog("Remove BG  -  error RBG-%s" % code,
            "Remove BG could not finish.\n\n"
            "Error code:  RBG-%s\n\n%s\n\n"
            "Details were saved to:\n%s\n\n"
            "Send the error code to whoever gave you this tool." % (code, human, LOG))
    digits = "".join(c for c in code if c.isdigit())
    sys.exit(int(digits) if digits else 1)


def models_dir():
    """Where rembg has always kept them, so an old download is reused."""
    home = os.environ.get("REMBG_HOME") or os.environ.get("U2NET_HOME")
    if home:
        return os.path.expanduser(home)
    return os.path.join(os.path.expanduser("~"), ".rembg")


def legacy_dir():
    return os.path.expanduser(os.environ.get("U2NET_HOME")
                              or os.path.join(os.path.expanduser("~"), ".u2net"))


def find_model(label):
    key, names = MODELS[label][0], MODELS[label][1]
    for name in names:
        for d in (os.path.join(models_dir(), "models", key), legacy_dir()):
            p = os.path.join(d, name)
            if os.path.isfile(p) and os.path.getsize(p) > 1024:
                return p
    return None


def check_model(path, want):
    kind, digest = want.split(":", 1)
    h = hashlib.new(kind)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().lower() == digest.lower()


# ---------------------------------------------------------------- download
def download(label, quiet=False):
    """Fetch a model, showing a progress window so it never looks hung."""
    key, names, url, want = MODELS[label]
    dest_dir = os.path.join(models_dir(), "models", key)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, names[0])
    part = dest + ".part"

    bar = None if quiet else _Progress("downloading the %s model" % label,
                                       "one time, it stays on disk")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "removebg"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            with open(part, "wb") as out:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    got += len(chunk)
                    if bar:
                        bar.set(("%.0f MB of %.0f MB" % (got / 1e6, total / 1e6)) if total
                                else "%.0f MB" % (got / 1e6),
                                (got / total) if total else 0.0)
        if not check_model(part, want):
            os.remove(part)
            raise ValueError("downloaded file did not match its checksum")
        os.replace(part, dest)
        return dest
    finally:
        if bar:
            bar.close()
        if os.path.exists(part):
            try:
                os.remove(part)
            except Exception:
                pass


class _Progress(object):
    """Tiny tk progress window. If tk is missing it just runs silent."""

    def __init__(self, title, sub):
        self.root = None
        try:
            import tkinter as tk
            from tkinter import ttk
            self.root = tk.Tk()
            self.root.title("Remove BG")
            self.root.resizable(False, False)
            self.root.attributes("-topmost", True)
            frm = tk.Frame(self.root, padx=18, pady=14)
            frm.pack()
            tk.Label(frm, text="Remove BG  -  %s" % title,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(frm, text=sub, fg="#555555").pack(anchor="w", pady=(2, 8))
            self.bar = ttk.Progressbar(frm, length=340, maximum=1.0)
            self.bar.pack()
            self.msg = tk.Label(frm, text="", fg="#555555")
            self.msg.pack(anchor="w", pady=(6, 0))
            self.root.update()
        except Exception:
            self.root = None

    def set(self, text, frac):
        if self.root is None:
            return
        try:
            self.msg.configure(text=text)
            self.bar["value"] = max(0.0, min(1.0, frac))
            self.root.update()
        except Exception:
            pass

    def close(self):
        if self.root is None:
            return
        try:
            self.root.destroy()
        except Exception:
            pass
        self.root = None


# ---------------------------------------------------------------- inference
def _session(path):
    import onnxruntime as ort
    ort.set_default_logger_severity(3)
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    return ort.InferenceSession(path, sess_options=opts,
                               providers=["CPUExecutionProvider"])


def _predict(sess, img):
    """Foreground mask for one image. Same maths rembg's sessions use."""
    import numpy as np
    from PIL import Image

    shape = sess.get_inputs()[0].shape
    try:
        h, w = int(shape[2]), int(shape[3])
    except Exception:
        h = w = 320  # u2netp and u2net; anything else should always report a shape
    im = img.convert("RGB").resize((w, h), Image.Resampling.LANCZOS)
    arr = np.asarray(im, dtype=np.float32)
    arr = arr / max(float(arr.max()), 1e-6)
    mean = (0.485, 0.456, 0.406)
    std = (0.229, 0.224, 0.225)
    t = np.zeros((h, w, 3), dtype=np.float32)
    for c in range(3):
        t[:, :, c] = (arr[:, :, c] - mean[c]) / std[c]
    t = np.expand_dims(t.transpose((2, 0, 1)), 0)

    out = sess.run(None, {sess.get_inputs()[0].name: t})[0][:, 0, :, :]
    ma, mi = float(out.max()), float(out.min())
    out = (out - mi) / (ma - mi + 1e-6)
    mask = Image.fromarray((np.squeeze(out) * 255).astype("uint8"), mode="L")
    return mask.resize(img.size, Image.Resampling.LANCZOS)


def _lock(timeout=120):
    """One run at a time: three right-clicks must not load three models."""
    try:
        import msvcrt
        f = open(LOCK, "a+")
        for _ in range(int(timeout / 0.5)):
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                return f
            except OSError:
                time.sleep(0.5)
        return None
    except Exception:
        return True  # no locking available, better to run than to refuse


def _unlock(f):
    try:
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        f.close()
    except Exception:
        pass


def process(path, label=DEFAULT):
    t0 = time.time()
    if label not in MODELS:
        label = DEFAULT
    if not os.path.isfile(path):
        fail("W10", "This file could not be found:\n%s" % path)

    lock = _lock()
    if lock is None:
        fail("W31", "Remove BG is already working on an image.\n"
                    "Wait for that to finish, then try again.")

    try:
        from PIL import Image, ImageOps
    except Exception:
        fail("W15", "The imaging backend is missing or damaged.\nRe-run the installer.",
             exc=True)
    try:
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
    except Exception:
        fail("W15", "The background removal backend is missing or damaged.\n"
                    "Re-run the installer.", exc=True)

    # heic and heif are common (anything off an iphone) and Pillow cannot read
    # them by itself, so the plugin is registered here when it is present.
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass

    model = find_model(label)
    if model is None:
        _log("model %s missing, downloading" % label)
        try:
            model = download(label)
        except Exception:
            fail("W20", "The '%s' model could not be downloaded.\n"
                        "The first use of each setting needs an internet connection."
                 % label, exc=True)

    try:
        sess = _session(model)
    except Exception:
        fail("W20", "Could not load the '%s' model from\n%s" % (label, model), exc=True)

    try:
        with open(path, "rb") as f:
            raw = f.read()
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        fail("W11", "This image could not be read.\n"
                    "It may be locked by another program.", exc=True)

    try:
        img = ImageOps.exif_transpose(img) or img
        alpha = _predict(sess, img)
        out = img.convert("RGBA")
        out.putalpha(alpha)
    except Exception:
        fail("W25", "This image could not be processed.\n"
                    "It may be corrupt or an unsupported format.", exc=True)

    base, _ = os.path.splitext(path)
    out_path = base + "_bgremoved.png"
    n = 2
    while os.path.exists(out_path):
        out_path = "%s_bgremoved (%d).png" % (base, n)
        n += 1
    try:
        out.save(out_path, "PNG", optimize=True)
    except Exception:
        fail("W30", "The result could not be saved.\n"
                    "The folder may be read-only or the disk full.", exc=True)

    _log("ok  model=%s  %.1fs  in=%s  out=%s"
         % (label, time.time() - t0, path, out_path))
    _unlock(lock)
    return out_path


# ---------------------------------------------------------------- install
def _cmd(label):
    exe = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
    s = '"%s" "%%1" %s' % (exe, label)
    return s.replace("\\", "\\\\").replace('"', '\\"')


def build_reg():
    """Written as UTF-16LE so a non-ASCII user name in the path survives."""
    root = r"HKEY_CURRENT_USER\Software\Classes\SystemFileAssociations"
    lines = ["Windows Registry Editor Version 5.00", "",
             "; Remove Background - right-click submenu (Fast/Balanced/HQ).",
             "; Written by removebg.exe --install", ""]
    for ext in EXTS:
        base = r"%s\.%s\shell\RemoveBG" % (root, ext)
        lines += ["[-%s]" % base, "[%s]" % base,
                  '"MUIVerb"="Remove Background"', '"subcommands"=""',
                  "[%s\\shell]" % base]
        for key, name in LABELS:
            sub = "%s\\shell\\%s" % (base, name)
            lines += ["[%s]" % sub, '@="%s"' % name,
                      "[%s\\command]" % sub, '@="%s"' % _cmd(key)]
        lines.append("")
    return "\r\n".join(lines)


def install(dry_run=False):
    text = build_reg()
    with open(REG_FILE, "wb") as f:
        f.write(b"\xff\xfe" + text.encode("utf-16-le"))
    _say("  registry file written (%d extensions)" % len(EXTS))
    if dry_run:
        _say("  dry run, nothing imported")
        return 0
    err = os.system('reg import "%s" >nul 2>&1' % REG_FILE)
    if err != 0:
        _say("  ERROR: Windows refused the registry change (RBG-41)")
        _say("  A work or school policy can block this.")
        return 41
    _say("  right-click menu registered")
    _say("  windows 11 hides it behind 'show more options'")
    return 0


def uninstall():
    for ext in EXTS:
        os.system('reg delete "HKCU\\Software\\Classes\\SystemFileAssociations\\.%s'
                  '\\shell\\RemoveBG" /f >nul 2>&1' % ext)
    _say("  right-click menu removed")
    _say("  models are kept in %s" % models_dir())
    _say("  delete that folder and this one to reclaim the space")
    return 0


def verify():
    ok = True
    for mod in ("numpy", "onnxruntime", "PIL"):
        try:
            __import__(mod)
            _say("  %-10s ok" % mod)
        except Exception as e:
            _say("  %-10s BROKEN (%s)" % (mod, e))
            ok = False
    try:
        import pillow_heif  # noqa: F401
        _say("  %-10s ok" % "heic")
    except Exception:
        _say("  %-10s missing, heic files will fail" % "heic")
    for label in MODELS:
        path = find_model(label)
        _say("  %-10s %s" % (label, path if path else "not downloaded yet"))
    if not ok:
        return 30

    # one real end to end pass on a generated image, nothing written to disk
    label = "fast" if find_model("fast") else ("balanced" if find_model("balanced") else None)
    if label is None:
        _say("  end to end: skipped, no model downloaded yet")
        return 0
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (320, 240), (255, 255, 255))
        ImageDraw.Draw(img).ellipse((80, 40, 240, 200), fill=(200, 40, 90))
        alpha = _predict(_session(find_model(label)), img)
        lo, hi = alpha.getextrema()
        _say("  end to end: ok on %s (alpha range %d-%d)" % (label, lo, hi))
        return 0
    except Exception as e:
        _say("  end to end: FAILED (%s)" % e)
        _log("verify failed: %s" % e)
        return 31


def main(argv):
    global _SAY_SINK
    args = list(argv[1:])
    if not args:
        fail("W05", "No image file was passed to the tool.")
    head = args[0].lower()
    if head in ("--install", "-i"):
        _SAY_SINK = []
        rc = install(dry_run="--dry-run" in args)
        _report("install.txt")
        if rc:
            _dialog("Remove BG  -  install failed",
                    "The right-click menu could not be registered.\n\n"
                    "Error code: RBG-%d\n\nLog: %s" % (rc, LOG))
        return rc
    if head in ("--uninstall", "-u"):
        _SAY_SINK = []
        rc = uninstall()
        _report("uninstall.txt")
        return rc
    if head in ("--verify", "-v"):
        _SAY_SINK = []
        rc = verify()
        path = _report("verify.txt")
        if rc:
            _dialog("Remove BG  -  check failed",
                    "Something is broken in this install.\n\n"
                    "Error code: RBG-%d\n\nReport: %s" % (rc, path))
        return rc
    if head in ("--warm", "-w"):
        _SAY_SINK = []
        label = args[1] if len(args) > 1 and args[1] in MODELS else DEFAULT
        if find_model(label):
            _say("  the %s model is already here" % label)
            return 0
        _say("  fetching the %s model" % label)
        try:
            download(label)
        except Exception as e:
            _say("  download failed: %s" % e)
            _dialog("Remove BG  -  download failed",
                    "The %s model could not be downloaded.\n\n%s" % (label, e))
            return 20
        _say("  done")
        _report("warm.txt")
        return 0
    process(args[0], args[1] if len(args) > 1 else DEFAULT)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except SystemExit:
        raise
    except Exception:
        fail("W99", "An unexpected error occurred.", exc=True)
