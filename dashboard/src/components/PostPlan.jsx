import React, { useEffect, useState } from 'react';
import { Loader2, Copy, Check, Download, ExternalLink, CheckCircle2, SkipForward, MessageCircle, RefreshCw, Repeat, Undo2, Youtube } from 'lucide-react';
import { apiJson } from '../lib/api';
import { getApiUrl } from '../config';

// "Ready to post" (GET /api/queue, post_queue.py): every finished Short with
// a posting time, its copy and a pinned comment, until it is marked posted.
// Posted ones show their views and offer a part 2 from the same video.

const slotText = (iso) => {
    const d = new Date(iso);
    const today = new Date();
    const tomorrow = new Date(); tomorrow.setDate(today.getDate() + 1);
    const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    if (d.toDateString() === today.toDateString()) return `today ${time}`;
    if (d.toDateString() === tomorrow.toDateString()) return `tomorrow ${time}`;
    return d.toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
};

function CopyButton({ text, label }) {
    const [done, setDone] = useState(false);
    return (
        <button type="button" onClick={async () => {
            try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1400); } catch { /* ignore */ }
        }} className="btn-ghost px-2.5 py-1 text-[11px]" aria-label={`copy ${label}`}>
            {done ? <Check size={12} className="text-ok" /> : <Copy size={12} />} {label}
        </button>
    );
}

function ReadyCard({ item, onStatus, ytConnected }) {
    const [pinned, setPinned] = useState(item.pinned_comment || '');
    const [busy, setBusy] = useState('');
    const [error, setError] = useState('');
    const [open, setOpen] = useState(false);

    const writePinned = async () => {
        setBusy('pinned');
        setError('');
        try {
            const d = await apiJson(`/api/queue/${encodeURIComponent(item.id)}/pinned`, { method: 'POST' });
            setPinned(d.pinned_comment);
        } catch (e) {
            setError(e.detail || 'Could not write a comment.');
        } finally {
            setBusy('');
        }
    };

    const schedule = async () => {
        setBusy('upload');
        setError('');
        try {
            await apiJson('/api/youtube/upload', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_id: item.job_id, clip_index: item.index, when: item.slot || 'slot' }),
            });
            await onStatus(item, 'posted');
        } catch (e) {
            setError(e.detail || 'Upload failed.');
        } finally {
            setBusy('');
        }
    };

    const tagLine = (item.tags || []).join(', ');
    return (
        <div className="card p-3 sm:p-4 flex gap-3 sm:gap-4">
            <video src={getApiUrl(item.video_url)} controls preload="metadata"
                className="w-24 sm:w-36 aspect-[9/16] rounded-input bg-black object-contain shrink-0 border border-rule self-start" />
            <div className="min-w-0 flex-1 space-y-2">
                <div className="flex flex-wrap items-center gap-1.5">
                    {item.slot && <span className="badge-brass">post {slotText(item.slot)}</span>}
                    <span className="readout">{item.genre}</span>
                    {item.autopilot && <span className="readout">autopilot</span>}
                    <span className="readout">{Math.round(item.seconds)}s</span>
                </div>
                <p className="text-sm text-ink break-words">{item.title}</p>
                <div className="flex flex-wrap gap-1.5">
                    <CopyButton text={item.title} label="title" />
                    <CopyButton text={item.description} label="description" />
                    {tagLine && <CopyButton text={tagLine} label="tags" />}
                    {item.tiktok && <CopyButton text={item.tiktok} label="tiktok caption" />}
                    {item.instagram && <CopyButton text={item.instagram} label="instagram / facebook caption" />}
                    <button type="button" onClick={() => setOpen((v) => !v)} className="btn-ghost px-2.5 py-1 text-[11px]">
                        {open ? 'hide description' : 'show description'}
                    </button>
                </div>
                {open && <p className="text-xs text-ink2 whitespace-pre-wrap break-words bg-paper rounded-input border border-rule p-2.5">{item.description}</p>}
                <div className="rounded-input border border-rule p-2.5 space-y-1.5">
                    <p className="eyebrow flex items-center gap-1"><MessageCircle size={11} /> pinned comment</p>
                    {pinned ? (
                        <div className="flex flex-wrap items-center gap-2">
                            <p className="text-xs text-ink2 flex-1 min-w-0 break-words">{pinned}</p>
                            <CopyButton text={pinned} label="copy" />
                            <button type="button" onClick={writePinned} disabled={busy === 'pinned'} className="btn-ghost px-2 py-1 text-[11px]" aria-label="write another">
                                {busy === 'pinned' ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                            </button>
                        </div>
                    ) : (
                        <button type="button" onClick={writePinned} disabled={busy === 'pinned'} className="btn-ghost px-2.5 py-1 text-[11px]">
                            {busy === 'pinned' ? <Loader2 size={12} className="animate-spin" /> : <MessageCircle size={12} />} write one that gets replies
                        </button>
                    )}
                </div>
                {error && <p className="text-[11px] text-danger">{error}</p>}
                <div className="flex flex-wrap gap-2 pt-1">
                    <a href={getApiUrl(item.video_url)} download className="btn-primary px-3 py-1.5 text-[11px]"><Download size={13} /> download</a>
                    <a href="https://studio.youtube.com" target="_blank" rel="noreferrer" className="btn-ghost px-3 py-1.5 text-[11px]"><ExternalLink size={13} /> youtube studio</a>
                    {ytConnected && (
                        <button type="button" onClick={schedule} disabled={busy === 'upload'} className="btn-ghost px-3 py-1.5 text-[11px]">
                            {busy === 'upload' ? <Loader2 size={13} className="animate-spin" /> : <Youtube size={13} />} schedule on youtube
                        </button>
                    )}
                    <button type="button" onClick={() => onStatus(item, 'posted')} className="btn-ghost px-3 py-1.5 text-[11px] text-ok"><CheckCircle2 size={13} /> posted</button>
                    <button type="button" onClick={() => onStatus(item, 'skipped')} className="btn-ghost px-3 py-1.5 text-[11px]"><SkipForward size={13} /> skip</button>
                </div>
            </div>
        </div>
    );
}

