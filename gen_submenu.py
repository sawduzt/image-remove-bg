"""Generate remove-bg-submenu.reg — a cascading "Remove Background" context menu.

Pattern (battle-tested for SystemFileAssociations cascades):
  parent verb: "MUIVerb" = label (NOT the default value), plus empty "subcommands".
  children under a `shell` subkey, each with @ (default) = label + a `command` subkey.

Presets (model -> label): Fast=u2netp, Balanced=u2net, HQ=bria-rmbg.
Run in the tool dir with the venv python. Regenerate if the tool path changes.
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
PYW = os.path.join(HERE, "venv", "Scripts", "pythonw.exe")
PY = os.path.join(HERE, "remove_bg.py")
EXTS = ["jpg", "jpeg", "png", "bmp", "gif", "webp", "tif", "tiff", "heic", "heif", "avif"]
PRESETS = [("u2netp", "Fast"), ("u2net", "Balanced"), ("bria-rmbg", "HQ")]

ROOT = r"HKEY_CURRENT_USER\Software\Classes\SystemFileAssociations"


def cmd(model: str) -> str:
    # .reg escaping: backslash -> \\, quote -> \"
    s = f'"{PYW}" "{PY}" "%1" {model}'
    return s.replace("\\", "\\\\").replace('"', '\\"')


lines = [
    "Windows Registry Editor Version 5.00",
    "",
    "; Remove Background - right-click submenu (Fast/Balanced/HQ).",
    "; Regenerate if the tool path changes: python gen_submenu.py",
    "",
]
for ext in EXTS:
    base = rf"{ROOT}\.{ext}\shell\RemoveBG"
    lines += [
        f"[-{base}]",
        f"[{base}]",
        '"MUIVerb"="Remove Background"',
        '"subcommands"=""',
        f"[{base}\\shell]",
    ]
    for model, label in PRESETS:
        sub = rf"{base}\shell\{label}"
        lines += [
            f"[{sub}]",
            f'@="{label}"',
            f"[{sub}\\command]",
            f'@="{cmd(model)}"',
        ]
    lines.append("")

with open("remove-bg-submenu.reg", "w", newline="") as f:
    f.write("\n".join(lines))
print(f"wrote remove-bg-submenu.reg ({len(lines)} lines)")
