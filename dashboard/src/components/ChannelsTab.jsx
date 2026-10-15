import React, { useCallback, useEffect, useState } from 'react';
import {
    Loader2, Youtube, Plus, Play, Trash2, LogOut, Layers, X, Copy, Check, ExternalLink, Rocket, AlertTriangle,
    Trophy, Brain, Music, HelpCircle, Flame, Landmark,
} from 'lucide-react';
import { apiJson } from '../lib/api';
import { getApiUrl } from '../config';
import ChannelKit from './ChannelKit';
import UpNext from './UpNext';

// Every YouTube channel Shortkaar runs (GET /api/my-channels, my_channels.py):
// the main one (comedy, set up in Autopilot) and the others, each with its
// own Google connection, kind of Short, number a day and posting times.

const KIND_ICON = { comedy: Rocket, cricket: Trophy, quiz: HelpCircle, music: Music, controversy: Flame, history: Landmark };
// Long videos (history_videos.py): minutes per video. Over 15 needs a phone-verified channel.
const MINUTES = [2, 3, 5, 8, 10, 12, 15, 20, 25, 30];
const STATUS = { running: 'making', done: 'waiting to upload', uploaded: 'uploaded', failed: 'failed', skipped: 'skipped' };
const PUBLISH_STEPS = `1. Open console.cloud.google.com and pick your Shortkaar project.
2. Go to: APIs & Services > OAuth consent screen (Google Auth Platform > Audience).
3. Under "Publishing status" press "Publish app", then confirm.
4. Back in Shortkaar (Channels tab), press "reconnect" once on each channel.`;

const when = (iso) => {
    if (!iso) return '';
    const d = typeof iso === 'number' ? new Date(iso * 1000) : new Date(iso);
    return d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
};

