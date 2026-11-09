"""Where the beats are in a song, so the songs channel cuts its footage on the beat.

Plain numpy (no librosa or scipy here): ffmpeg decodes the stretch to mono 22.05 kHz, a spectral-flux
onset envelope (log-magnitude STFT, positive differences summed per frame), the tempo from its
autocorrelation between 70 and 180 BPM (a strong half/double tempo is folded into 90-160), then the
grid phase that lines up with the most onset energy, each beat nudged to the strongest onset within
a tenth of a period. Good enough for cutting pictures; not a music-analysis library.
``BEAT_CUTS=0`` turns beat cuts off.
"""
import os
import subprocess

import numpy as np

SR = 22050
HOP = 512
N_FFT = 2048


def available():
    return os.environ.get("BEAT_CUTS", "1") != "0"


def _decode(path, start, seconds):
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(0.0, start):.3f}", "-t", f"{seconds:.3f}",
                        "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, timeout=120)
    if r.returncode != 0:
        return None
    return np.frombuffer(r.stdout, dtype=np.float32)


def onset_envelope(y):
    """Spectral flux per hop (HOP / SR seconds)."""
    if y is None or len(y) < N_FFT * 2:
        return np.zeros(0, dtype=np.float32)
    n = 1 + (len(y) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    frames = y[idx] * np.hanning(N_FFT)[None, :].astype(np.float32)
    mag = np.log1p(10.0 * np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0.0, np.diff(mag, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    flux -= np.convolve(flux, np.ones(16) / 16, mode="same")    # remove the slow loudness trend
    return np.maximum(flux, 0.0)


def tempo_period(env, fps=SR / HOP):
    """The beat period in envelope frames (float), or None."""
    if len(env) < fps * 4 or not env.any():
        return None
    e = env - env.mean()
    ac = np.correlate(e, e, mode="full")[len(e) - 1:]
    lo, hi = int(fps * 60 / 180), int(fps * 60 / 70)
    if hi >= len(ac):
        return None
    lag = lo + int(np.argmax(ac[lo:hi + 1]))
    bpm = 60 * fps / lag
    if bpm < 90 and 2 * bpm <= 180 and ac[lag // 2] > 0.8 * ac[lag]:
        lag = lag / 2
    elif bpm > 160 and ac[int(lag * 2)] > 0.8 * ac[lag] if int(lag * 2) < len(ac) else False:
        lag = lag * 2
    return float(lag)


def beat_times(env, period, fps=SR / HOP, tightness=100.0):
    """Beat times (s) by dynamic programming (Ellis 2007): each frame's best score is its onset
    strength plus the best earlier beat 0.5-2 periods back, penalised by how far that gap is from the
    period. A fixed grid drifted: an integer-frame period was 2% off at 120 BPM, a beat a minute."""
    if period is None or period < 2 or len(env) < 2 * period:
        return []
    e = env / (env.std() + 1e-9)
    n = len(e)
    offs = np.arange(max(1, int(round(period / 2))), int(round(2 * period)) + 1)
    penalty = -tightness * np.log(offs / period) ** 2
    score = e.astype(np.float64).copy()
    back = np.full(n, -1)
    for t in range(int(offs[0]), n):
        ok = offs <= t
        cand = score[t - offs[ok]] + penalty[ok]
        k = int(np.argmax(cand))
        if cand[k] > 0:
            score[t] = e[t] + cand[k]
            back[t] = t - offs[ok][k]
    tail = n - int(period)
    t = tail + int(np.argmax(score[tail:]))
    frames = []
    while t >= 0:
        frames.append(t)
        t = back[t]
    # A frame's window starts at t*HOP: an onset shows up when it enters the window's louder middle.
    return [float(f) / fps + N_FFT / (2.0 * SR) for f in reversed(frames)]


def track(path, start=0.0, seconds=60.0):
    """[beat time in seconds from ``start``] of the song stretch, or [] (off, or any failure)."""
    if not available():
        return []
    try:
        env = onset_envelope(_decode(path, start, seconds))
        return beat_times(env, tempo_period(env))
    except Exception:  # noqa: BLE001 — cuts on the beat are a bonus
        return []


def bpm(beats):
    if len(beats) < 3:
        return None
    return 60.0 / float(np.median(np.diff(beats)))
