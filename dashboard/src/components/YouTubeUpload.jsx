import React, { useEffect, useState } from 'react';
import { Loader2, Youtube, Check } from 'lucide-react';
import { apiJson } from '../lib/api';

// Upload one Short to the user's own channel (POST /api/youtube/upload,
// youtube_account.py): now, into the next free posting time, or at a time
// they pick. Hidden where the endpoint does not exist (cloud mode).

let statusOnce = null;
const ytStatus = () => {
    if (!statusOnce) statusOnce = apiJson('/api/youtube/status').catch(() => null);
    return statusOnce;
};

export default function YouTubeUpload({ jobId, index, title, description }) {
    const [yt, setYt] = useState(undefined);
    const [slot, setSlot] = useState(null);
    const [when, setWhen] = useState('slot');
    const [custom, setCustom] = useState('');
    const [busy, setBusy] = useState(false);
    const [done, setDone] = useState(null);
    const [error, setError] = useState('');

    useEffect(() => {
        let alive = true;
        ytStatus().then((s) => { if (alive) setYt(s); });
        apiJson('/api/youtube/slots?count=1').then((d) => { if (alive) setSlot(d.slots?.[0] || null); }).catch(() => {});
        return () => { alive = false; };
    }, []);

    if (yt === undefined || yt === null || !jobId) return null;
    if (!yt.connected) {
        return <p className="text-[11px] text-muted text-center">Connect YouTube in My channel to upload from here.</p>;
    }

    const upload = async () => {
        setBusy(true);
        setError('');
        try {
            const at = when === 'custom' ? custom : when;
            if (when === 'custom' && !custom) throw new Error('Pick a time first.');
            const d = await apiJson('/api/youtube/upload', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_id: jobId, clip_index: index, title, description, when: at }),
            });
            setDone(d.publish_at);
        } catch (e) {
            setError(e.detail || e.message || 'Upload failed.');
        } finally {
            setBusy(false);
        }
    };

    const fmt = (iso) => new Date(iso).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    if (done !== null) {
        return (
            <p className="text-xs text-ok text-center inline-flex items-center justify-center gap-1.5 w-full">
                <Check size={14} /> Uploading{done ? `, goes live ${fmt(done)}` : ''}. Follow it in My channel.
            </p>
        );
    }
    return (
        <div className="space-y-2 pt-1">
            <div className="flex flex-wrap items-center gap-2">
                <select value={when} onChange={(e) => setWhen(e.target.value)} className="input-field !w-auto flex-1 text-xs py-1.5" aria-label="when">
                    <option value="slot">{slot ? `next posting time: ${fmt(slot)}` : 'next posting time'}</option>
                    <option value="now">publish now</option>
                    <option value="custom">pick a time</option>
                </select>
                {when === 'custom' && (
                    <input type="datetime-local" value={custom} onChange={(e) => setCustom(e.target.value)} className="input-field !w-auto text-xs py-1.5" aria-label="time" />
                )}
            </div>
            <button onClick={upload} disabled={busy}
                className="w-full flex items-center justify-center gap-2 py-2 rounded-input bg-brass text-brassink text-xs lowercase hover:brightness-110 transition">
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Youtube size={14} />} upload to youtube
            </button>
            {error && <p className="text-[11px] text-danger">{error}</p>}
        </div>
    );
}