function CopyBox({ text }) {
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

function Times({ times, onChange, max }) {
    const [t, setT] = useState('');
    return (
        <div className="flex flex-wrap items-center gap-2">
            {times.map((x) => (
                <span key={x} className="inline-flex items-center gap-1 pl-3 pr-1 py-1 rounded-full border border-rule2 text-xs text-ink2">
                    {x}
                    <button onClick={() => onChange(times.filter((y) => y !== x))} aria-label={`remove ${x}`}
                        disabled={times.length <= 1} className="p-0.5 text-muted hover:text-danger"><X size={13} /></button>
                </span>
            ))}
            {times.length < max && (
                <>
                    <input type="time" value={t} onChange={(e) => setT(e.target.value)} className="input-field !w-auto text-xs py-1" aria-label="new posting time" />
                    <button onClick={() => t && !times.includes(t) && onChange([...times, t].sort())} className="btn-ghost px-2.5 py-1 text-xs">
                        <Plus size={13} /> add time
                    </button>
                </>
            )}
        </div>
    );
}

function Connection({ ch }) {
    const yt = ch.youtube || {};
    const connectUrl = getApiUrl(`/api/youtube/connect?back=${encodeURIComponent(window.location.origin)}`
        + (ch.main ? '' : `&channel=${encodeURIComponent(ch.id)}`));
    if (yt.connected && yt.channel) {
        return (
            <div className="flex items-center gap-3 min-w-0">
                {yt.channel.thumbnail && <img src={yt.channel.thumbnail} alt="" className="h-9 w-9 rounded-full shrink-0" />}
                <div className="min-w-0">
                    <p className="text-sm text-ink truncate">{yt.channel.title} <span className="text-muted">{yt.channel.handle}</span></p>
                    <p className="text-xs text-muted">{yt.channel.subscribers} subscribers · connected</p>
                </div>
                {/* A new sign-in replaces the token; nothing is revoked first. */}
                {yt.expires && <a href={connectUrl} className="btn-ghost px-3 py-1.5 text-xs shrink-0"><Youtube size={13} /> reconnect</a>}
            </div>
        );
    }
    if (!yt.configured) return <p className="text-xs text-warn">Set up YouTube first in My channel.</p>;
    return (
        <div className="space-y-1.5">
            <a href={connectUrl} className="btn-primary px-4 py-2 text-sm inline-flex"><Youtube size={15} /> connect youtube channel</a>
            {!ch.main && (
                <p className="text-[11px] text-muted leading-relaxed">
                    On Google&apos;s screen, pick the channel for {ch.name}. It starts making Shorts once it is connected.
                </p>
            )}
        </div>
    );
}

// engage.py switches; the main channel has them too (its replies default off:
// the Comments tab drafts them for you to send).
const ENGAGE = [
    ['first_comment', 'first comment with a question when each Short goes live'],
    ['auto_reply', 'reply to new comments (up to 15 a day; the quiz says who got it right)'],
    ['playlists', 'add each Short to a playlist for its kind'],
    ['cross_promo', 'name my other channels in the description ("More from us")'],
];

function EngageSwitches({ ch, save }) {
    return (
        <div className="space-y-1">
            <p className="text-xs text-muted">
                Engagement after posting{ch.main ? ' (off until you switch them on: they post on your live channel)' : ''}
            </p>
            {ENGAGE.map(([key, label]) => (
                <label key={key} className="flex items-start gap-2 text-xs text-ink2">
                    <input type="checkbox" checked={!!ch[key]} onChange={() => save({ [key]: !ch[key] })} aria-label={key} className="mt-0.5" />
                    {label}
                </label>
            ))}
        </div>
    );
}

function ChannelCard({ ch, maxPerDay, onChanged, onOpenAutopilot }) {
    const [busy, setBusy] = useState('');
    const [error, setError] = useState('');
    const [sure, setSure] = useState(false);
    const Icon = KIND_ICON[ch.kind] || Layers;

    const act = async (key, path, options) => {
        setBusy(key);
        setError('');
        try {
            await apiJson(path, options);
            await onChanged();
        } catch (e) {
            setError(e.detail || 'That did not work. Try again.');
        } finally {
            setBusy('');
        }
    };
    const save = (patch) => act('save', `/api/my-channels/${ch.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
    });

    const stats = ch.stats || {};
    const formats = Object.entries(stats.formats || {}).sort((a, b) => b[1].median - a[1].median);
    return (
        <div className="card p-5 space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="text-sm text-ink flex items-center gap-1.5"><Icon size={15} /> {ch.name}</p>
                    <p className="text-xs text-muted">{ch.kind_label}</p>
                </div>
                {ch.main ? (
                    <button onClick={onOpenAutopilot} className="btn-ghost px-3 py-1.5 text-xs"><Rocket size={13} /> settings in Autopilot</button>
                ) : (
                    <label className="flex items-center gap-2 text-xs text-ink2">
                        <input type="checkbox" checked={ch.enabled} onChange={() => save({ enabled: !ch.enabled })} aria-label={`run ${ch.name}`} />
                        make and post by itself
                    </label>
                )}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3">
                <Connection ch={ch} />
                {!ch.main && ch.youtube?.connected && (
                    <button onClick={() => act('disconnect', `/api/my-channels/${ch.id}/disconnect`, { method: 'POST' })}
                        disabled={busy === 'disconnect'} className="btn-ghost px-3 py-1.5 text-xs"><LogOut size={13} /> disconnect</button>
                )}
            </div>
            {error && <p className="text-xs text-danger" role="alert">{error}</p>}

            {ch.main ? (
                <>
                    <p className="text-xs text-ink2">
                        {ch.per_day} Shorts a day at {ch.post_times.join(', ')}. Ready to post and Autopilot run this channel as before.
                    </p>
                    <EngageSwitches ch={ch} save={save} />
                </>
            ) : (
                <>
                    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-ink2">
                        <label className="flex items-center gap-2">
                            {ch.long ? 'Videos a day' : 'Shorts a day'}
                            <select value={ch.per_day} onChange={(e) => save({ per_day: Number(e.target.value) })}
                                className="input-field !w-auto text-xs py-1" aria-label={ch.long ? 'videos a day' : 'shorts a day'}>
                                {Array.from({ length: ch.max_per_day || maxPerDay }, (_, k) => k + 1).map((n) => <option key={n} value={n}>{n}</option>)}
                            </select>
                        </label>
                        {ch.long && (
                            <>
                                <label className="flex items-center gap-2">
                                    minutes each
                                    <select value={ch.minutes} onChange={(e) => save({ minutes: Number(e.target.value) })}
                                        className="input-field !w-auto text-xs py-1" aria-label="minutes each">
                                        {MINUTES.map((n) => <option key={n} value={n}>{n}</option>)}
                                    </select>
                                </label>
                                <label className="flex items-center gap-2">
                                    language
                                    <select value={ch.lang} onChange={(e) => save({ lang: e.target.value })}
                                        className="input-field !w-auto text-xs py-1" aria-label="language">
                                        <option value="urdu">Urdu (Roman)</option>
                                        <option value="english">English</option>
                                    </select>
                                </label>
                            </>
                        )}
                        <label className="flex items-center gap-2">
                            <input type="checkbox" checked={ch.auto_upload} onChange={() => save({ auto_upload: !ch.auto_upload })} aria-label="upload by itself" />
                            upload by itself
                        </label>
                        <label className="flex items-center gap-2">
                            handle
                            <input defaultValue={ch.handle} onBlur={(e) => e.target.value !== ch.handle && save({ handle: e.target.value })}
                                placeholder={ch.youtube?.channel?.handle || '@yourchannel'} className="input-field !w-36 text-xs py-1" aria-label="handle" />
                        </label>
                        <label className="flex items-center gap-2">
                            colour
                            <input type="color" value={ch.color} onChange={(e) => save({ color: e.target.value })} className="h-7 w-9 rounded border border-rule bg-transparent" aria-label="colour" />
                        </label>
                    </div>
                    {ch.kind === 'cricket' && (
                        <label className="flex items-start gap-2 text-xs text-ink2">
                            <input type="checkbox" checked={!!ch.match_watch} onChange={() => save({ match_watch: !ch.match_watch })}
                                aria-label="fast match results" className="mt-0.5" />
                            fast results: when Pakistan or India finish a match, make its Short next and post it 20 minutes later (checked every 2 hours)
                        </label>
                    )}
                    {ch.kind === 'quiz' && (
                        <input defaultValue={ch.notes} onBlur={(e) => e.target.value !== ch.notes && save({ notes: e.target.value })}
                            placeholder="Favourite quiz topics, optional (e.g. Pakistan history, science)"
                            className="input-field text-xs py-1.5" aria-label="quiz topics" maxLength={300} />
                    )}
                    {ch.kind === 'history' && (
                        <>
                            <input defaultValue={ch.notes} onBlur={(e) => e.target.value !== ch.notes && save({ notes: e.target.value })}
                                placeholder="Topics you want (e.g. Rome, Karbala, the Caliphs, the US economy)"
                                className="input-field text-xs py-1.5" aria-label="history topics" maxLength={300} />
                            {ch.minutes > 15 && (
                                <p className="text-xs text-warn">
                                    Videos over 15 minutes need a verified channel: switch to this channel on YouTube, open youtube.com/verify and verify with your phone. The same unlocks custom thumbnails.
                                </p>
                            )}
                        </>
                    )}
                    <div>
                        <p className="text-xs text-muted mb-2">Posting times (every day, this computer&apos;s time)</p>
                        <Times times={ch.post_times} max={ch.max_per_day || maxPerDay} onChange={(t) => save({ post_times: t })} />
                    </div>
                    <EngageSwitches ch={ch} save={save} />
                    <ChannelKit ch={ch} />
                    <UpNext ch={ch} onChanged={onChanged} />

                    <div className="flex flex-wrap items-center justify-between gap-3 rounded-input border border-rule p-3">
                        <p className="text-xs text-ink2">
                            Today: {ch.made_today} of {ch.per_day} made, {ch.uploaded_today} uploaded, {ch.waiting} waiting to upload.
                            {ch.running?.length > 0 && <span className="text-brass"> Making now: {ch.running[0]}.</span>}
                            {ch.upload_paused_until * 1000 > Date.now() && (
                                <span className="text-warn"> YouTube&apos;s daily upload limit: uploads start again {when(ch.upload_paused_until)}.</span>
                            )}
                        </p>
                        <button onClick={() => act('make', `/api/my-channels/${ch.id}/make`, { method: 'POST' })}
                            disabled={busy === 'make' || ch.running?.length > 0} className="btn-ghost px-3 py-1.5 text-xs">
                            {busy === 'make' ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} make one now
                        </button>
                    </div>

                    {ch.jobs?.length > 0 && (
                        <div className="space-y-1.5">
                            <p className="text-xs text-ink">{ch.long ? 'Latest videos' : 'Latest Shorts'}</p>
                            {ch.jobs.slice(0, 8).map((j) => (
                                <div key={j.job_id || j.at} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
                                    <span className={`readout ${j.status === 'failed' ? 'text-danger' : j.status === 'uploaded' ? 'text-ok' : 'text-muted'}`}>
                                        {STATUS[j.status] || j.status}
                                    </span>
                                    <span className="text-ink2 min-w-0 break-words flex-1">{j.title || j.label}</span>
                                    {j.slot && <span className="text-muted">{when(j.slot)}</span>}
                                    {j.video_url && (
                                        <a href={getApiUrl(j.video_url)} target="_blank" rel="noreferrer" className="text-brass hover:underline">watch</a>
                                    )}
                                    {j.status === 'done' && (
                                        <button onClick={() => act('skip', `/api/my-channels/${ch.id}/skip/${j.job_id}`, { method: 'POST' })}
                                            disabled={busy === 'skip'} className="text-muted hover:text-danger" aria-label={`skip ${j.title || j.label}`}>skip</button>
                                    )}
                                    {j.video_id && (
                                        <a href={`https://studio.youtube.com/video/${j.video_id}/edit`} target="_blank" rel="noreferrer"
                                            className="text-brass hover:underline inline-flex items-center gap-0.5">Studio <ExternalLink size={11} /></a>
                                    )}
                                    {j.status === 'failed' && j.error && <span className="text-muted w-full">{j.error}</span>}
                                </div>
                            ))}
                        </div>
                    )}

                    {stats.at && (
                        <div className="space-y-1">
                            <p className="text-xs text-ink flex items-center gap-1.5"><Brain size={13} /> What it learned (every 6 hours)</p>
                            <p className="text-xs text-ink2">
                                {stats.tracked} Shorts tracked, {stats.counted} counted (public 2 days), {stats.views} views in all
                                {stats.counted > 0 ? `, median ${stats.median}` : ''}.
                            </p>
                            {formats.length > 1 && (
                                <p className="text-xs text-ink2">{formats.map(([f, v]) => `${f}: median ${v.median} (${v.shorts})`).join(' · ')}</p>
                            )}
                            {stats.best?.length > 0 && <p className="text-[11px] text-muted">Best: {stats.best.slice(0, 3).join(' · ')}</p>}
                        </div>
                    )}

                    <div className="flex justify-end">
                        {sure ? (
                            <span className="flex items-center gap-2 text-xs">
                                <span className="text-ink2">Remove {ch.name} from Shortkaar? Its videos stay on YouTube.</span>
                                <button onClick={() => act('remove', `/api/my-channels/${ch.id}`, { method: 'DELETE' })} className="btn-ghost px-2.5 py-1 text-xs text-danger">remove</button>
                                <button onClick={() => setSure(false)} className="btn-ghost px-2.5 py-1 text-xs">keep</button>
                            </span>
                        ) : (
                            <button onClick={() => setSure(true)} className="text-xs text-muted hover:text-danger inline-flex items-center gap-1"><Trash2 size={12} /> remove channel</button>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}

function AddChannel({ kinds, onAdded }) {
    const [kind, setKind] = useState('');
    const [name, setName] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const add = async () => {
        setBusy(true);
        setError('');
        try {
            await apiJson('/api/my-channels', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind, name }),
            });
            setKind('');
            setName('');
            await onAdded();
        } catch (e) {
            setError(e.detail || 'Could not add it.');
        } finally {
            setBusy(false);
        }
    };
    return (
        <div className="card p-5 space-y-3">
            <p className="text-sm text-ink flex items-center gap-1.5"><Plus size={15} /> Add a channel</p>
            <p className="text-xs text-muted leading-relaxed">
                Make the new channel on YouTube first (YouTube app or studio.youtube.com: your picture &gt; Settings &gt; Add or manage channels &gt; Create a channel). Then add it here and connect it.
            </p>
            <div className="grid gap-2 sm:grid-cols-3">
                {Object.entries(kinds).map(([k, v]) => {
                    const Icon = KIND_ICON[k] || Layers;
                    return (
                        <button key={k} onClick={() => { setKind(k); setName(v.label); }}
                            className={`text-left rounded-input border p-3 space-y-1 ${kind === k ? 'border-brass' : 'border-rule hover:border-rule2'}`}>
                            <span className="text-sm text-ink flex items-center gap-1.5"><Icon size={14} /> {v.label}</span>
                            <span className="block text-[11px] text-muted leading-relaxed">{v.about}</span>
                        </button>
                    );
                })}
            </div>
            {kind && (
                <div className="flex flex-wrap items-center gap-2">
                    <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} aria-label="channel name"
                        className="input-field flex-1 min-w-[12rem] text-sm py-1.5" />
                    <button onClick={add} disabled={busy || !name.trim()} className="btn-primary px-4 py-2 text-sm">
                        {busy ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />} add channel
                    </button>
                </div>
            )}
            {error && <p className="text-xs text-danger" role="alert">{error}</p>}
        </div>
    );
}

