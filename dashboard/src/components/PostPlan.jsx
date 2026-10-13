import React, { useEffect, useState } from 'react';
import { Loader2, Copy, Check, Download, ExternalLink, CheckCircle2, SkipForward, MessageCircle, RefreshCw, Repeat, Undo2, Youtube, Sparkles, Smartphone } from 'lucide-react';
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

function ReadyCard({ item, onStatus, ytConnected, phone }) {
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

    const [sent, setSent] = useState(!!item.telegram_sent);
    const toPhone = async () => {
        setBusy('phone');
        setError('');
        try {
            await apiJson('/api/phone/send', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: item.id }) });
            setSent(true);
        } catch (e) {
            setError(e.detail || 'Could not send it.');
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
        <div id={`plan-${item.id}`} className="card p-3 sm:p-4 flex gap-3 sm:gap-4">
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
                    {phone && (
                        <button type="button" onClick={toPhone} disabled={busy === 'phone'} className="btn-ghost px-3 py-1.5 text-[11px]">
                            {busy === 'phone' ? <Loader2 size={13} className="animate-spin" /> : <Smartphone size={13} />} {sent ? 'sent, send again' : 'send to phone'}
                        </button>
                    )}
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

function NewTitles({ item }) {
    const [titles, setTitles] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const ask = async () => {
        setBusy(true);
        setError('');
        try {
            const d = await apiJson(`/api/queue/${encodeURIComponent(item.id)}/retitle`, { method: 'POST' });
            setTitles(d.titles);
        } catch (e) {
            setError(e.detail || 'Could not write titles.');
        } finally {
            setBusy(false);
        }
    };
    return (
        <div className="w-full">
            {!titles && (
                <button onClick={ask} disabled={busy} className="btn-ghost px-2.5 py-1 text-[11px]" title="A better title can revive a Short; change it in YouTube Studio">
                    {busy ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} new title
                </button>
            )}
            {error && <p className="text-[11px] text-danger">{error}</p>}
            {titles && (
                <div className="mt-2 space-y-1.5 rounded-input border border-rule p-2.5">
                    <p className="text-[11px] text-muted">Pick one and paste it in YouTube Studio, Details, Title. Keep it the same here so views still match.</p>
                    {titles.map((t) => (
                        <div key={t.title} className="flex flex-wrap items-center gap-2">
                            <span className="text-xs text-ink flex-1 min-w-0 break-words">{t.title}<span className="block text-[11px] text-muted">{t.why}</span></span>
                            <CopyButton text={t.title} label="copy" />
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

// The next 7 days of posting times, each with the Short planned there or an
// open slot, so a gap in the week shows before it happens.
function WeekView({ ready, postTimes, onOpen, onFill }) {
    const now = new Date();
    const days = Array.from({ length: 7 }, (_, d) => {
        const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() + d);
        const slots = (postTimes || []).map((t) => {
            const [h, m] = t.split(':').map(Number);
            const at = new Date(day.getFullYear(), day.getMonth(), day.getDate(), h, m);
            const item = ready.find((x) => x.slot && Math.abs(new Date(x.slot) - at) < 60000);
            return { t, at, item };
        }).filter((s) => s.at > now);
        return { day, slots };
    });
    const empty = days.reduce((n, d) => n + d.slots.filter((s) => !s.item).length, 0);
    return (
        <div className="space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
                {days.map(({ day, slots }) => (
                    <div key={day.toDateString()} className="card p-2.5 space-y-1.5 min-w-0">
                        <p className="eyebrow">{day.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' })}</p>
                        {slots.length === 0 && <p className="text-[11px] text-muted">no more times today</p>}
                        {slots.map((s) => (s.item ? (
                            <button key={s.t} type="button" onClick={() => onOpen(s.item)} title={s.item.title}
                                className="w-full text-left rounded-input border border-rule p-1.5 hover:border-[color:var(--color-accent)]">
                                <span className="readout block">{s.t} · {s.item.genre}</span>
                                <span className="text-[11px] text-ink2 line-clamp-2 break-words">{s.item.title}</span>
                            </button>
                        ) : (
                            <div key={s.t} className="rounded-input border border-dashed border-rule2 p-1.5">
                                <span className="readout block">{s.t}</span>
                                <span className="text-[11px] text-muted">open</span>
                            </div>
                        )))}
                    </div>
                ))}
            </div>
            {empty > 0 && (
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                    {empty} open {empty === 1 ? 'slot' : 'slots'} this week.
                    <button type="button" onClick={onFill} className="btn-ghost px-2.5 py-1 text-[11px]">make more shorts</button>
                </div>
            )}
        </div>
    );
}

// One button for the whole plan (POST /api/youtube/post-all): every waiting
// Short is uploaded with its title, description and tags, each scheduled into
// its posting time. Followed on GET until the run is over.
function PostAll({ ready, yt, onDone, onOpenChannel }) {
    const [run, setRun] = useState(null);
    const [error, setError] = useState('');

    useEffect(() => {
        apiJson('/api/youtube/post-all').then((r) => { if (r.running || r.finished) setRun(r); }).catch(() => {});
    }, []);
    useEffect(() => {
        if (!run?.running) return undefined;
        const t = setInterval(() => {
            apiJson('/api/youtube/post-all').then((r) => {
                setRun(r);
                if (!r.running) onDone();
            }).catch(() => {});
        }, 3000);
        return () => clearInterval(t);
    }, [run?.running]); // eslint-disable-line react-hooks/exhaustive-deps

    const start = async () => {
        setError('');
        try {
            const d = await apiJson('/api/youtube/post-all', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
            setRun({ running: true, total: d.total, done: 0, failed: 0, errors: [] });
        } catch (e) {
            setError(e.detail || 'Could not start posting.');
        }
    };

    if (!yt?.connected) {
        return (
            <div className="card p-4 flex flex-wrap items-center gap-3">
                <Youtube size={18} className="text-muted shrink-0" />
                <p className="text-xs text-muted flex-1 min-w-[14rem]">Connect your YouTube channel once, then every Short here goes up with one click, each at its posting time.</p>
                <button onClick={onOpenChannel} className="btn-ghost px-3 py-1.5 text-xs">connect YouTube</button>
            </div>
        );
    }
    const busy = !!run?.running;
    return (
        <div className="card p-4 space-y-2">
            <div className="flex flex-wrap items-center gap-3">
                <Youtube size={18} className="text-brass shrink-0" />
                <p className="text-xs text-muted flex-1 min-w-[14rem]">
                    Uploads every waiting Short to {yt.channel?.title || 'your channel'} with its title, description and tags, each scheduled at its posting time.
                </p>
                <button onClick={start} disabled={busy || ready.length === 0} className="btn-primary px-4 py-2 text-sm">
                    {busy ? <Loader2 size={15} className="animate-spin" /> : <Youtube size={15} />}
                    {busy ? ` posting ${run.done + run.failed + 1} of ${run.total}` : ` post all ${ready.length} to YouTube`}
                </button>
            </div>
            {busy && run.current && <p className="text-[11px] text-muted truncate">now: {run.current}</p>}
            {run && !busy && run.total > 0 && (
                <p className={`text-xs ${run.failed ? 'text-warn' : 'text-ok'}`}>
                    {run.done} of {run.total} uploaded and scheduled{run.failed ? `, ${run.failed} failed` : ''}. Check them in YouTube Studio under Content.
                </p>
            )}
            {(run?.errors || []).slice(0, 4).map((e) => <p key={e} className="text-[11px] text-danger break-words">{e}</p>)}
            {!busy && (run?.uploaded || []).length > 0 && (
                <div className="rounded-input border border-rule p-2.5 space-y-1.5">
                    <p className="text-[11px] text-muted leading-relaxed">
                        Until your Google project passes the YouTube audit, YouTube keeps these private. In Studio, set each one to Schedule at its time (or Public when the time comes).
                    </p>
                    {run.uploaded.map((u) => (
                        <div key={u.video_id || u.slot} className="flex flex-wrap items-center gap-2 text-xs">
                            <span className="readout shrink-0">{slotText(u.slot)}</span>
                            <span className="text-ink2 flex-1 min-w-0 truncate">{u.title}</span>
                            {u.video_id && (
                                <a href={`https://studio.youtube.com/video/${u.video_id}/edit`} target="_blank" rel="noreferrer"
                                    className="btn-ghost px-2 py-1 text-[11px]"><ExternalLink size={12} /> open in Studio</a>
                            )}
                        </div>
                    ))}
                </div>
            )}
            {error && <p className="text-xs text-danger" role="alert">{error}</p>}
        </div>
    );
}

export default function PostPlan({ onMakeShorts, onOpenAutopilot, onNewShorts, onOpenChannel }) {
    const [data, setData] = useState(null);
    const [error, setError] = useState('');
    const [view, setView] = useState('ready');
    const [busy, setBusy] = useState('');
    const [yt, setYt] = useState(null);
    const [phone, setPhone] = useState(false);
    const [phoneMsg, setPhoneMsg] = useState('');

    const load = () => {
        apiJson('/api/queue').then(setData).catch((e) => setError(e.detail || 'Could not load the plan.'));
    };
    useEffect(() => {
        load();
        apiJson('/api/youtube/status').then(setYt).catch(() => setYt(null));
        apiJson('/api/telegram/status').then((s) => setPhone(!!s.connected)).catch(() => setPhone(false));
    }, []);

    const allToPhone = async () => {
        setPhoneMsg('');
        try {
            const d = await apiJson('/api/phone/send', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
            setPhoneMsg(`Sending ${d.sending} ${d.sending === 1 ? 'Short' : 'Shorts'} to your phone.`);
        } catch (e) {
            setPhoneMsg(e.detail || 'Could not send.');
        }
    };

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
    // "Needs a new title": out for 2+ days and well under the channel's usual
    // views, while a title change can still give it a second push.
    const seen = posted.filter((p) => p.views != null).map((p) => p.views).sort((a, b) => a - b);
    const median = seen.length ? seen[Math.floor(seen.length / 2)] : 0;
    const weak = (p) => p.views != null && p.posted_at && Date.now() / 1000 - p.posted_at > 2 * 86400
        && seen.length >= 3 && p.views < 0.6 * median;

    return (
        <div className="h-full overflow-y-auto p-4 sm:p-8 animate-fade">
            <div className="max-w-4xl mx-auto space-y-5">
                <div>
                    <p className="eyebrow mb-1.5">READY TO POST</p>
                    <h1 className="font-display lowercase text-2xl text-ink">your posting plan</h1>
                    <p className="text-xs text-muted mt-1 max-w-2xl leading-relaxed">
                        Post all of them to YouTube with one click, or each one by hand from the YouTube app (paste the copy, then press posted). Pin the comment after it goes live.
                        Shorts waiting here are kept for {data?.keep_days || 7} days.
                        Posting times: {(data?.post_times || []).join(', ')} (<button onClick={onOpenAutopilot} className="underline hover:text-brass">change</button>).
                    </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    {[['ready', `to post (${ready.length})`], ['week', 'week'], ['posted', `posted (${posted.length})`], ['skipped', `skipped (${skipped.length})`]].map(([v, l]) => (
                        <button key={v} onClick={() => setView(v)} aria-pressed={view === v}
                            className={`px-3 py-1.5 rounded-input border text-xs ${view === v ? 'border-[color:var(--color-accent)] text-ink' : 'border-rule2 text-muted'}`}>{l}</button>
                    ))}
                    {ready.length > 0 && phone && (
                        <button onClick={allToPhone} className="btn-ghost px-2.5 py-1.5 text-xs ml-auto" title="Every waiting Short not sent yet, to your Telegram">
                            <Smartphone size={13} /> send all to phone
                        </button>
                    )}
                    {ready.length > 0 && (
                        <a href={getApiUrl('/api/queue/pack')} download className="btn-ghost px-2.5 py-1.5 text-xs ml-auto"
                            title="Every waiting Short with a text file of its copy, in posting order">
                            <Download size={13} /> download posting pack
                        </a>
                    )}
                    <button onClick={load} className={`btn-ghost px-2.5 py-1.5 text-xs ${ready.length ? '' : 'ml-auto'}`}><RefreshCw size={13} /> refresh</button>
                </div>
                {data && <PostAll ready={ready} yt={yt} onDone={load} onOpenChannel={onOpenChannel || onOpenAutopilot} />}
                {error && <p className="text-sm text-danger" role="alert">{error}</p>}
                {phoneMsg && <p className="text-sm text-ink2">{phoneMsg}</p>}
                {!data && !error && <div className="flex items-center gap-2 text-sm text-muted"><Loader2 size={16} className="animate-spin" /> loading…</div>}

                {view === 'week' && data && (
                    <WeekView ready={ready} postTimes={data.post_times}
                        onOpen={(item) => {
                            setView('ready');
                            setTimeout(() => document.getElementById(`plan-${item.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 80);
                        }}
                        onFill={onNewShorts || onOpenAutopilot} />
                )}

                {view === 'ready' && data && (
                    ready.length === 0
                        ? <div className="card p-6 text-sm text-muted text-center">Nothing waiting. Make Shorts, or switch on Autopilot, and they will line up here.</div>
                        : <div className="space-y-3">{ready.map((x) => <ReadyCard key={x.id} item={x} onStatus={setStatus} ytConnected={!!yt?.connected} phone={phone} />)}</div>
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
                                <span className="text-sm text-ink2 flex-1 min-w-[50%] break-words">{p.title}
                                    {p.blocked && <span className="badge-warn ml-2 align-middle">blocked by a copyright claim</span>}
                                    {weak(p) && !p.blocked && <span className="badge-warn ml-2 align-middle">needs a new title</span>}</span>
                                {p.youtube_id && <a href={`https://youtube.com/shorts/${p.youtube_id}`} target="_blank" rel="noreferrer" className="text-muted hover:text-brass" aria-label="open on YouTube"><ExternalLink size={13} /></a>}
                                {p.source_url && p.genre !== 'cricket' && (
                                    <button onClick={() => onMakeShorts(p.source_url)} className="btn-ghost px-2.5 py-1 text-[11px]" title="New Shorts from the same video, never the same moment">
                                        <Repeat size={12} /> make part 2
                                    </button>
                                )}
                                <button onClick={() => setStatus(p, 'ready')} className="btn-ghost px-2 py-1 text-[11px]" aria-label="back to ready"><Undo2 size={12} /></button>
                                <NewTitles item={p} />
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
