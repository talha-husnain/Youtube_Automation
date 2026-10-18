import React, { useCallback, useEffect, useState } from 'react';
import {
    Loader2, CheckCircle2, Circle, Copy, Check, AlertTriangle, Rocket, Trophy, HelpCircle, Music, Layers,
    Bell, CalendarClock, Clock, Eye, Users, Upload, Clapperboard, ExternalLink, Flame, Landmark, Youtube,
} from 'lucide-react';
import { apiJson } from '../lib/api';
import { getApiUrl } from '../config';

// The home page for self-host (GET /api/today, app._today): every channel at a
// glance, what the owner still has to do, the next posts, and the switches
// for the Windows reminders and the evening summary (reminders.py).

const KIND_ICON = { comedy: Rocket, cricket: Trophy, quiz: HelpCircle, music: Music, controversy: Flame, history: Landmark };
const at = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : '');
const day = (ts) => new Date(ts * 1000).toLocaleString(undefined, { weekday: 'long', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

function Stat({ icon, label, value }) {
    const Icon = icon;
    return (
        <div className="rounded-input border border-rule p-3 min-w-0">
            <p className="text-[11px] text-muted flex items-center gap-1"><Icon size={12} /> {label}</p>
            <p className="text-lg text-ink readout">{value ?? '–'}</p>
        </div>
    );
}

function Steps({ text }) {
    const [copied, setCopied] = useState(false);
    return (
        <div className="relative">
            <pre className="text-[11px] leading-relaxed text-ink2 bg-paper rounded-input border border-rule p-3 pr-10 whitespace-pre-wrap break-words">{text}</pre>
            <button onClick={async () => {
                try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1400); } catch { /* ignore */ }
            }} aria-label="copy steps" className="absolute top-2 right-2 p-1.5 text-muted hover:text-brass">
                {copied ? <Check size={14} className="text-ok" /> : <Copy size={14} />}
            </button>
        </div>
    );
}

