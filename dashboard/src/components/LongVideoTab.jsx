import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, Film, Copy, Check, Download, ExternalLink, RefreshCw, Image } from 'lucide-react';
import { apiJson } from '../lib/api';
import { getApiUrl } from '../config';

// "Long video" (GET/POST /api/long-video, long_video.py): the week's best
// Shorts joined into one 16:9 YouTube video, counting down to #1, with a
// title, description and chapters written for it.

const mmss = (s) => `${Math.floor((s || 0) / 60)}:${String(Math.round((s || 0) % 60)).padStart(2, '0')}`;
const when = (ts) => new Date(ts * 1000).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

function Copier({ text, label }) {
    const [done, setDone] = useState(false);
    return (
        <button type="button" onClick={async () => {
            try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1400); } catch { /* ignore */ }
        }} className="btn-ghost px-2.5 py-1 text-[11px]">
            {done ? <Check size={12} className="text-ok" /> : <Copy size={12} />} {label}
        </button>
    );
}

function Thumbnails({ build }) {
    const [thumbs, setThumbs] = useState(build.thumbnails || []);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const make = async () => {
        setBusy(true);
        setError('');
        try {
            const d = await apiJson(`/api/long-video/${build.job_id}/thumbnail`, { method: 'POST' });
            setThumbs(d.thumbnails || []);
        } catch (e) {
            setError(e.detail || 'Could not make thumbnails.');
        } finally {
            setBusy(false);
        }
    };
    return (
        <div className="space-y-2">
            <button type="button" onClick={make} disabled={busy} className="btn-ghost px-3 py-1.5 text-[11px]">
                {busy ? <><Loader2 size={13} className="animate-spin" /> making 2 thumbnails, about a minute…</>
                    : <><Image size={13} /> {thumbs.length ? 'make 2 more thumbnails' : 'make thumbnails'}</>}
            </button>
            {error && <p className="text-[11px] text-danger">{error}</p>}
            {thumbs.length > 0 && (
                <div className="grid grid-cols-2 gap-2">
                    {thumbs.map((t) => (
                        <a key={t.url} href={getApiUrl(t.url)} download className="block" title={`download: ${t.text}`}>
                            <img src={getApiUrl(t.url)} alt={t.text} className="w-full aspect-video object-cover rounded-input border border-rule" />
                        </a>
                    ))}
                </div>
            )}
        </div>
    );
}

