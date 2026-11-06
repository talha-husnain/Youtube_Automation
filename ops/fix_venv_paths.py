"""Re-point a moved venv's launchers at where the venv lives now.

Run it with the venv's own python, e.g.  .venv\\Scripts\\python.exe ops\\fix_venv_paths.py

Why: a Windows venv's Scripts\\*.exe (pip, pytest, uvicorn, edge-tts, ...) carry
the ABSOLUTE path of the python.exe they were installed with. The project was
made at D:\\youtube\\Automate (a junction to the external F: disk) and moved to
D:\\Shortkaar on 4-nov-2026: every launcher still started F:'s old copy, so
``.venv\\Scripts\\pip install x`` installed into the OLD venv and the launchers
failed outright whenever F: was not plugged in. python.exe itself is fine (it
reads pyvenv.cfg next to it), which is why ``python -m uvicorn`` kept working.

What it does, only inside this venv:
- rebuilds each console/gui-script launcher that names another python, from
  the installed packages' entry points, with pip's own ScriptMaker;
- fixes ``#!`` lines of plain scripts in Scripts\\ and the hard-coded
  VIRTUAL_ENV in the activate scripts;
- fixes pyvenv.cfg's ``command =`` line (informational).
``--dry-run`` only lists what it would change.
"""
import importlib.metadata as md
import os
import re
import sys

DRY = "--dry-run" in sys.argv


def main():
    venv = sys.prefix
    if venv == sys.base_prefix:
        sys.exit("Run this with the venv's python, not the system one.")
    scripts = os.path.join(venv, "Scripts" if os.name == "nt" else "bin")
    exe = os.path.join(scripts, "python.exe" if os.name == "nt" else "python")
    me = os.path.normcase(os.path.abspath(exe)).encode("utf-8", "replace")

    specs = {}
    for dist in md.distributions():
        for ep in dist.entry_points:
            if ep.group in ("console_scripts", "gui_scripts"):
                specs.setdefault(ep.name.lower(), (ep.name, ep.value, ep.group == "gui_scripts"))
    # pip installs version-suffixed copies of its own launcher (pip3.14.exe).
    ver = f"{sys.version_info[0]}.{sys.version_info[1]}"
    for base in ("pip", "pip3"):
        if base in specs:
            specs.setdefault(f"pip{ver}", (f"pip{ver}",) + specs[base][1:])

    stale, fixed, failed, unknown = [], [], [], []
    for name in sorted(os.listdir(scripts)):
        path = os.path.join(scripts, name)
        stem, ext = os.path.splitext(name)
        if ext.lower() != ".exe" or stem.lower() in ("python", "pythonw"):
            continue
        with open(path, "rb") as f:
            data = f.read()
        m = re.search(rb"#!([^\r\n]*python[w]?\.exe)", data, re.I)
        if not m or os.path.normcase(m.group(1).decode("utf-8", "replace").strip('"')).encode("utf-8", "replace") == me:
            continue
        stale.append(name)
        spec = specs.get(stem.lower())
        if not spec:
            unknown.append(name)
            continue
        if DRY:
            continue
        try:
            from pip._vendor.distlib.scripts import ScriptMaker
            maker = ScriptMaker(None, scripts, add_launchers=True)
            maker.executable = exe
            maker.clobber = True
            maker.variants = {""}
            ep_name, value, gui = spec
            maker.make(f"{stem} = {value}", {"gui": gui} if gui else None)
            fixed.append(name)
        except Exception as e:  # noqa: BLE001 — a launcher in use, say, stays as it was
            failed.append(f"{name} ({type(e).__name__}: {e})")

    texts = []
    for name in sorted(os.listdir(scripts)):
        path = os.path.join(scripts, name)
        if not os.path.isfile(path) or name.lower().endswith((".exe", ".dll", ".pyd")):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        if text.startswith("#!") and "python" in text.splitlines()[0].lower():
            first, _, rest = text.partition("\n")
            if os.path.normcase(first[2:].strip().strip('"')) != os.path.normcase(exe):
                new = f"#!{exe}\n{rest}"
        if name.lower().startswith("activate"):
            new = re.sub(r'(set "VIRTUAL_ENV=)[^"]*(")', lambda mm: mm.group(1) + venv + mm.group(2), new)
            new = re.sub(r"(VIRTUAL_ENV=')[^']*(')", lambda mm: mm.group(1) + venv.replace("\\", "/") + mm.group(2), new)
        if new != text:
            texts.append(name)
            if not DRY:
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(new)

    cfg = os.path.join(venv, "pyvenv.cfg")
    cfg_fixed = False
    with open(cfg, encoding="utf-8") as f:
        c = f.read()
    nc = re.sub(r"(?m)^(command\s*=.*-m venv\s+).*$", lambda mm: mm.group(1) + venv, c)
    if nc != c:
        cfg_fixed = True
        if not DRY:
            with open(cfg, "w", encoding="utf-8", newline="") as f:
                f.write(nc)

    print(f"venv: {venv}")
    print(f"launchers naming another python: {len(stale)}"
          + ("" if DRY else f", rebuilt {len(fixed)}, failed {len(failed)}"))
    for x in failed:
        print("  failed:", x)
    for x in unknown:
        print("  no entry point found (left as is):", x)
    print(f"text scripts fixed: {', '.join(texts) or 'none'}")
    print(f"pyvenv.cfg command line fixed: {cfg_fixed}")
    if DRY:
        print("(dry run: nothing changed)")


if __name__ == "__main__":
    main()