export default function TodayTab({ onOpenTab }) {
    const [data, setData] = useState(null);
    const [error, setError] = useState('');
    const [sampleNote, setSampleNote] = useState('');

    const load = useCallback(() => apiJson('/api/today').then((d) => { setData(d); setError(''); })
        .catch((e) => setError(e.detail || 'Could not load today.')), []);
    useEffect(() => {
        load();
        const t = setInterval(load, 60000);
        return () => clearInterval(t);
    }, [load]);

    const setNotify = async (patch) => {
        try {
            setData(await apiJson('/api/today/settings', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
            }));
        } catch (e) {
            setError(e.detail || 'Could not save.');
        }
    };

    // The posting-time and length tips (my_channels.time_tip, length_tip):
    // one click saves the suggested setting.
    const applyTip = async (cid, patch) => {
        try {
            await apiJson(`/api/my-channels/${cid}`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
            });
            load();
        } catch (e) {
            setError(e.detail || 'Could not change that setting.');
        }
    };

    if (!data) {
        return <div className="card p-5 text-sm text-muted">{error || <><Loader2 size={14} className="animate-spin inline" /> loading…</>}</div>;
    }
    const t = data.totals;
    const open = data.setup.filter((s) => !s.done);
    const publish = data.setup.find((s) => s.key === 'publish');
    const held = data.notify.snooze_until * 1000 > Date.now();
    return (
        <div className="space-y-4 max-w-4xl">
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                <Stat icon={Clapperboard} label="made today" value={t.made_today} />
                <Stat icon={Upload} label="uploaded today" value={t.uploaded_today} />
                <Stat icon={CalendarClock} label="scheduled" value={t.scheduled} />
                <Stat icon={Eye} label="views" value={t.views == null ? null : `${t.views.toLocaleString()}${t.views_gain ? ` (+${t.views_gain})` : ''}`} />
                <Stat icon={Users} label="subscribers" value={t.subscribers} />
            </div>
            {error && <p className="text-xs text-danger" role="alert">{error}</p>}

            {open.length > 0 && (
                <div className={`card p-5 space-y-3 ${publish && !publish.done && publish.deadline ? 'border-warn' : ''}`}>
                    <p className="text-sm text-ink flex items-center gap-1.5">
                        <AlertTriangle size={15} className="text-warn" /> To do once ({open.length} left, about 15 minutes)
                    </p>
                    {publish && !publish.done && publish.deadline && (
                        <p className="text-xs text-warn">Before {day(publish.deadline)}: that is when your YouTube connection stops.</p>
                    )}
                    <div className="space-y-1.5">
                        {data.setup.map((s) => (
                            <div key={s.key} className="flex items-center gap-2 text-xs">
                                {s.done ? <CheckCircle2 size={14} className="text-ok shrink-0" /> : <Circle size={14} className="text-muted shrink-0" />}
                                <span className={s.done ? 'text-muted line-through' : 'text-ink2'}>{s.title}</span>
                                {!s.done && s.tab && (
                                    <button onClick={() => onOpenTab(s.tab)} className="text-brass hover:underline">open</button>
                                )}
                            </div>
                        ))}
                    </div>
                    {publish && !publish.done && <Steps text={publish.steps} />}
                    {data.setup.filter((s) => s.key !== 'publish' && !s.done && s.steps).map((s) => (
                        <div key={s.key} className="space-y-1">
                            <p className="text-xs text-ink2">{s.title}:</p>
                            <Steps text={s.steps} />
                        </div>
                    ))}
                    {held && <p className="text-[11px] text-muted">Reminders start {day(data.notify.snooze_until)}, as you asked.</p>}
                </div>
            )}

            <div className="card p-5 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm text-ink flex items-center gap-1.5"><Layers size={15} /> Your channels</p>
                    <div className="flex flex-wrap gap-2">
                    {data.channels.some((c) => c.id !== 'main' && !c.connected) && (
                        <a href={getApiUrl(`/api/youtube/connect-all?back=${encodeURIComponent(window.location.origin)}`)} className="btn-primary px-3 py-1.5 text-xs inline-flex items-center gap-1.5">
                            <Youtube size={13} /> connect all channels
                        </a>
                    )}
                    <button onClick={async () => {
                        try {
                            const d = await apiJson('/api/my-channels/samples', { method: 'POST' });
                            setSampleNote(`${d.queued.length} sample videos queued: they are made one after another (a few minutes each). Watch them on the Channels page.`);
                        } catch (e) {
                            setSampleNote(e.detail || 'Could not queue the samples.');
                        }
                    }} className="btn-ghost px-3 py-1.5 text-xs"><Clapperboard size={13} /> make a sample for every channel</button>
                    </div>
                </div>
                {sampleNote && <p className="text-xs text-ok">{sampleNote}</p>}
                {data.channels.map((c) => {
                    const Icon = KIND_ICON[c.kind] || Layers;
                    const ok = c.problems.length === 0;
                    return (
                        <div key={c.id} className="space-y-1">
                        <button onClick={() => onOpenTab('channels')}
                            className="w-full text-left flex flex-wrap items-center gap-x-3 gap-y-1 rounded-input border border-rule hover:border-rule2 p-3">
                            {c.thumbnail ? <img src={c.thumbnail} alt="" className="h-8 w-8 rounded-full shrink-0" />
                                : <span className="h-8 w-8 rounded-full bg-paper flex items-center justify-center shrink-0"><Icon size={15} /></span>}
                            <span className="min-w-0 flex-1">
                                <span className="block text-sm text-ink truncate">{c.name}</span>
                                <span className={`block text-[11px] ${ok ? 'text-ok' : 'text-warn'}`}>{ok ? 'running' : c.problems.join(' · ')}</span>
                            </span>
                            <span className="text-xs text-ink2 readout">{c.made_today}/{c.per_day} made · {c.uploaded_today} up</span>
                            <span className="text-xs text-muted w-full sm:w-auto">
                                {c.next_post ? `next ${at(c.next_post)}` : 'nothing scheduled'}
                                {c.views != null ? ` · ${c.views.toLocaleString()} views` : ''}
                                {c.subscribers != null ? ` · ${c.subscribers} subs` : ''}
                            </span>
                        </button>
                        {c.elsewhere?.map((v) => (
                            <p key={v.video_id} className="px-3 text-xs text-warn">
                                &quot;{v.title}&quot; went up on {v.on} by mistake.{' '}
                                <a href={`https://studio.youtube.com/video/${v.video_id}/edit`} target="_blank" rel="noreferrer"
                                   className="underline">Open it in Studio</a> and set it to Private or delete it.
                            </p>
                        ))}
                        {c.asked?.length > 0 && (
                            <p className="px-3 text-xs text-muted">Viewers asked for: {c.asked.join(' · ')} (the next ideas hear this)</p>
                        )}
                        {c.time_tip && (
                            <div className="flex flex-wrap items-center gap-2 px-3 text-xs text-ink2">
                                <Clock size={12} className="text-brass" /> <span className="flex-1 min-w-0">{c.time_tip.text}</span>
                                <button onClick={() => applyTip(c.id, { post_times: c.time_tip.post_times })} className="btn-ghost px-2 py-1 text-xs">
                                    use {c.time_tip.new}
                                </button>
                            </div>
                        )}
                        {c.length_tip && (
                            <div className="flex flex-wrap items-center gap-2 px-3 text-xs text-ink2">
                                <Clock size={12} className="text-brass" /> <span className="flex-1 min-w-0">{c.length_tip.text}</span>
                                <button onClick={() => applyTip(c.id, { minutes: c.length_tip.minutes })} className="btn-ghost px-2 py-1 text-xs">
                                    use {c.length_tip.minutes} min
                                </button>
                            </div>
                        )}
                        </div>
                    );
                })}
            </div>

            {data.upcoming.length > 0 && (
                <div className="card p-5 space-y-2">
                    <p className="text-sm text-ink flex items-center gap-1.5"><CalendarClock size={15} /> Going live next (YouTube publishes these, even with the laptop off)</p>
                    {data.upcoming.map((u) => (
                        <div key={u.video_id || u.at + u.title} className="flex flex-wrap items-center gap-x-2 text-xs">
                            <span className="readout text-muted w-24 shrink-0">{at(u.at)}</span>
                            <span className="text-ink2 flex-1 min-w-0 break-words">{u.title}</span>
                            <span className="text-muted">{u.channel}</span>
                            {u.video_id && (
                                <a href={`https://studio.youtube.com/video/${u.video_id}/edit`} target="_blank" rel="noreferrer"
                                    className="text-brass hover:underline inline-flex items-center gap-0.5">Studio <ExternalLink size={11} /></a>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {data.look && (
                <div className="card p-5 space-y-2">
                    <p className="text-sm text-ink flex items-center gap-1.5"><Clapperboard size={15} /> Video style (every channel except comedy)</p>
                    <label className="flex flex-wrap items-center gap-2 text-xs text-ink2">
                        voice
                        <select value={data.look.voice} onChange={(e) => setNotify({ voice: e.target.value })}
                            className="input-field !w-auto text-xs py-1" aria-label="voice">
                            <option value="edge">Free Microsoft voice</option>
                            <option value="gemini">Gemini voice (about 1 cent a Short)</option>
                        </select>
                    </label>
                    {data.look.samples?.length > 0 && (
                        <div className="space-y-1.5">
                            <p className="text-[11px] text-muted">Listen before you choose:</p>
                            {data.look.samples.map((s) => (
                                <div key={s.url} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink2">
                                    <span className="w-56 shrink-0">{s.label}</span>
                                    <audio controls preload="none" src={getApiUrl(s.url)} className="h-8 max-w-full" aria-label={s.label} />
                                </div>
                            ))}
                        </div>
                    )}
                    {data.look.voice === 'edge' && data.look.voice_rest && (
                        <p className="text-[11px] text-warn">
                            The free voice is unavailable right now, so Gemini voices the videos until {at(new Date(data.look.voice_rest.until * 1000).toISOString())} (reason: {data.look.voice_rest.reason}).
                        </p>
                    )}
                    <label className="flex items-center gap-2 text-xs text-ink2">
                        <input type="checkbox" checked={data.look.footage} onChange={() => setNotify({ footage: !data.look.footage })} aria-label="stock footage" />
                        free stock footage behind the text
                        {!(data.look.stock_keys?.PEXELS_API_KEY || data.look.stock_keys?.PIXABAY_API_KEY) && (
                            <span className="text-warn">(photos only until the Pexels and Pixabay keys are in)</span>
                        )}
                    </label>
                </div>
            )}

            <div className="card p-5 space-y-2">
                <p className="text-sm text-ink flex items-center gap-1.5"><Bell size={15} /> Windows notifications</p>
                <label className="flex items-center gap-2 text-xs text-ink2">
                    <input type="checkbox" checked={data.notify.reminders} onChange={() => setNotify({ reminders: !data.notify.reminders })} aria-label="reminders" />
                    remind me when something needs me (at {data.notify.slots.join(' and ')})
                </label>
                <label className="flex items-center gap-2 text-xs text-ink2">
                    <input type="checkbox" checked={data.notify.summary} onChange={() => setNotify({ summary: !data.notify.summary })} aria-label="evening summary" />
                    the day&apos;s numbers every evening at {data.notify.summary_at}, and the week&apos;s on Sundays
                </label>
                <label className="flex items-center gap-2 text-xs text-ink2">
                    <input type="checkbox" checked={data.notify.phone} onChange={() => setNotify({ phone: !data.notify.phone })} aria-label="also on Telegram" />
                    send them to my phone on Telegram too
                    {!data.notify.telegram && <span className="text-muted">(connect Telegram on the My channel tab first)</span>}
                </label>
                {held && (
                    <button onClick={() => setNotify({ snooze_until: 0 })} className="text-[11px] text-brass hover:underline">start reminders now</button>
                )}
            </div>
        </div>
    );
}
