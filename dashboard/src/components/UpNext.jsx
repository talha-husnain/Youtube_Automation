import React, { useState } from 'react';
import { ListOrdered, Plus, X, Loader2 } from 'lucide-react';
import { apiJson } from '../lib/api';

// What the channel makes next (my_channels ideas). The owner can put a topic
// first or drop one; a dropped topic goes on the avoid list for good.
export default function UpNext({ ch, onChanged }) {
    const [text, setText] = useState('');
    const [busy, setBusy] = useState('');
    const [error, setError] = useState('');
    if (!ch.plans_ideas) return null;

    const send = async (body, key) => {
        setBusy(key);
        setError('');
        try {
            await apiJson(`/api/my-channels/${ch.id}/ideas`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
            });
            if (body.add) setText('');
            await onChanged();
        } catch (e) {
            setError(e.detail || 'That did not work. Try again.');
        } finally {
            setBusy('');
        }
    };
    const next = ch.up_next || [];
    return (
        <div className="rounded-input border border-rule p-3 space-y-2">
            <p className="text-xs text-ink2 flex items-center gap-1.5"><ListOrdered size={13} /> Up next</p>
            {next.length === 0 && <p className="text-xs text-muted">New ideas are planned when the next video starts.</p>}
            {next.map((t, k) => (
                <div key={t} className="flex items-center gap-2 text-xs">
                    <span className="readout text-muted w-4 shrink-0">{k + 1}</span>
                    <span className="flex-1 min-w-0 break-words text-ink2">
                        {t}
                        {ch.up_next_series?.[k] && <span className="block text-[11px] text-brass">{ch.up_next_series[k]}</span>}
                    </span>
                    <button onClick={() => send({ drop: t }, t)} disabled={!!busy} aria-label={`drop ${t}`}
                        className="text-muted hover:text-warn p-1">
                        {busy === t ? <Loader2 size={12} className="animate-spin" /> : <X size={12} />}
                    </button>
                </div>
            ))}
            <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) send({ add: text }, 'add'); }}
                className="flex gap-2">
                <input value={text} onChange={(e) => setText(e.target.value)} maxLength={140}
                    placeholder={ch.kind === 'cricket' ? 'e.g. Babar Azam vs Virat Kohli' : 'your own topic, made next'}
                    className="input-field flex-1 min-w-0 text-xs py-1.5" aria-label="your own topic" />
                <button type="submit" disabled={!!busy || !text.trim()} className="btn-ghost px-3 py-1.5 text-xs">
                    {busy === 'add' ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} make next
                </button>
            </form>
            {error && <p className="text-xs text-warn">{error}</p>}
        </div>
    );
}
