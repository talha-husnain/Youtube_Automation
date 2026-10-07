import React, { useEffect, useState } from 'react';
import { Loader2, Youtube, BarChart3, RefreshCw, ExternalLink, Copy, Check, LogOut, Upload } from 'lucide-react';
import { apiJson } from '../lib/api';
import { getApiUrl } from '../config';

// "My channel": connect the user's own YouTube channel (youtube_account.py),
// the "what works" report (what_works.py) and the uploads Shortkaar made.

const AUDIT_FORM = 'https://support.google.com/youtube/contact/yt_api_form';
const SETUP_STEPS = `1. Open https://console.cloud.google.com and create a project named Shortkaar.
2. APIs & Services > Library: enable "YouTube Data API v3" and "YouTube Analytics API".
3. Google Auth Platform (OAuth consent screen): choose External, app name Shortkaar,
   your email. Under Audience, add your own Google account as a test user,
   then press "Publish app" so the sign-in does not expire every 7 days.
4. Clients > Create client > Web application.
   Authorized redirect URI: http://127.0.0.1:8000/api/youtube/callback
5. Put the client ID and secret in the .env file of Shortkaar:
   YT_CLIENT_ID=your-client-id
   YT_CLIENT_SECRET=your-client-secret
6. Restart Shortkaar, open My channel and press Connect.
   Google warns that the app is not verified: press Advanced, then Go to Shortkaar.`;

const when = (iso) => new Date(iso).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

