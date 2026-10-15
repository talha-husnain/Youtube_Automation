"""JSON state files that survive a damaged write.

The channels, their upload logs and tokens are JSON files rewritten every
minute. A file that cannot be read used to come back as "empty": every
channel's settings and history gone without a word, and the next write made
it permanent. Each write here keeps the last good copy as ``<file>.bak`` (at
most once an hour, so a bad minute cannot overwrite a good hour), and a read
that finds the file damaged falls back to it. A missing file stays missing:
that is a fresh start, not damage.
"""
import json
import os
import shutil
import time

BACKUP_EVERY = 3600
BUSY_TRIES, BUSY_WAIT = 20, 0.05


def _load(path):
    # Windows refuses to open a file while another thread replaces it
    # (PermissionError): that is a busy file, not a damaged one. Read as
    # damaged, the tick got the hour-old backup and could upload a video twice.
    for k in range(BUSY_TRIES):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except PermissionError:
            if k == BUSY_TRIES - 1:
                raise
            time.sleep(BUSY_WAIT)


def _replace(tmp, path):
    for k in range(BUSY_TRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if k == BUSY_TRIES - 1:
                raise
            time.sleep(BUSY_WAIT)


def read(path, default):
    try:
        data = _load(path)
        if isinstance(data, type(default)):
            return data
    except FileNotFoundError:
        return default
    except PermissionError:
        raise                             # still busy after a second: never guess with an old copy
    except (OSError, ValueError):
        pass
    try:
        data = _load(path + ".bak")
        if isinstance(data, type(default)):
            print(f"⚠️ {os.path.basename(path)} was damaged: using its backup.")
            return data
    except (OSError, ValueError):
        pass
    return default


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    bak = path + ".bak"
    try:
        if os.path.isfile(path) and (not os.path.isfile(bak) or time.time() - os.path.getmtime(bak) > BACKUP_EVERY):
            _load(path)                   # only a file that reads back becomes the backup
            shutil.copy2(path, bak)
            os.utime(bak)
    except (OSError, ValueError):
        pass
    _replace(tmp, path)
