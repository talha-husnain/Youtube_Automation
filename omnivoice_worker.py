"""Runs INSIDE OmniVoice's own venv (local_voice.py starts it): reads a job file, loads the model once,
voices every item, writes ``<job>.out.json``. Imports nothing from this repo.

Job: {"device": "auto"|"cpu"|"xpu", "steps": 16,
      "prompts": {"<path.pt>": {"instruct": "...", "text": "..."}},   # made once when missing
      "items": [{"text", "out", "prompt"?, "speed"?}]}
"""
import json
import os
import sys


def main(job_path):
    with open(job_path, encoding="utf-8") as f:
        job = json.load(f)
    import soundfile as sf
    import torch
    from omnivoice import OmniVoice, VoiceClonePrompt

    dev = job.get("device") or "auto"
    if dev == "auto":
        dev = "xpu" if getattr(torch, "xpu", None) is not None and torch.xpu.is_available() else "cpu"
    model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map=dev,
                                      dtype=torch.float16 if dev == "xpu" else torch.float32, asr_device="cpu")
    steps = int(job.get("steps") or 16)
    for path, spec in (job.get("prompts") or {}).items():
        if os.path.exists(path):
            continue
        # A designed voice comes out a little different on every call, so one reference line is made once
        # and every later line clones it: the same narrator in every video.
        ref = model.generate(text=spec["text"], instruct=spec["instruct"], num_step=32)[0]
        wav = path[:-3] + ".wav"
        sf.write(wav, ref, 24000, subtype="PCM_16")
        model.create_voice_clone_prompt(ref_audio=wav, ref_text=spec["text"]).save(path)
    loaded, results = {}, []
    for it in job["items"]:
        try:
            kw = {"text": it["text"], "num_step": steps}
            if it.get("speed"):
                kw["speed"] = float(it["speed"])
            if it.get("prompt"):
                if it["prompt"] not in loaded:
                    loaded[it["prompt"]] = VoiceClonePrompt.load(it["prompt"])
                kw["voice_clone_prompt"] = loaded[it["prompt"]]
            audio = model.generate(**kw)[0]
            sf.write(it["out"], audio, 24000, subtype="PCM_16")
            results.append({"out": it["out"], "seconds": round(len(audio) / 24000, 3)})
        except Exception as e:  # noqa: BLE001 — one bad line must not lose the others
            results.append({"out": it["out"], "error": f"{type(e).__name__}: {e}"[:300]})
        print(f"voiced {len(results)}/{len(job['items'])}", flush=True)
    with open(job_path + ".out.json", "w", encoding="utf-8") as f:
        json.dump({"device": dev, "results": results}, f, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1])