export default function PostPlan({ onMakeShorts, onOpenAutopilot }) {
    const [data, setData] = useState(null);
    const [error, setError] = useState('');
    const [view, setView] = useState('ready');
    const [busy, setBusy] = useState('');
    const [yt, setYt] = useState(null);

    const load = () => {
        apiJson('/api/queue').then(setData).catch((e) => setError(e.detail || 'Could not load the plan.'));
    };
    useEffect(() => {
        load();
        apiJson('/api/youtube/status').then(setYt).catch(() => setYt(null));
    }, []);

    const setStatus = async (item, status) => {
        await apiJson(`/api/queue/${encodeURIComponent(item.id)}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
        }).catch((e) => setError(e.detail || 'Could not save.'));
        load();
    };

    const refreshViews = async () => {
        setBusy('views');
        setError('');
        try {
            const d = await apiJson('/api/queue/views', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
            if (d.posted && !d.matched) setError('None of your posted Shorts were found on the channel by title yet. Keep the title exactly as copied from here.');
            load();
        } catch (e) {
            setError(e.detail || 'Could not read the views.');
        } finally {
            setBusy('');
        }
    };

    const items = data?.items || [];
    const ready = items.filter((x) => x.status === 'ready').sort((a, b) => (a.slot || '').localeCompare(b.slot || ''));
    const posted = items.filter((x) => x.status === 'posted').sort((a, b) => (b.views ?? -1) - (a.views ?? -1) || (b.posted_at || 0) - (a.posted_at || 0));
    const skipped = items.filter((x) => x.status === 'skipped');
    const best = Math.max(0, ...posted.map((p) => p.views || 0));

    return (
        <div className="h-full overflow-y-auto p-4 sm:p-8 animate-fade">
            <div className="max-w-4xl mx-auto space-y-5">
                <div>
                    <p className="eyebrow mb-1.5">READY TO POST</p>
                    <h1 className="font-display lowercase text-2xl text-ink">your posting plan</h1>
                    <p className="text-xs text-muted mt-1 max-w-2xl leading-relaxed">
                        Post each Short at its time from the YouTube app or Studio, paste the copy, pin the comment, then press posted.
                        Shorts waiting here are kept for {data?.keep_days || 7} days.
                        Posting times: {(data?.post_times || []).join(', ')} (<button onClick={onOpenAutopilot} className="underline hover:text-brass">change</button>).
                    </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    {[['ready', `to post (${ready.length})`], ['posted', `posted (${posted.length})`], ['skipped', `skipped (${skipped.length})`]].map(([v, l]) => (
                        <button key={v} onClick={() => setView(v)} aria-pressed={view === v}
                            className={`px-3 py-1.5 rounded-input border text-xs ${view === v ? 'border-[color:var(--color-accent)] text-ink' : 'border-rule2 text-muted'}`}>{l}</button>
                    ))}
                    <button onClick={load} className="btn-ghost px-2.5 py-1.5 text-xs ml-auto"><RefreshCw size={13} /> refresh</button>
                </div>
                {error && <p className="text-sm text-danger" role="alert">{error}</p>}
                {!data && !error && <div className="flex items-center gap-2 text-sm text-muted"><Loader2 size={16} className="animate-spin" /> loading…</div>}

                {view === 'ready' && data && (
                    ready.length === 0
                        ? <div className="card p-6 text-sm text-muted text-center">Nothing waiting. Make Shorts, or switch on Autopilot, and they will line up here.</div>
                        : <div className="space-y-3">{ready.map((x) => <ReadyCard key={x.id} item={x} onStatus={setStatus} ytConnected={!!yt?.connected} />)}</div>
                )}

                {view === 'posted' && data && (
                    <div className="space-y-3">
                        <div className="flex flex-wrap items-center gap-2">
                            <p className="text-xs text-muted flex-1 min-w-0">Views come from your channel&apos;s public Shorts, matched by title. A part 2 takes new moments from the same video.</p>
                            <button onClick={refreshViews} disabled={busy === 'views'} className="btn-primary px-3 py-1.5 text-xs">
                                {busy === 'views' ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} update views
                            </button>
                        </div>
                        {posted.length === 0 && <div className="card p-6 text-sm text-muted text-center">Nothing marked posted yet.</div>}
                        {posted.map((p) => (
                            <div key={p.id} className="card p-3 flex flex-wrap items-center gap-3">
                                <span className={`readout w-20 text-right shrink-0 ${p.views && p.views === best ? 'text-brass' : ''}`}>{p.views == null ? '?' : `${p.views} views`}</span>
                                <span className="text-sm text-ink2 flex-1 min-w-[50%] break-words">{p.title}</span>
                                {p.youtube_id && <a href={`https://youtube.com/shorts/${p.youtube_id}`} target="_blank" rel="noreferrer" className="text-muted hover:text-brass" aria-label="open on YouTube"><ExternalLink size={13} /></a>}
                                {p.source_url && p.genre !== 'cricket' && (
                                    <button onClick={() => onMakeShorts(p.source_url)} className="btn-ghost px-2.5 py-1 text-[11px]" title="New Shorts from the same video, never the same moment">
                                        <Repeat size={12} /> make part 2
                                    </button>
                                )}
                                <button onClick={() => setStatus(p, 'ready')} className="btn-ghost px-2 py-1 text-[11px]" aria-label="back to ready"><Undo2 size={12} /></button>
                            </div>
                        ))}
                    </div>
                )}

                {view === 'skipped' && data && (
                    <div className="space-y-2">
                        {skipped.length === 0 && <div className="card p-6 text-sm text-muted text-center">Nothing skipped.</div>}
                        {skipped.map((p) => (
                            <div key={p.id} className="card p-3 flex items-center gap-3">
                                <span className="text-sm text-ink2 flex-1 min-w-0 truncate">{p.title}</span>
                                <button onClick={() => setStatus(p, 'ready')} className="btn-ghost px-2.5 py-1 text-[11px]"><Undo2 size={12} /> back to plan</button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
