import React, { useEffect, useState } from 'react';
import { Search, Loader2, Scissors, Rocket, ExternalLink, Check } from 'lucide-react';
import { apiJson } from '../lib/api';

// "Find videos": YouTube search with the Creative Commons filter on
// (GET /api/finder/search, channel_tools.py), so every result says the
// uploader allows reuse. One click sends a link to Make Shorts, or adds its
// channel to Autopilot's sources.

const QUICK = [
    'pakistani stand up comedy',
    'urdu stand up comedy',
    'hindi stand up comedy',
    'urdu comedy podcast',
    'cricket podcast urdu',
];
const DURATIONS = [['long', 'over 20 min'], ['medium', '4-20 min'], ['any', 'any length']];
const DATES = [['any', 'any time'], ['year', 'this year'], ['month', 'this month'], ['week', 'this week']];
const SORTS = [['relevance', 'best match'], ['views', 'most viewed'], ['date', 'newest']];

const mmss = (s) => {
    if (!s) return '';
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return h ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`;
};
const views = (n) => (n == null ? '' : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M views` : n >= 1e3 ? `${Math.round(n / 1e3)}K views` : `${n} views`);

export default function FinderTab({ onMakeShorts }) {
    const [q, setQ] = useState('');
    const [duration, setDuration] = useState('long');
    const [date, setDate] = useState('any');
    const [sort, setSort] = useState('relevance');
    const [results, setResults] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [added, setAdded] = useState({});
    // Batch: tick several results, one job per video (POST /api/finder/batch).
    const [selected, setSelected] = useState([]);
    const [perVideo, setPerVideo] = useState(3);
    const [batchMsg, setBatchMsg] = useState('');
    const [batchBusy, setBatchBusy] = useState(false);
    // An idea from Similar channels arrives as a ready search.
    useEffect(() => {
        let q0 = null;
        try { q0 = localStorage.getItem('os_finder_q'); if (q0) localStorage.removeItem('os_finder_q'); } catch { /* ignore */ }
        if (q0) search(q0);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    const toggleSel = (url) => setSelected((s) => (s.includes(url) ? s.filter((x) => x !== url) : [...s, url].slice(0, 10)));
    const runBatch = async () => {
        setBatchBusy(true);
        setBatchMsg('');
        setError('');
        try {
            const d = await apiJson('/api/finder/batch', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ urls: selected, clips: perVideo }),
            });
            setBatchMsg(`${d.started.length} ${d.started.length === 1 ? 'job' : 'jobs'} started. The Shorts appear in History and Ready to post as each one finishes.`
                + (d.failed.length ? ` ${d.failed.length} could not start.` : ''));
            setSelected([]);
        } catch (e) {
            setError(e.detail || 'Could not start the jobs.');
        } finally {
            setBatchBusy(false);
        }
    };

    const search = async (text) => {
        const query = (text ?? q).trim();
        if (!query) return;
        setQ(query);
        setLoading(true);
        setError('');
        try {
            const p = new URLSearchParams({ q: query, duration, date, sort, cc: '1' });
            const d = await apiJson(`/api/finder/search?${p}`);
            setResults(d.results || []);
        } catch (e) {
            setError(e.detail || 'Search failed. Try again.');
        } finally {
            setLoading(false);
        }
    };

    const addChannel = async (v) => {
        if (!v.channel_url) return;
        try {
            const cur = await apiJson('/api/local-autopilot');
            const channels = cur.settings.channels || [];
            if (!channels.some((c) => c.url === v.channel_url)) {
                await apiJson('/api/local-autopilot', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ channels: [...channels, { url: v.channel_url, name: v.channel }] }),
                });
            }
            setAdded((a) => ({ ...a, [v.channel_url]: true }));
        } catch (e) {
            setError(e.detail || 'Could not add that channel.');
        }
    };

    const select = (value, set, options, label) => (
        <select value={value} onChange={(e) => set(e.target.value)} aria-label={label}
            className="input-field !w-auto text-xs py-1.5">
            {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
    );

    return (
        <div className="h-full overflow-y-auto p-4 sm:p-8 animate-fade">
            <div className="max-w-6xl mx-auto">
                <p className="eyebrow mb-1.5">FIND VIDEOS</p>
                <h1 className="font-display lowercase text-2xl text-ink">videos you may reuse</h1>
                <p className="text-xs text-muted mt-1 max-w-2xl leading-relaxed">
                    Every result is marked Creative Commons by its uploader, which allows reuse with credit.
                    That label is only what the uploader claims: prefer the creator&apos;s own channel, and skip
                    re-uploads of TV shows and stage dramas.
                </p>

                <form onSubmit={(e) => { e.preventDefault(); search(); }} className="mt-5 flex flex-col sm:flex-row gap-2">
                    <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="search, e.g. urdu stand up comedy"
                        className="input-field flex-1" aria-label="search" />
                    <button type="submit" disabled={loading || !q.trim()} className="btn-primary px-5 py-2 text-sm">
                        {loading ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />} search
                    </button>
                </form>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                    {select(duration, setDuration, DURATIONS, 'length')}
                    {select(date, setDate, DATES, 'upload date')}
                    {select(sort, setSort, SORTS, 'sort')}
                    <span className="mx-1 h-4 w-px bg-rule2" aria-hidden="true" />
                    {QUICK.map((t) => (
                        <button key={t} type="button" onClick={() => search(t)}
                            className="px-2.5 py-1 rounded-full border border-rule2 text-[11px] text-muted hover:text-ink hover:border-[color:var(--color-accent)]">
                            {t}
                        </button>
                    ))}
                </div>

                {selected.length > 0 && (
                    <div className="mt-4 card p-3 flex flex-wrap items-center gap-2 sticky top-0 z-10">
                        <span className="text-sm text-ink">{selected.length} selected</span>
                        <select value={perVideo} onChange={(e) => setPerVideo(Number(e.target.value))} aria-label="shorts per video"
                            className="input-field !w-auto text-xs py-1.5">
                            {[2, 3, 4, 5].map((n) => <option key={n} value={n}>{n} Shorts per video</option>)}
                        </select>
                        <button onClick={runBatch} disabled={batchBusy} className="btn-primary px-3 py-1.5 text-xs">
                            {batchBusy ? <Loader2 size={13} className="animate-spin" /> : <Scissors size={13} />} make shorts from all
                        </button>
                        <button onClick={() => setSelected([])} className="btn-ghost px-2.5 py-1.5 text-xs">clear</button>
                    </div>
                )}
                {batchMsg && <p className="text-sm text-ok mt-4">{batchMsg}</p>}
                {error && <p className="text-sm text-danger mt-4" role="alert">{error}</p>}
                {results && results.length === 0 && !loading && (
                    <div className="card p-6 mt-6 text-sm text-muted text-center">No reuse-allowed videos for that search. Try other words or "any length".</div>
                )}

                {results && results.length > 0 && (
                    <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                        {results.map((v) => (
                            <div key={v.id} className="card overflow-hidden flex flex-col">
                                <a href={v.url} target="_blank" rel="noreferrer" className="relative block bg-black aspect-video">
                                    <img src={v.thumbnail} alt="" loading="lazy" className="absolute inset-0 w-full h-full object-cover" />
                                    {v.seconds && <span className="absolute bottom-1.5 right-1.5 readout bg-black/75 text-white px-1.5 rounded">{mmss(v.seconds)}</span>}
                                </a>
                                <div className="p-3 flex flex-col gap-2 flex-1">
                                    <p className="text-sm text-ink line-clamp-2 break-words" title={v.title}>{v.title}</p>
                                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
                                        <input type="checkbox" checked={selected.includes(v.url)} onChange={() => toggleSel(v.url)}
                                            aria-label={`select ${v.title}`} />
                                        <span className="truncate max-w-[55%]">{v.channel}</span>
                                        <span>{views(v.views)}</span>
                                        <span className="badge-brass">CC</span>
                                        {v.used?.count > 0 && <span className="badge-warn">{v.used.count} used</span>}
                                    </div>
                                    <div className="mt-auto pt-1 flex flex-wrap gap-2">
                                        <button onClick={() => onMakeShorts(v.url)} className="btn-primary px-3 py-1.5 text-[11px]">
                                            <Scissors size={13} /> make shorts
                                        </button>
                                        {v.channel_url && (
                                            <button onClick={() => addChannel(v)} disabled={added[v.channel_url]}
                                                className="btn-ghost px-3 py-1.5 text-[11px]" title="Autopilot will clip this channel's new videos">
                                                {added[v.channel_url] ? <><Check size={13} /> in autopilot</> : <><Rocket size={13} /> add channel to autopilot</>}
                                            </button>
                                        )}
                                        <a href={v.url} target="_blank" rel="noreferrer" className="btn-ghost px-2 py-1.5 text-[11px]" aria-label="open on YouTube">
                                            <ExternalLink size={13} />
                                        </a>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
