import React, { useEffect, useState } from 'react';
import { Loader2, Smartphone, Copy, Check } from 'lucide-react';
import { apiJson } from '../lib/api';

// Phone delivery through the owner's own Telegram bot (telegram_notify.py):
// each Short arrives on the phone with its time, title and copy to paste.

const STEPS = `1. In Telegram, open @BotFather and send: /newbot
2. Give it any name, then a username ending in "bot". BotFather replies with a token.
3. Put the token in the .env file of Shortkaar:
   TELEGRAM_BOT_TOKEN=paste-the-token-here
4. Restart Shortkaar, open your new bot in Telegram and send it: hi
5. Press Connect below.`;

export default function TelegramCard() {
    const [st, setSt] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [copied, setCopied] = useState(false);

    useEffect(() => { apiJson('/api/telegram/status').then(setSt).catch(() => setSt(null)); }, []);

    const act = async (path) => {
        setBusy(true);
        setError('');
        try {
            setSt(await apiJson(path, { method: 'POST' }));
        } catch (e) {
            setError(e.detail || 'That did not work.');
        } finally {
            setBusy(false);
        }
    };

    if (!st) return null;
    return (
        <div className="card p-5 space-y-3">
            <p className="text-sm text-ink flex items-center gap-1.5"><Smartphone size={15} /> Shorts on your phone (Telegram)</p>
            <p className="text-xs text-muted leading-relaxed">
                Each Short arrives in Telegram with its posting time, title, description and pinned comment, ready to save and post from the YouTube app.
            </p>
            {st.connected && (
                <div className="flex flex-wrap items-center gap-3">
                    <p className="text-xs text-ok flex-1">Connected to {st.name}. Use &quot;send to phone&quot; in Ready to post, or switch it on in Autopilot.</p>
                    <button onClick={() => act('/api/telegram/disconnect')} disabled={busy} className="btn-ghost px-3 py-1.5 text-xs">disconnect</button>
                </div>
            )}
            {!st.connected && (
                <>
                    <div className="relative">
                        <pre className="text-[11px] leading-relaxed text-ink2 bg-paper rounded-input border border-rule p-3 pr-10 whitespace-pre-wrap break-words">{STEPS}</pre>
                        <button onClick={async () => {
                            try { await navigator.clipboard.writeText(STEPS); setCopied(true); setTimeout(() => setCopied(false), 1400); } catch { /* ignore */ }
                        }} aria-label="copy steps" className="absolute top-2 right-2 p-1.5 text-muted hover:text-brass">
                            {copied ? <Check size={14} className="text-ok" /> : <Copy size={14} />}
                        </button>
                    </div>
                    <button onClick={() => act('/api/telegram/connect')} disabled={busy || !st.configured} className="btn-primary px-4 py-2 text-sm">
                        {busy ? <Loader2 size={15} className="animate-spin" /> : <Smartphone size={15} />} connect
                    </button>
                    {!st.configured && <p className="text-[11px] text-muted">The Connect button works once the token is in .env and Shortkaar was restarted.</p>}
                </>
            )}
            {error && <p className="text-[11px] text-danger">{error}</p>}
        </div>
    );
}
