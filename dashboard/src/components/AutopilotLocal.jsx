import React, { useEffect, useState } from 'react';
import { Loader2, Play, Plus, X, RefreshCw, Rocket, Clock, Upload } from 'lucide-react';
import { apiJson } from '../lib/api';

// Daily Autopilot on this computer (GET/PUT /api/local-autopilot,
// autopilot_local.py): every day at a set time it makes the planned Shorts
// on its own, and can upload each one into the next posting time.

const when = (ts) => new Date(ts * 1000).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
const STATUS = { completed: 'done', processing: 'making', queued: 'waiting', failed: 'failed', missing: 'deleted', building: 'making' };

function Toggle({ on, onChange, label }) {
    return (
        <button type="button" role="switch" aria-checked={on} aria-label={label} onClick={() => onChange(!on)}
            className={`relative h-6 w-11 rounded-full transition-colors shrink-0 ${on ? 'bg-brass' : 'bg-paper3 border border-rule2'}`}>
            <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${on ? 'left-[22px]' : 'left-0.5'}`} />
        </button>
    );
}

function Num({ value, onChange, min = 0, max = 10, label }) {
    return (
        <input type="number" min={min} max={max} value={value} aria-label={label}
            onChange={(e) => onChange(Math.max(min, Math.min(max, Number(e.target.value) || 0)))}
            className="input-field !w-20 text-sm py-1.5" />
    );
}

export default function AutopilotLocal({ onOpenChannelTab }) {
    const [cfg, setCfg] = useState(null);
    const [looks, setLooks] = useState({});
    const [yt, setYt] = useState(null);
    const [dirty, setDirty] = useState(false);
    const [busy, setBusy] = useState('');
    const [error, setError] = useState('');
    const [newChannel, setNewChannel] = useState('');
    const [newTime, setNewTime] = useState('21:00');

    const load = async () => {
        setError('');
        try {
            const d = await apiJson('/api/local-autopilot');
            setCfg(d.settings);
            setLooks(d.looks || {});
            setDirty(false);
        } catch (e) {
            setError(e.detail || 'Could not load Autopilot.');
        }
        apiJson('/api/youtube/status').then(setYt).catch(() => setYt(null));
    };
    useEffect(() => { load(); }, []);

    const set = (k, v) => { setCfg((c) => ({ ...c, [k]: v })); setDirty(true); };

    const save = async (patch = {}) => {
        setBusy('save');
        setError('');
        try {
            const body = { ...cfg, ...patch };
            delete body.runs;
            const d = await apiJson('/api/local-autopilot', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
            });
            setCfg(d.settings);
            setLooks(d.looks || {});
            setDirty(false);
        } catch (e) {
            setError(e.detail || 'Could not save.');
        } finally {
            setBusy('');
        }
    };

    const addChannel = async () => {
        const text = newChannel.trim();
        if (!text) return;
        setBusy('channel');
        setError('');
        try {
            const info = await apiJson(`/api/finder/channel?url=${encodeURIComponent(text)}`);
            if (!cfg.channels.some((c) => c.url === info.url)) {
                set('channels', [...cfg.channels, { url: info.url, name: info.name }]);
            }
            setNewChannel('');
        } catch (e) {
            setError(e.detail || 'Could not find that channel.');
        } finally {
            setBusy('');
        }
    };

    const runNow = async () => {
        if (dirty) await save();
        setBusy('run');
        setError('');
        try {
            const d = await apiJson('/api/local-autopilot/run', { method: 'POST' });
            setCfg(d.settings);
        } catch (e) {
            setError(e.detail || 'Could not start the run.');
        } finally {
            setBusy('');
        }
    };

    if (!cfg) {
        return (
            <div className="h-full overflow-y-auto p-4 sm:p-8">
                {error ? <p className="text-sm text-danger">{error}</p>
                    : <div className="flex items-center gap-2 text-sm text-muted"><Loader2 size={16} className="animate-spin" /> loading…</div>}
            </div>
        );
    }

    const ytReady = yt?.connected;
    const lookLine = (g, label) => (looks[g]
        ? <span>{label} Shorts copy the look of your last {label} Short made by hand ({when(looks[g])}).</span>
        : <span>{label} Shorts use the Punchline Bazaar look until you make one {label} Short by hand.</span>);

    return (
        <div className="h-full overflow-y-auto p-4 sm:p-8 animate-fade">
            <div className="max-w-4xl mx-auto space-y-5">
                <div className="flex flex-wrap items-end justify-between gap-3">
                    <div>
                        <p className="eyebrow mb-1.5">AUTOPILOT</p>
                        <h1 className="font-display lowercase text-2xl text-ink">shorts made while you sleep</h1>
                        <p className="text-xs text-muted mt-1 max-w-2xl leading-relaxed">
                            Every day at the time below, Shortkaar makes your planned Shorts by itself. They show up in History.
                            Keep this computer on with Shortkaar running. If it was off at that time, the day&apos;s Shorts are made when it starts again.
                        </p>
                    </div>
                    <div className="flex gap-2">
                        <button onClick={runNow} disabled={!!busy} className="btn-ghost px-3 py-2 text-xs" title="Make today's Shorts now">
                            {busy === 'run' ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} make today&apos;s shorts now
                        </button>
                        <button onClick={() => save()} disabled={!dirty || !!busy} className="btn-primary px-4 py-2 text-xs">
                            {busy === 'save' ? <Loader2 size={14} className="animate-spin" /> : null} save
                        </button>
                    </div>
                </div>
                {error && <p className="text-sm text-danger" role="alert">{error}</p>}

                <div className="card p-5 space-y-4">
                    <div className="flex items-center justify-between gap-3">
                        <div>
                            <p className="text-sm text-ink">Daily plan</p>
                            <p className="text-xs text-muted">{cfg.enabled ? `On: runs every day at ${cfg.run_at}.` : 'Off: nothing runs on its own.'}</p>
                        </div>
                        <Toggle on={cfg.enabled} onChange={(v) => set('enabled', v)} label="autopilot on" />
                    </div>
                    <div className="grid sm:grid-cols-3 gap-4">
                        <label className="text-xs text-muted space-y-1.5 block">
                            <span className="flex items-center gap-1"><Clock size={12} /> run at</span>
                            <input type="time" value={cfg.run_at} onChange={(e) => set('run_at', e.target.value)} className="input-field text-sm py-1.5" />
                        </label>
                        <label className="text-xs text-muted space-y-1.5 block">
                            <span>comedy shorts a day</span>
                            <Num value={cfg.comedy_per_day} onChange={(v) => set('comedy_per_day', v)} max={10} label="comedy per day" />
                        </label>
                        <label className="text-xs text-muted space-y-1.5 block">
                            <span>cricket shorts a day</span>
                            <div className="flex gap-2 items-center">
                                <Num value={cfg.cricket_per_day} onChange={(v) => set('cricket_per_day', v)} max={5} label="cricket per day" />
                                <select value={cfg.cricket_kinds} onChange={(e) => set('cricket_kinds', e.target.value)} className="input-field !w-auto text-xs py-1.5" aria-label="cricket kind">
                                    <option value="both">matches + facts</option>
                                    <option value="match">matches only</option>
                                    <option value="topic">facts & stats only</option>
                                </select>
                            </div>
                        </label>
                    </div>
                    <div className="flex flex-wrap items-center gap-3 pt-1">
                        <Toggle on={!!cfg.weekly_long} onChange={(v) => set('weekly_long', v)} label="weekly long video" />
                        <span className="text-xs text-ink2">Build a long video of the week&apos;s best Shorts every</span>
                        <select value={cfg.weekly_day ?? 6} onChange={(e) => set('weekly_day', Number(e.target.value))}
                            className="input-field !w-auto text-xs py-1.5" aria-label="weekly day">
                            {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map((d, i) => (
                                <option key={d} value={i}>{d}</option>
                            ))}
                        </select>
                    </div>
                    <p className="text-[11px] text-muted leading-relaxed">
                        {lookLine('comedy', 'comedy')} {lookLine('cricket', 'cricket')} Cricket ideas come from this week&apos;s news, never the same idea twice.
                    </p>
                </div>

                <div className="card p-5 space-y-3">
                    <p className="text-sm text-ink">Source channels for comedy</p>
                    <p className="text-xs text-muted">Each day it takes their newest videos it has not used yet, a few Shorts per video, never the same moment twice.</p>
                    {cfg.channels.length === 0 && <p className="text-xs text-warn">No channel yet. Add one below or from Find videos.</p>}
                    <div className="flex flex-wrap gap-2">
                        {cfg.channels.map((c) => (
                            <span key={c.url} className="inline-flex items-center gap-1.5 pl-3 pr-1 py-1 rounded-full border border-rule2 text-xs text-ink2">
                                <a href={c.url} target="_blank" rel="noreferrer" className="hover:text-brass">{c.name || c.url}</a>
                                <button onClick={() => set('channels', cfg.channels.filter((x) => x.url !== c.url))} aria-label={`remove ${c.name}`}
                                    className="p-0.5 text-muted hover:text-danger"><X size={13} /></button>
                            </span>
                        ))}
                    </div>
                    <form onSubmit={(e) => { e.preventDefault(); addChannel(); }} className="flex gap-2">
                        <input value={newChannel} onChange={(e) => setNewChannel(e.target.value)} placeholder="channel link or @handle"
                            className="input-field flex-1 text-sm py-1.5" aria-label="channel" />
                        <button type="submit" disabled={!newChannel.trim() || busy === 'channel'} className="btn-ghost px-3 py-1.5 text-xs">
                            {busy === 'channel' ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} add
                        </button>
                    </form>
                    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 pt-1">
                        <label className="flex items-center gap-2 text-xs text-ink2">
                            <input type="checkbox" checked={cfg.cc_only} onChange={(e) => set('cc_only', e.target.checked)} />
                            only videos marked Creative Commons (reuse allowed)
                        </label>
                        <label className="flex items-center gap-2 text-xs text-muted">
                            video length
                            <Num value={cfg.min_minutes} onChange={(v) => set('min_minutes', v)} max={600} label="min minutes" />
                            to
                            <Num value={cfg.max_minutes} onChange={(v) => set('max_minutes', v)} max={600} label="max minutes" />
                            min
                        </label>
                    </div>
                    {!cfg.cc_only && (
                        <p className="text-[11px] text-warn">Videos without a reuse licence can get claims or strikes. Only turn this off for channels that gave you permission.</p>
                    )}
                </div>

                <div className="card p-5 space-y-3">
                    <div className="flex items-center justify-between gap-3">
                        <div>
                            <p className="text-sm text-ink flex items-center gap-1.5"><Upload size={14} /> Upload to YouTube by itself</p>
                            <p className="text-xs text-muted">Each finished Short goes into the next free posting time below, scheduled on your channel.</p>
                        </div>
                        <Toggle on={cfg.auto_upload && ytReady} onChange={(v) => set('auto_upload', v)} label="auto upload" />
                    </div>
                    {!ytReady && (
                        <p className="text-[11px] text-warn">
                            Connect your channel first in <button onClick={onOpenChannelTab} className="underline hover:text-brass">My channel</button>.
                        </p>
                    )}
                    <div>
                        <p className="text-xs text-muted mb-2">Posting times (every day, this computer&apos;s time). Also used by the upload button on each Short.</p>
                        <div className="flex flex-wrap items-center gap-2">
                            {cfg.post_times.map((t) => (
                                <span key={t} className="inline-flex items-center gap-1 pl-3 pr-1 py-1 rounded-full border border-rule2 text-xs text-ink2">
                                    {t}
                                    <button onClick={() => set('post_times', cfg.post_times.filter((x) => x !== t))} aria-label={`remove ${t}`}
                                        disabled={cfg.post_times.length <= 1} className="p-0.5 text-muted hover:text-danger"><X size={13} /></button>
                                </span>
                            ))}
                            <input type="time" value={newTime} onChange={(e) => setNewTime(e.target.value)} className="input-field !w-auto text-xs py-1" aria-label="new posting time" />
                            <button onClick={() => newTime && !cfg.post_times.includes(newTime) && set('post_times', [...cfg.post_times, newTime].sort())}
                                className="btn-ghost px-2.5 py-1 text-xs"><Plus size={13} /> add time</button>
                        </div>
                    </div>
                </div>

                <div className="card p-5">
                    <div className="flex items-center justify-between gap-3 mb-3">
                        <p className="text-sm text-ink flex items-center gap-1.5"><Rocket size={14} /> Recent runs</p>
                        <button onClick={load} className="btn-ghost px-2.5 py-1 text-xs"><RefreshCw size={13} /> refresh</button>
                    </div>
                    {(!cfg.runs || cfg.runs.length === 0) && <p className="text-xs text-muted">No run yet.</p>}
                    <div className="space-y-4">
                        {(cfg.runs || []).map((run) => (
                            <div key={run.at} className="border-t border-rule pt-3 first:border-0 first:pt-0">
                                <p className="readout mb-1.5">{when(run.at)} · {run.reason === 'manual' ? 'started by you' : 'daily run'}</p>
                                {run.jobs.map((j) => (
                                    <div key={j.job_id} className="flex items-center gap-2 text-xs py-0.5">
                                        <span className="badge-brass shrink-0">{j.kind}</span>
                                        <span className="text-ink2 truncate flex-1" title={j.label}>{j.label}</span>
                                        <span className={`shrink-0 ${j.status === 'failed' ? 'text-danger' : j.status === 'completed' ? 'text-ok' : 'text-muted'}`}>
                                            {STATUS[j.status] || j.status || 'waiting'}{j.status === 'completed' ? ` · ${j.ready} ready` : ''}
                                        </span>
                                    </div>
                                ))}
                                {run.notes.map((n, i) => <p key={i} className="text-[11px] text-muted">{n}</p>)}
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
