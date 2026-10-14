import React, { useEffect, useState } from 'react';
import { Loader2, Brain, RefreshCw } from 'lucide-react';
import { apiJson } from '../lib/api';

// "What Shortkaar is learning" (GET/PUT /api/learning, POST /api/learning/run,
// learning.py): the numbers of its own Shorts, the test it is running, the
// changes it kept and how each source channel does.

const AUDIT_FORM = 'https://support.google.com/youtube/contact/yt_api_form';
const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'not yet');

export default function LearningCard() {
    const [data, setData] = useState(null);
    const [busy, setBusy] = useState('');
    const [error, setError] = useState('');

    const load = () => apiJson('/api/learning').then(setData).catch((e) => setError(e.detail || 'Could not load.'));
    useEffect(() => { load(); }, []);

    const learnNow = async () => {
        setBusy('run');
        setError('');
        try {
            setData(await apiJson('/api/learning/run', { method: 'POST' }));
        } catch (e) {
            setError(e.detail || 'Could not learn now.');
        } finally {
            setBusy('');
        }
    };
    const toggle = async () => {
        setData(await apiJson('/api/learning', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ learn: !data.learn }),
        }));
    };

    if (!data) {
        return <div className="card p-5 text-sm text-muted">{error || <><Loader2 size={14} className="animate-spin inline" /> loading…</>}</div>;
    }
    const exp = data.experiment;
    return (
        <div className="card p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <p className="text-sm text-ink flex items-center gap-1.5"><Brain size={15} /> What Shortkaar is learning</p>
                    <p className="text-xs text-muted">From your own Shorts, every 6 hours. Last time: {when(data.last_run)}.</p>
                </div>
                <div className="flex items-center gap-2">
                    <label className="flex items-center gap-2 text-xs text-ink2">
                        <input type="checkbox" checked={data.learn} onChange={toggle} aria-label="learn and adjust" />
                        learn and adjust by itself
                    </label>
                    <button onClick={learnNow} disabled={busy === 'run'} className="btn-ghost px-3 py-1.5 text-xs">
                        {busy === 'run' ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} learn now
                    </button>
                </div>
            </div>
            {error && <p className="text-xs text-danger" role="alert">{error}</p>}
            {data.locked > 0 && (
                <p className="text-xs text-warn leading-relaxed">
                    {data.locked} upload{data.locked === 1 ? ' is' : 's are'} past {data.locked === 1 ? 'its' : 'their'} time and still private: YouTube may be holding uploads from your Google project.
                    Set them to Public in Studio, and fill in the <a href={AUDIT_FORM} target="_blank" rel="noreferrer" className="underline">audit form</a> (answers in docs/youtube-api-audit.md).
                </p>
            )}

            <p className="text-sm text-ink2">
                {data.tracked} Shorts tracked, {data.public} public, {data.counted} counted, {data.total_views} views in all
                {data.counted > 0 ? `, median ${data.median_views} views per Short` : ''}.
                {data.blocked > 0 && <span className="text-warn"> {data.blocked} blocked by a copyright claim.</span>}
            </p>
            {data.counted < 8 && (
                <p className="text-xs text-muted leading-relaxed">
                    Early days: a Short counts once it has been public for {Math.round(data.mature_hours / 24)} days, because Shorts get most of their views in that time.
                    Clear patterns need about 16 counted Shorts, so the first decisions come in about a week.
                </p>
            )}

            {exp && (
                <div className="rounded-input border border-rule p-3 space-y-1.5">
                    <p className="text-xs text-ink">Testing now: {exp.label}</p>
                    <p className="text-[11px] text-muted">Autopilot alternates it per video. The other side is kept only if it clearly gets more views (needs {exp.need} counted Shorts each).</p>
                    {Object.entries(exp.arms).map(([arm, a]) => (
                        <p key={arm} className="text-xs text-ink2">
                            <span className="readout mr-2">{arm}{arm === exp.base ? ' (now)' : ''}</span>
                            {a.made} made, {a.counted} of {exp.need} counted{a.counted ? `, median ${a.median_views} views` : ''}
                        </p>
                    ))}
                </div>
            )}

            {data.kept.length > 0 && (
                <div className="space-y-1">
                    <p className="text-xs text-ink">Changes it kept</p>
                    {data.kept.map((k) => <p key={k} className="text-xs text-ink2">{k}</p>)}
                </div>
            )}

            {Object.keys(data.genres).length > 1 && (
                <p className="text-xs text-ink2">
                    {Object.entries(data.genres).map(([g, v]) => `${g}: median ${v.median_views} views (${v.shorts})`).join(' · ')}
                </p>
            )}

            {data.sources.length > 0 && (
                <div className="space-y-1">
                    <p className="text-xs text-ink">Source channels (research picks the better ones first)</p>
                    {data.sources.map((s) => (
                        <p key={s.name} className="text-xs text-ink2 flex flex-wrap gap-x-2">
                            <span className="text-ink">{s.name}</span>
                            <span>{s.shorts} Shorts, median {s.median} views, score {s.score}</span>
                            {s.rest_until * 1000 > Date.now() && <span className="text-warn">resting until {when(s.rest_until)}</span>}
                        </p>
                    ))}
                </div>
            )}

            {data.history.length > 0 && (
                <div className="space-y-1">
                    <p className="text-xs text-ink">What it did</p>
                    {data.history.map((h) => (
                        <p key={h.at + h.text} className="text-[11px] text-muted"><span className="readout mr-2">{when(h.at)}</span>{h.text}</p>
                    ))}
                </div>
            )}
        </div>
    );
}
