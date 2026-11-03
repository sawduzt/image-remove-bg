# remove bg from the right-click menu

Adds **Remove Background** to the Windows right-click menu for image files, with a submenu
of three quality settings. Right click a photo, pick one, and a cut-out PNG appears next to
it. No window, no app to open.

![screenshot](docs/screenshot.jpg)

## install

Download `RemoveBG-Setup.bat` from the releases and double click it. No admin needed, it
installs per-user into `%LOCALAPPDATA%\RemoveBG` and adds the menu entries.

It will:

1. find a python (3.10 to 3.12; 3.13+ is too new for the wheels, and it will offer to
   install 3.12 with winget if you have none)
2. make a virtualenv and install `rembg[cpu]` with onnxruntime
3. download the default model so the first right-click is not a surprise stall
4. write the registry entries for jpg, jpeg, png, bmp, gif, webp, tif, tiff, heic, heif and
   avif

Then right click any image: **Remove Background > Fast / Balanced / HQ**.

Uninstall with `uninstall.bat` in the install folder.

## the three settings

| menu item | model | what it is good at |
|---|---|---|
| Fast | u2netp | about a second, fine for hard edges and graphics, mushy on fur |
| Balanced | u2net | about five seconds, the sensible default, decent on fur |
| HQ | bria-rmbg | about half a minute, best on fluffy animals and hair |

The first use of each setting downloads its model, so it needs internet once per setting.
Output is always `<originalname>_bgremoved.png` next to the source file.

If something fails you get one error dialog with a code (`RBG-W15` and so on) and the
details go to `removebg.log` in the install folder.

## how it is built

- `remove_bg.py` is the worker: takes a path and an optional model name, writes the PNG,
  stays silent unless it fails. It locates its own folder, so the install can live anywhere.
- `gen_submenu.py` writes `remove-bg-submenu.reg`, the cascading menu. It works out the
  pythonw and worker paths from its own location.
- `build_installer.py` packs the worker, the reg generator, the uninstaller and a setup
  script into one self-extracting `.bat` (base64 payloads decoded with certutil).

Rebuild the installer with `python build_installer.py`; it writes `RemoveBG-Setup.bat` next
to itself.

Registry entries go under `HKCU\Software\Classes\SystemFileAssociations\.<ext>\shell\RemoveBG`
so no elevation is involved. It changes nothing system-wide.

## credits

Windows only, python 3.10 to 3.12. Built on [rembg](https://github.com/danielgatis/rembg).

Demo photo by Alvesgaspar, CC BY-SA 3.0, via Wikimedia Commons.