export default function LongVideoTab() {
    const [data, setData] = useState(null);
    const [picked, setPicked] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    const load = () => apiJson('/api/long-video').then((d) => {
        setData(d);
        setPicked((p) => p || d.candidates.slice(0, 10).map((c) => c.id));
    }).catch((e) => setError(e.detail || 'Could not load.'));
    useEffect(() => { load(); }, []);
    // Follow a build in progress.
    const building = (data?.builds || []).some((b) => b.status === 'building');
    useEffect(() => {
        if (!building) return undefined;
        const t = setInterval(load, 4000);
        return () => clearInterval(t);
    }, [building]);

    const chosen = useMemo(() => (data?.candidates || []).filter((c) => (picked || []).includes(c.id)), [data, picked]);
    // Clip + its spoken take (~7 s when it has one), plus the intro and outro cards.
    const total = chosen.reduce((s, c) => s + (c.seconds || 0) + (c.take ? 7 : 0), 0) + (chosen.length ? 9.5 : 0);

    const toggle = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

    const build = async () => {
        setBusy(true);
        setError('');
        try {
            // Keep the list order (best first); the server plays the best last, as #1.
            const ids = (data.candidates || []).map((c) => c.id).filter((id) => picked.includes(id));
            await apiJson('/api/long-video', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) });
            await load();
        } catch (e) {
            setError(e.detail || 'Could not start.');
        } finally {
            setBusy(false);
        }
    };

    const min = data?.min || 3, max = data?.max || 15;
    return (
        <div className="h-full overflow-y-auto p-4 sm:p-8 animate-fade">
            <div className="max-w-4xl mx-auto space-y-5">
                <div>
                    <p className="eyebrow mb-1.5">LONG VIDEO</p>
                    <h1 className="font-display lowercase text-2xl text-ink">your week in one video</h1>
                    <p className="text-xs text-muted mt-1 max-w-2xl leading-relaxed">
                        Joins this week&apos;s best Shorts into one wide YouTube video that counts down to #1, with the title,
                        description and chapters written for you. Long videos earn from their own ads, so the same clips earn twice.
                        Autopilot can build it every week by itself.
                    </p>
                </div>
                {error && <p className="text-sm text-danger" role="alert">{error}</p>}
                {!data && !error && <div className="flex items-center gap-2 text-sm text-muted"><Loader2 size={16} className="animate-spin" /> loading…</div>}

                {data && (
                    <div className="card p-5 space-y-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm text-ink">Shorts from the last 7 days <span className="text-muted">(best first)</span></p>
                            <p className="readout">{chosen.length} picked · about {mmss(total)}</p>
                        </div>
                        {data.candidates.length === 0 && <p className="text-xs text-muted">No comedy Shorts from the last 7 days yet.</p>}
                        <div className="space-y-1 max-h-80 overflow-y-auto custom-scrollbar pr-1">
                            {data.candidates.map((c) => (
                                <label key={c.id} className="flex items-center gap-3 text-xs py-1 cursor-pointer">
                                    <input type="checkbox" checked={(picked || []).includes(c.id)} onChange={() => toggle(c.id)} />
                                    <span className="readout w-16 text-right shrink-0">{c.views != null ? `${c.views} views` : c.status}</span>
                                    <span className="text-ink2 truncate min-w-0 flex-1">{c.title}</span>
                                    <span className="text-muted shrink-0">{Math.round(c.seconds)}s</span>
                                </label>
                            ))}
                        </div>
                        <button onClick={build} disabled={busy || building || chosen.length < min || chosen.length > max}
                            className="btn-primary px-4 py-2 text-sm">
                            {busy ? <Loader2 size={15} className="animate-spin" /> : <Film size={15} />} build the long video
                        </button>
                        {(chosen.length < min || chosen.length > max) && (
                            <p className="text-[11px] text-warn">Pick {min} to {max} Shorts.</p>
                        )}
                    </div>
                )}

                {(data?.builds || []).map((b) => (
                    <div key={b.job_id} className="card p-5 space-y-3">
                        {b.status === 'building' && (
                            <p className="text-sm text-ink2 flex items-center gap-2"><Loader2 size={15} className="animate-spin" /> Building: {b.step}… (about 20 seconds per Short)</p>
                        )}
                        {b.status === 'failed' && <p className="text-sm text-danger">Build failed: {b.error}</p>}
                        {b.status === 'done' && (
                            <div className="flex flex-col md:flex-row gap-4">
                                <video src={getApiUrl(b.video_url)} controls preload="metadata" className="w-full md:w-80 aspect-video rounded-input bg-black shrink-0" />
                                <div className="min-w-0 flex-1 space-y-2">
                                    <p className="readout">{when(b.created)} · {mmss(b.seconds)}</p>
                                    <p className="text-sm text-ink break-words">{b.title}</p>
                                    <div className="flex flex-wrap gap-1.5">
                                        <Copier text={b.title || ''} label="title" />
                                        <Copier text={b.description || ''} label="description + chapters" />
                                        <Copier text={(b.tags || []).join(', ')} label="tags" />
                                    </div>
                                    <p className="text-xs text-muted whitespace-pre-wrap break-words max-h-40 overflow-y-auto custom-scrollbar bg-paper rounded-input border border-rule p-2.5">{b.description}</p>
                                    <div className="flex flex-wrap gap-2">
                                        <a href={getApiUrl(b.video_url)} download className="btn-primary px-3 py-1.5 text-[11px]"><Download size={13} /> download</a>
                                        <a href="https://studio.youtube.com" target="_blank" rel="noreferrer" className="btn-ghost px-3 py-1.5 text-[11px]"><ExternalLink size={13} /> youtube studio</a>
                                    </div>
                                    <Thumbnails build={b} />
                                    <p className="text-[11px] text-muted">Click a thumbnail to download it. The video is kept on this computer for 7 days.</p>
                                </div>
                            </div>
                        )}
                    </div>
                ))}
                {data && <button onClick={load} className="btn-ghost px-3 py-1.5 text-xs"><RefreshCw size={13} /> refresh</button>}
            </div>
        </div>
    );
}