export default function ChannelTab({ notice }) {
    const [yt, setYt] = useState(null);
    const [report, setReport] = useState(null);
    const [uploads, setUploads] = useState([]);
    const [busy, setBusy] = useState('');
    const [error, setError] = useState(notice?.error || '');
    const [copied, setCopied] = useState(false);
    const [handle, setHandle] = useState('@PunchlineBazaar');

    const load = () => {
        apiJson('/api/youtube/status').then(setYt).catch(() => setYt({ configured: false, connected: false }));
        apiJson('/api/report').then((d) => setReport(d.report)).catch(() => {});
        apiJson('/api/youtube/uploads').then((d) => setUploads(d.uploads || [])).catch(() => {});
    };
    useEffect(() => { load(); }, []);
    // Uploads run in the background: follow them while one is in flight.
    useEffect(() => {
        if (!uploads.some((u) => u.status === 'uploading')) return undefined;
        const t = setInterval(() => apiJson('/api/youtube/uploads').then((d) => setUploads(d.uploads || [])).catch(() => {}), 5000);
        return () => clearInterval(t);
    }, [uploads]);

    const build = async () => {
        setBusy('report');
        setError('');
        try {
            const d = await apiJson('/api/report/build', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ handle }),
            });
            setReport(d.report);
        } catch (e) {
            setError(e.detail || 'Could not build the report.');
        } finally {
            setBusy('');
        }
    };

    const setUse = async (use) => {
        const d = await apiJson('/api/report/use', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ use }),
        });
        setReport(d.report);
    };

    const disconnect = async () => {
        setBusy('disconnect');
        await apiJson('/api/youtube/disconnect', { method: 'POST' }).catch(() => {});
        setBusy('');
        load();
    };

    const copySteps = async () => {
        try { await navigator.clipboard.writeText(SETUP_STEPS); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* ignore */ }
    };

    return (
        <div className="h-full overflow-y-auto p-4 sm:p-8 animate-fade">
            <div className="max-w-4xl mx-auto space-y-5">
                <div>
                    <p className="eyebrow mb-1.5">MY CHANNEL</p>
                    <h1 className="font-display lowercase text-2xl text-ink">your channel, uploads and what works</h1>
                </div>
                {notice?.connected && <p className="text-sm text-ok">YouTube is connected.</p>}
                {error && <p className="text-sm text-danger" role="alert">{error}</p>}

                {/* Connection */}
                <div className="card p-5 space-y-3">
                    <p className="text-sm text-ink flex items-center gap-1.5"><Youtube size={15} /> YouTube connection</p>
                    {!yt && <Loader2 size={16} className="animate-spin text-muted" />}
                    {yt && yt.connected && yt.channel && (
                        <div className="flex flex-wrap items-center gap-3">
                            {yt.channel.thumbnail && <img src={yt.channel.thumbnail} alt="" className="h-10 w-10 rounded-full" />}
                            <div className="flex-1 min-w-0">
                                <p className="text-sm text-ink">{yt.channel.title} <span className="text-muted">{yt.channel.handle}</span></p>
                                <p className="text-xs text-muted">{yt.channel.subscribers} subscribers · connected</p>
                            </div>
                            <button onClick={disconnect} disabled={busy === 'disconnect'} className="btn-ghost px-3 py-1.5 text-xs">
                                <LogOut size={13} /> disconnect
                            </button>
                        </div>
                    )}
                    {yt && yt.configured && !yt.connected && (
                        <a href={getApiUrl(`/api/youtube/connect?back=${encodeURIComponent(window.location.origin)}`)} className="btn-primary px-4 py-2 text-sm inline-flex">
                            <Youtube size={15} /> connect youtube
                        </a>
                    )}
                    {yt && !yt.configured && (
                        <div className="space-y-2">
                            <p className="text-xs text-muted leading-relaxed">
                                One-time setup, about 10 minutes. It uses a free Google project that only you own, so Shortkaar never sees your password.
                            </p>
                            <div className="relative">
                                <pre className="text-[11px] leading-relaxed text-ink2 bg-paper rounded-input border border-rule p-3 pr-10 whitespace-pre-wrap break-words">{SETUP_STEPS}</pre>
                                <button onClick={copySteps} aria-label="copy steps" className="absolute top-2 right-2 p-1.5 text-muted hover:text-brass">
                                    {copied ? <Check size={14} className="text-ok" /> : <Copy size={14} />}
                                </button>
                            </div>
                        </div>
                    )}
                    <p className="text-[11px] text-warn leading-relaxed">
                        YouTube keeps every video uploaded from your own Google project private until that project passes YouTube&apos;s API audit.
                        Fill in the <a href={AUDIT_FORM} target="_blank" rel="noreferrer" className="underline">audit form</a> once (free, can take a few weeks).
                        Until then, upload from the YouTube app; the report below works now.
                    </p>
                </div>

                {/* What works */}
                <div className="card p-5 space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="text-sm text-ink flex items-center gap-1.5"><BarChart3 size={15} /> What works on your channel</p>
                        <div className="flex items-center gap-2">
                            {!yt?.connected && (
                                <input value={handle} onChange={(e) => setHandle(e.target.value)} aria-label="channel handle"
                                    className="input-field !w-44 text-xs py-1.5" />
                            )}
                            <button onClick={build} disabled={busy === 'report'} className="btn-primary px-3 py-1.5 text-xs">
                                {busy === 'report' ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                                {report ? 'update report' : 'build report'}
                            </button>
                        </div>
                    </div>
                    {!report && <p className="text-xs text-muted">Reads your Shorts and their numbers, then shows what the winners have in common. The title rules it finds are used for your next titles.</p>}
                    {report && report.enough === false && (
                        <p className="text-xs text-muted">Only {report.count} Shorts with numbers so far. Post at least 5, then update the report.</p>
                    )}
                    {report && report.enough && (
                        <>
                            <p className="readout whitespace-normal break-words">{report.count} Shorts · {report.total_views} views · median {report.median_views} · from {report.source} · {new Date(report.at * 1000).toLocaleDateString()}</p>
                            <p className="text-sm text-ink2 leading-relaxed">{report.summary}</p>
                            <ul className="space-y-2">
                                {(report.lessons || []).map((l, i) => (
                                    <li key={i} className="text-sm text-ink2 leading-relaxed">
                                        {l.text}
                                        <span className="block text-[11px] text-muted break-words">{l.evidence}</span>
                                    </li>
                                ))}
                            </ul>
                            <div className="grid sm:grid-cols-3 gap-4">
                                {[['Title rules for the AI', report.title_rules], ['Make more of', report.do_more], ['Stop doing', report.avoid]].map(([label, items]) => (
                                    <div key={label} className="min-w-0">
                                        <p className="eyebrow mb-1.5">{label}</p>
                                        <ul className="space-y-1">{(items || []).map((x, i) => <li key={i} className="text-xs text-ink2">{x}</li>)}</ul>
                                    </div>
                                ))}
                            </div>
                            <label className="flex items-center gap-2 text-xs text-ink2">
                                <input type="checkbox" checked={report.use !== false} onChange={(e) => setUse(e.target.checked)} />
                                use these title rules when writing new titles
                            </label>
                            <div className="grid sm:grid-cols-2 gap-4">
                                {[['Best', report.top], ['Weakest', report.bottom]].map(([label, rows]) => (
                                    <div key={label} className="min-w-0">
                                        <p className="eyebrow mb-1.5">{label}</p>
                                        {(rows || []).map((r) => (
                                            <a key={r.id} href={`https://youtube.com/shorts/${r.id}`} target="_blank" rel="noreferrer"
                                                className="flex items-center gap-2 text-xs py-0.5 hover:text-brass">
                                                <span className="readout w-14 shrink-0 text-right">{r.views}</span>
                                                <span className="truncate min-w-0 flex-1 text-ink2">{r.title}</span>
                                                {r.avg_percent != null && <span className="text-muted shrink-0">{r.avg_percent}%</span>}
                                            </a>
                                        ))}
                                    </div>
                                ))}
                            </div>
                        </>
                    )}
                </div>

                {/* Uploads */}
                <div className="card p-5">
                    <p className="text-sm text-ink flex items-center gap-1.5 mb-3"><Upload size={15} /> Uploads from Shortkaar</p>
                    {uploads.length === 0 && <p className="text-xs text-muted">None yet. Use the upload button under a Short (copy panel), or Autopilot&apos;s auto upload.</p>}
                    <div className="space-y-1.5">
                        {uploads.map((u) => (
                            <div key={u.id} className="flex flex-wrap items-center gap-2 text-xs">
                                <span className={`shrink-0 ${u.status === 'failed' ? 'text-danger' : u.status === 'done' ? 'text-ok' : 'text-muted'}`}>
                                    {u.status === 'uploading' ? <Loader2 size={12} className="animate-spin inline" /> : u.status}
                                </span>
                                <span className="text-ink2 truncate flex-1 min-w-[40%]">{u.title}</span>
                                <span className="text-muted shrink-0">{u.publish_at ? `goes live ${when(u.publish_at)}` : 'now'}</span>
                                {u.url && <a href={u.url} target="_blank" rel="noreferrer" className="text-muted hover:text-brass"><ExternalLink size={12} /></a>}
                                {u.locked_private && <span className="badge-warn">kept private: audit needed</span>}
                                {u.error && <span className="block w-full text-[11px] text-danger">{u.error}</span>}
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
