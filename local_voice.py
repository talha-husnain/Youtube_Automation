"""A free voice that runs on this laptop: OmniVoice (k2-fsa/OmniVoice, 600+ languages, Urdu and Hindi
included), used when the edge voice cannot read a line, before the paid Gemini voice.

Why: edge-tts is Microsoft's unofficial read-aloud service; whenever it rested (403/429, outages) every
line went to Gemini. On 22-oct-2026 OmniVoice read an Urdu history narration and a Quran translation
line that Whisper heard back word for word, on the CPU at ~5.4x real time (16 steps); a cloned voice
ran ~12x. Slow, so it is the fallback, not the default (VOICE_ENGINE=omni puts it first).

Licences: code Apache-2.0; its audio tokenizer is Boson AI's Higgs Audio 2 community licence (Llama 3
style): commercial use allowed, the credit "Built with Higgs Materials licensed from Boson AI USA, Inc."
on a related about page, and an expanded licence needed past 100,000 annual active users.

It runs in its own venv (torch + transformers 5, D:/youtube/oss/OmniVoice) through omnivoice_worker.py,
one process per batch of lines, so its packages never meet ours. LOCAL_VOICE=0 turns it off.
"""
import json
import os
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(ROOT, "omnivoice_worker.py")
VOICES_DIR = os.path.join(ROOT, "state", "voices")
OSS = r"D:\youtube\oss\OmniVoice"
STEPS = int(os.environ.get("OMNIVOICE_STEPS") or 16)
DESIGN = {"male": "male, middle-aged, low pitch", "female": "female, young adult, moderate pitch"}
# The one reference line each narrator is cloned from (Urdu, ~5 s): see omnivoice_worker.
REFERENCE = "السلام علیکم، آج ہم آپ کو ایک بہت دلچسپ کہانی سناتے ہیں۔"
# Urdu runs ~15 characters a second of speech, so 2,000 is ~2 minutes of voice and ~25 minutes of CPU
# with a cloned voice: a long video's whole narration would hold the one-job channel loop for hours.
MAX_CHARS = int(os.environ.get("LOCAL_VOICE_MAX_CHARS") or 2000)
LOAD_SECONDS = 180       # torch + model load, and making a missing reference voice
PER_ITEM_SECONDS = 240   # a long line on the CPU with a cloned voice


def python():
    if os.environ.get("OMNIVOICE_PYTHON"):
        return os.environ["OMNIVOICE_PYTHON"]
    import glob
    # .venv-xpu has PyTorch's Intel Arc build, but the Arc driver here (31.0.101.4502, 2023) is too old
    # for it: torch.xpu saw no device on 22-oct-2026. After a driver update set OMNIVOICE_PYTHON to it.
    for venv in (".venv",):
        exe = os.path.join(OSS, venv, "Scripts", "python.exe")
        # A venv whose install has not finished has python.exe but no omnivoice yet.
        if os.path.isfile(exe) and glob.glob(os.path.join(OSS, venv, "Lib", "site-packages", "omnivoice-*.dist-info")):
            return exe
    return ""


def available():
    return os.environ.get("LOCAL_VOICE", "1").strip() != "0" and os.path.isfile(python()) and os.path.isfile(WORKER)


def speed_of(rate):
    """edge's "+12%" -> 1.12."""
    try:
        return round(1 + float(str(rate).strip().rstrip("%")) / 100, 3)
    except ValueError:
        return 1.0


def prompt_path(gender):
    return os.path.join(VOICES_DIR, f"omni_{'female' if gender == 'female' else 'male'}.pt")


def speak_many(jobs, run=subprocess.run):
    """jobs: [(text, wav path, "male"|"female", edge rate)] -> [seconds | None] per job, one worker
    process for all of them. Never raises: a line it cannot voice is None (Gemini takes it)."""
    if not jobs or not available():
        return [None] * len(jobs)
    if sum(len(t) for t, *_ in jobs) > MAX_CHARS:
        print(f"   ℹ️ {len(jobs)} lines are too long for the local voice; Gemini reads them.")
        return [None] * len(jobs)
    os.makedirs(VOICES_DIR, exist_ok=True)
    prompts = {prompt_path(g): {"instruct": DESIGN["female" if g == "female" else "male"], "text": REFERENCE}
               for _t, _p, g, _r in jobs}
    job = {"device": os.environ.get("OMNIVOICE_DEVICE") or "auto", "steps": STEPS, "prompts": prompts,
           "items": [{"text": t, "out": p, "prompt": prompt_path(g), "speed": speed_of(r)} for t, p, g, r in jobs]}
    fd, path = tempfile.mkstemp(prefix="omnivoice_", suffix=".json")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False)
        # The model is cached: offline skips Hugging Face's checks, which are slow on this connection.
        env = {**os.environ, "HF_HUB_OFFLINE": "1", "PYTHONIOENCODING": "utf-8"}
        run([python(), "-I", WORKER, path], check=True, capture_output=True, env=env,
            timeout=LOAD_SECONDS + PER_ITEM_SECONDS * len(jobs))
        with open(path + ".out.json", encoding="utf-8") as f:
            got = {r["out"]: r for r in json.load(f)["results"]}
    except Exception as e:  # noqa: BLE001 — the paid voice is the fallback
        detail = getattr(e, "stderr", b"") or b""
        print(f"   ⚠️ Local voice failed ({type(e).__name__}: {detail[-200:].decode('utf-8', 'replace') if detail else e}).")
        return [None] * len(jobs)
    finally:
        for p in (path, path + ".out.json"):
            if os.path.exists(p):
                os.remove(p)
    out = []
    for _t, p, _g, _r in jobs:
        r = got.get(p) or {}
        out.append(r.get("seconds") if r.get("seconds") and os.path.isfile(p) else None)
    return out