export default function ChannelsTab({ notice, onOpenAutopilot }) {
    const [data, setData] = useState(null);
    const [error, setError] = useState('');

    const load = useCallback(() => apiJson('/api/my-channels').then((d) => { setData(d); setError(''); })
        .catch((e) => setError(e.detail || 'Could not load your channels.')), []);
    useEffect(() => { load(); }, [load]);
    // While a Short is being made, follow it.
    const busy = (data?.channels || []).some((c) => c.running?.length > 0);
    useEffect(() => {
        if (!busy) return undefined;
        const t = setInterval(load, 15000);
        return () => clearInterval(t);
    }, [busy, load]);

    if (!data) {
        return <div className="card p-5 text-sm text-muted">{error || <><Loader2 size={14} className="animate-spin inline" /> loading…</>}</div>;
    }
    const expiring = data.channels.filter((c) => c.youtube?.expires);
    const soonest = expiring.reduce((m, c) => (m && m < c.youtube.expires ? m : c.youtube.expires), 0);
    return (
        <div className="space-y-4 max-w-4xl">
            <div className="card p-5 space-y-2">
                <p className="text-sm text-ink flex items-center gap-1.5"><Layers size={15} /> Your channels</p>
                <p className="text-xs text-muted leading-relaxed">
                    Each channel has its own YouTube connection, its own kind of Short and its own posting times. Shortkaar makes them one at a time while this computer is on, and uploads each one into the channel&apos;s next free time. YouTube publishes them at that time, even when the computer is off.
                </p>
                {notice?.connected && <p className="text-xs text-ok">Connected.</p>}
                {notice?.error && <p className="text-xs text-danger" role="alert">{notice.error}</p>}
            </div>

            {expiring.length > 0 && (
                <div className="card p-5 space-y-2 border-warn">
                    <p className="text-sm text-warn flex items-center gap-1.5"><AlertTriangle size={15} /> Your Google connection stops working {soonest ? `around ${when(soonest)}` : 'after 7 days'}</p>
                    <p className="text-xs text-ink2 leading-relaxed">
                        Your Google project is still in &quot;Testing&quot;, and Google ends those sign-ins 7 days after you connect. Change it to &quot;In production&quot; once and reconnect each channel, and it keeps working. Nothing is listed anywhere, and only someone with your project&apos;s keys can use it:
                    </p>
                    <CopyBox text={PUBLISH_STEPS} />
                    <p className="text-[11px] text-muted">Google may show &quot;Google hasn&apos;t verified this app&quot; when you connect: press Advanced, then Go to your project. It is your own app.</p>
                </div>
            )}

            {data.channels.map((ch) => (
                <ChannelCard key={ch.id} ch={ch} maxPerDay={data.max_per_day} onChanged={load} onOpenAutopilot={onOpenAutopilot} />
            ))}
            <AddChannel kinds={data.kinds} onAdded={load} />
        </div>
    );
}
