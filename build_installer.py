"""Build RemoveBG.zip: a folder a stranger can unzip and double click.

The payload is a PyInstaller onedir build of remove_bg.py, so the machine it
lands on needs no Python, no pip, and no internet until it fetches a model.
That replaces the old self-extracting .bat, which needed a compatible Python
to already be installed and pulled 400 MB of wheels at install time.

Usage:
    python build_installer.py             build the exe, then the zip
    python build_installer.py --zip-only  re-zip whatever is already staged

Needs a Python with: pyinstaller, numpy, onnxruntime, pillow, pillow-heif.
Build from a throwaway venv so nothing else in site-packages gets collected.
"""

import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
BUILD = os.path.join(HERE, "build")
STAGE = os.path.join(BUILD, "RemoveBG")
OUT = os.path.join(HERE, "RemoveBG.zip")

PAYLOAD = ["removebg"]                       # the onedir folder pyinstaller makes
EXTRAS = ["install.bat", "uninstall.bat", "README.txt"]
KEEP_OUT = ("test.png", "test_bgremoved.png", "verify.txt", "install.txt",
            "warm.txt", "uninstall.txt", "remove-bg-submenu.reg",
            "running.lock", "removebg.log")


def build_exe():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", "removebg",
        "--noconsole",                     # called from a menu: no console flash
        "--onedir",                        # onefile unpacks 139 MB on every click
        "--collect-all", "pillow_heif",    # ships libheif and its dlls
        "--exclude-module", "scipy",
        "--exclude-module", "skimage",
        "--exclude-module", "matplotlib",
        "remove_bg.py",
    ]
    print("building exe...")
    res = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stdout[-3000:])
        print(res.stderr[-3000:])
        raise SystemExit("pyinstaller failed")
    if not os.path.isfile(os.path.join(DIST, "removebg", "removebg.exe")):
        raise SystemExit("pyinstaller reported success but there is no exe")
    print("  exe built")


def stage():
    if os.path.isdir(BUILD):
        shutil.rmtree(BUILD)
    os.makedirs(STAGE)
    for name in PAYLOAD:
        shutil.copytree(os.path.join(DIST, name), os.path.join(STAGE, name))
    for name in EXTRAS:
        src = os.path.join(HERE, name)
        if not os.path.isfile(src):
            raise SystemExit("missing %s, it is part of the package" % name)
        shutil.copy2(src, os.path.join(STAGE, name))
    for name in KEEP_OUT:
        p = os.path.join(STAGE, "removebg", name)
        if os.path.exists(p):
            os.remove(p)


def zip_it():
    if os.path.exists(OUT):
        os.remove(OUT)
    n = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, _dirs, files in os.walk(STAGE):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, "RemoveBG/" + os.path.relpath(full, STAGE))
                n += 1
    return n


def main():
    if "--zip-only" not in sys.argv:
        build_exe()
        stage()
    elif not os.path.isdir(STAGE):
        raise SystemExit("nothing staged, run without --zip-only first")
    n = zip_it()
    raw = sum(os.path.getsize(os.path.join(r, f))
              for r, _d, fs in os.walk(STAGE) for f in fs)
    print("%s  %d files  %.0f MB on disk  %.0f MB zipped"
          % (os.path.basename(OUT), n, raw / 1e6, os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()
