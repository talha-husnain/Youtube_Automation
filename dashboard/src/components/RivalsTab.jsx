import React, { useEffect, useState } from 'react';
import { Loader2, Plus, X, Eye, Search, ExternalLink, Lightbulb } from 'lucide-react';
import { apiJson } from '../lib/api';

// "Similar channels" (GET/PUT /api/rivals, POST /api/rivals/scan, rivals.py):
// other comedy Shorts channels' latest Shorts by views, what the winners have
// in common, and ideas with a search that finds reusable videos for them.

const views = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}K` : `${n}`);

export default function RivalsTab({ onSearch }) {
    const [channels, setChannels] = useState([]);
    const [report, setReport] = useState(null);
    const [input, setInput] = useState('');
    const [busy, setBusy] = useState('');
    const [error, setError] = useState('');

    useEffect(() => {
        apiJson('/api/rivals').then((d) => { setChannels(d.channels || []); setReport(d.report); })
            .catch((e) => setError(e.detail || 'Could not load.'));
    }, []);

    const saveChannels = async (list) => {
        const d = await apiJson('/api/rivals', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ channels: list }),
        });
        setChannels(d.channels || []);
    };

    const add = async () => {
        const text = input.trim();
        if (!text) return;
        setBusy('add');
        setError('');
        try {
            const info = await apiJson(`/api/finder/channel?url=${encodeURIComponent(text)}`);
            if (!channels.some((c) => c.url === info.url)) await saveChannels([...channels, { url: info.url, name: info.name }]);
            setInput('');
        } catch (e) {
            setError(e.detail || 'Could not find that channel.');
        } finally {
            setBusy('');
        }
    };

    const scan = async () => {
        setBusy('scan');
        setError('');
        try {
            setReport((await apiJson('/api/rivals/scan', { method: 'POST' })).report);
        } catch (e) {
            setError(e.detail || 'Could not read those channels.');
        } finally {
            setBusy('');
        }
    };

    return (
        <div className="h-full overflow-y-auto p-4 sm:p-8 animate-fade">
            <div className="max-w-4xl mx-auto space-y-5">
                <div>
                    <p className="eyebrow mb-1.5">SIMILAR CHANNELS</p>
                    <h1 className="font-display lowercase text-2xl text-ink">what works for others</h1>
                    <p className="text-xs text-muted mt-1 max-w-2xl leading-relaxed">
                        Add channels like yours. Shortkaar reads their latest Shorts and views, says what the winners have in
                        common, and gives you ideas with a search that finds videos you may reuse. It never copies their Shorts.
                    </p>
                </div>
                {error && <p className="text-sm text-danger" role="alert">{error}</p>}

                <div className="card p-5 space-y-3">
                    <div className="flex flex-wrap gap-2">
                        {channels.map((c) => (
                            <span key={c.url} className="inline-flex items-center gap-1.5 pl-3 pr-1 py-1 rounded-full border border-rule2 text-xs text-ink2">
                                <a href={c.url} target="_blank" rel="noreferrer" className="hover:text-brass">{c.name || c.url}</a>
                                <button onClick={() => saveChannels(channels.filter((x) => x.url !== c.url))} aria-label={`remove ${c.name}`}
                                    className="p-0.5 text-muted hover:text-danger"><X size={13} /></button>
                            </span>
                        ))}
                        {channels.length === 0 && <span className="text-xs text-muted">No channel yet.</span>}
                    </div>
                    <form onSubmit={(e) => { e.preventDefault(); add(); }} className="flex flex-wrap gap-2">
                        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="channel link or @handle"
                            className="input-field flex-1 min-w-[12rem] text-sm py-1.5" aria-label="channel" />
                        <button type="submit" disabled={!input.trim() || busy === 'add'} className="btn-ghost px-3 py-1.5 text-xs">
                            {busy === 'add' ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} add
                        </button>
                        <button type="button" onClick={scan} disabled={!channels.length || !!busy} className="btn-primary px-4 py-1.5 text-xs">
                            {busy === 'scan' ? <Loader2 size={13} className="animate-spin" /> : <Eye size={13} />} {report ? 'check again' : 'check them'}
                        </button>
                    </form>
                    {busy === 'scan' && <p className="text-xs text-muted">Reading their Shorts… about half a minute.</p>}
                </div>

                {report && (
                    <>
                        {report.summary && (
                            <div className="card p-5 space-y-3">
                                <p className="readout">{report.count} Shorts read · {new Date(report.at * 1000).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</p>
                                <p className="text-sm text-ink2 leading-relaxed">{report.summary}</p>
                                <ul className="space-y-1.5 list-disc pl-5">
                                    {(report.patterns || []).map((p, i) => <li key={i} className="text-sm text-ink2">{p}</li>)}
                                </ul>
                            </div>
                        )}
                        {(report.ideas || []).length > 0 && (
                            <div className="card p-5 space-y-2">
                                <p className="text-sm text-ink flex items-center gap-1.5"><Lightbulb size={15} /> Ideas for your channel</p>
                                {report.ideas.map((x, i) => (
                                    <div key={i} className="flex flex-wrap items-center gap-2 text-sm">
                                        <span className="text-ink2 flex-1 min-w-0 break-words">{x.idea}</span>
                                        <button onClick={() => onSearch(x.search)} className="btn-ghost px-2.5 py-1 text-[11px]" title={`search: ${x.search}`}>
                                            <Search size={12} /> find videos
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                        <div className="card p-5">
                            <div className="flex flex-wrap gap-2 mb-3">
                                {(report.channels || []).map((c) => (
                                    <span key={c.channel} className="readout">{c.channel}: median {views(c.median)} · best {views(c.best)}</span>
                                ))}
                            </div>
                            <p className="eyebrow mb-1.5">their most viewed Shorts</p>
                            <div className="space-y-1">
                                {(report.top || []).slice(0, 25).map((r) => (
                                    <a key={r.id} href={r.url} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-xs py-0.5 hover:text-brass">
                                        <span className="readout w-14 text-right shrink-0">{views(r.views)}</span>
                                        <span className="text-muted shrink-0 max-w-[30%] truncate">{r.channel}</span>
                                        <span className="text-ink2 truncate min-w-0 flex-1">{r.title}</span>
                                        <ExternalLink size={11} className="shrink-0 text-muted" />
                                    </a>
                                ))}
                            </div>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
