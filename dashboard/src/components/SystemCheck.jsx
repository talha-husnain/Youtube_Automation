import React, { useState } from 'react';
import { Loader2, Stethoscope, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';
import { apiJson } from '../lib/api';

// System check (GET /api/system-check, system_check.py): is the AI key,
// downloader, ffmpeg, disk, channel and Autopilot fine, in plain words.

const ICON = {
    ok: <CheckCircle2 size={15} className="text-ok shrink-0" />,
    warn: <AlertTriangle size={15} className="text-warn shrink-0" />,
    error: <XCircle size={15} className="text-danger shrink-0" />,
};

export default function SystemCheck() {
    const [rows, setRows] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const run = async () => {
        setBusy(true);
        setError('');
        try {
            setRows((await apiJson('/api/system-check')).checks);
        } catch (e) {
            setError(e.detail || 'The check could not run.');
        } finally {
            setBusy(false);
        }
    };
    const bad = (rows || []).filter((r) => r.status === 'error').length;
    return (
        <div className="card p-5 mb-6 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm text-ink flex items-center gap-1.5"><Stethoscope size={15} /> System check</p>
                <button onClick={run} disabled={busy} className="btn-primary px-3 py-1.5 text-xs">
                    {busy ? <Loader2 size={13} className="animate-spin" /> : null} {rows ? 'check again' : 'check everything'}
                </button>
            </div>
            {!rows && !busy && <p className="text-xs text-muted">When something fails, run this first: it says what is wrong and how to fix it.</p>}
            {error && <p className="text-xs text-danger">{error}</p>}
            {rows && (
                <>
                    <p className={`text-xs ${bad ? 'text-danger' : 'text-ok'}`}>{bad ? `${bad} problem(s) to fix.` : 'Everything needed is working.'}</p>
                    <div className="space-y-2">
                        {rows.map((r) => (
                            <div key={r.name} className="flex gap-2 text-xs">
                                {ICON[r.status]}
                                <div className="min-w-0">
                                    <p className="text-ink2"><span className="text-ink">{r.name}:</span> {r.detail}</p>
                                    {r.fix && r.status !== 'ok' && <p className="text-muted break-words">{r.fix}</p>}
                                </div>
                            </div>
                        ))}
                    </div>
                </>
            )}
        </div>
    );
}
