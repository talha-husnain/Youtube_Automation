import React, { useEffect, useState } from 'react';
import { Loader2, Wand2, Copy, Check, Upload, Download } from 'lucide-react';
import { apiJson } from '../lib/api';
import { getApiUrl } from '../config';

// A new channel's launch kit (channel_kit.py): name ideas, About text,
// keywords, a banner and a profile picture, and one button that puts the
// text and banner on the connected YouTube channel.

function CopyBox({ text, label }) {
    const [copied, setCopied] = useState(false);
    return (
        <div className="relative">
            <p className="text-[11px] text-muted mb-1">{label}</p>
            <pre className="text-[11px] leading-relaxed text-ink2 bg-paper rounded-input border border-rule p-3 pr-10 whitespace-pre-wrap break-words max-h-48 overflow-auto">{text}</pre>
            <button onClick={async () => {
                try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1400); } catch { /* ignore */ }
            }} aria-label={`copy ${label}`} className="absolute top-6 right-2 p-1.5 text-muted hover:text-brass">
                {copied ? <Check size={14} className="text-ok" /> : <Copy size={14} />}
            </button>
        </div>
    );
}

export default function ChannelKit({ ch }) {
    const [kit, setKit] = useState(undefined);
    const [busy, setBusy] = useState('');
    const [note, setNote] = useState('');
    const [error, setError] = useState('');

    useEffect(() => {
        apiJson(`/api/my-channels/${ch.id}/kit`).then((d) => setKit(d.kit)).catch(() => setKit(null));
    }, [ch.id]);

    const make = async () => {
        setBusy('make'); setError(''); setNote('');
        try {
            const d = await apiJson(`/api/my-channels/${ch.id}/kit`, { method: 'POST' });
            setKit(d.kit);
        } catch (e) {
            setError(e.detail || 'Could not make the kit.');
        }
        setBusy('');
    };
    const apply = async () => {
        setBusy('apply'); setError(''); setNote('');
        try {
            const d = await apiJson(`/api/my-channels/${ch.id}/kit/apply`, { method: 'POST' });
            setNote(`Done on YouTube: ${d.set.join(', ')}. Still yours to do: ${d.left_for_you.join(', ')}.`);
        } catch (e) {
            setError(e.detail || 'YouTube did not take it.');
        }
        setBusy('');
    };

    if (kit === undefined) return null;
    return (
        <details className="rounded-input border border-rule p-3 space-y-3">
            <summary className="text-xs text-ink cursor-pointer select-none">
                Channel kit: name ideas, About text, keywords, banner and profile picture
            </summary>
            {!kit ? (
                <div className="space-y-2 pt-2">
                    <p className="text-xs text-ink2">Make everything the new channel's page needs, in its colour. Free except one small text call.</p>
                    <button onClick={make} disabled={busy === 'make'} className="btn-ghost px-3 py-1.5 text-xs">
                        {busy === 'make' ? <Loader2 size={13} className="animate-spin" /> : <Wand2 size={13} />} make channel kit
                    </button>
                </div>
            ) : (
                <div className="space-y-3 pt-2">
                    <div className="text-xs text-ink2 space-y-1">
                        <p><span className="text-muted">Name ideas:</span> {kit.names.join(' | ')}</p>
                        <p><span className="text-muted">Handle ideas:</span> {kit.handles.map((h) => `@${h}`).join(' | ')}</p>
                        <p><span className="text-muted">Tagline:</span> {kit.tagline}</p>
                    </div>
                    <CopyBox label="About text" text={kit.description} />
                    <CopyBox label="Keywords" text={kit.keywords.join(', ')} />
                    <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3 items-start">
                        <a href={getApiUrl(kit.banner)} target="_blank" rel="noreferrer" className="block">
                            <img src={getApiUrl(kit.banner)} alt="banner" className="w-full rounded-input border border-rule" />
                            <span className="text-[11px] text-brass inline-flex items-center gap-1 mt-1"><Download size={11} /> banner (2560x1440)</span>
                        </a>
                        <a href={getApiUrl(kit.profile)} target="_blank" rel="noreferrer" className="block">
                            <img src={getApiUrl(kit.profile)} alt="profile" className="h-24 w-24 rounded-full border border-rule" />
                            <span className="text-[11px] text-brass inline-flex items-center gap-1 mt-1"><Download size={11} /> profile picture</span>
                        </a>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <button onClick={apply} disabled={busy === 'apply' || !ch.youtube?.connected}
                            className="btn-ghost px-3 py-1.5 text-xs" title={ch.youtube?.connected ? '' : 'Connect the channel first'}>
                            {busy === 'apply' ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />} put About text, keywords and banner on YouTube
                        </button>
                        <button onClick={make} disabled={busy === 'make'} className="text-[11px] text-brass hover:underline">
                            {busy === 'make' ? 'making...' : 'make a new kit'}
                        </button>
                    </div>
                    {!ch.youtube?.connected && <p className="text-[11px] text-muted">Connect this channel first; the profile picture is always yours to upload (YouTube Studio, Customization, Branding).</p>}
                    {note && <p className="text-xs text-ok">{note}</p>}
                </div>
            )}
            {error && <p className="text-xs text-danger" role="alert">{error}</p>}
        </details>
    );
}
