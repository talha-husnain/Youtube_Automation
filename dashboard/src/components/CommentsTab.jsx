import React, { useState } from 'react';
import { Loader2, MessageCircle, Copy, Check, ExternalLink, Send, EyeOff, CheckCircle2, ThumbsUp } from 'lucide-react';
import { apiJson } from '../lib/api';

// "Comments" (GET /api/comments, comment_replies.py): new comments on the
// latest Shorts, each with a reply drafted in the channel's voice. Copy it
// and reply on YouTube, or send it from here once the channel is connected.

function CommentCard({ c, canSend, onDone }) {
    const [text, setText] = useState(c.draft || '');
    const [copied, setCopied] = useState(false);
    const [busy, setBusy] = useState('');
    const [error, setError] = useState('');

    const act = async (action) => {
        setBusy(action);
        setError('');
        try {
            await apiJson(`/api/comments/${encodeURIComponent(c.id)}`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, text }),
            });
            onDone(c.id);
        } catch (e) {
            setError(e.detail || 'Could not do that.');
        } finally {
            setBusy('');
        }
    };

    return (
        <div className={`card p-4 space-y-2 ${c.skip ? 'opacity-60' : ''}`}>
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
                <span className="text-ink2">{c.author}</span>
                <span>{c.when}</span>
                {c.likes > 0 && <span className="inline-flex items-center gap-1"><ThumbsUp size={11} /> {c.likes}</span>}
                <span className="truncate min-w-0 flex-1">on: {c.video_title}</span>
            </div>
            <p className="text-sm text-ink break-words">{c.text}</p>
            {c.skip && <p className="text-[11px] text-warn">The AI thinks this one is spam or abuse: better to hide it.</p>}
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} aria-label="reply"
                className="input-field text-sm py-2" placeholder="your reply" />
            {error && <p className="text-[11px] text-danger">{error}</p>}
            <div className="flex flex-wrap gap-2">
                {canSend ? (
                    <button onClick={() => act('send')} disabled={!!busy || !text.trim()} className="btn-primary px-3 py-1.5 text-[11px]">
                        {busy === 'send' ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} send reply
                    </button>
                ) : (
                    <button onClick={async () => {
                        try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1400); } catch { /* ignore */ }
                    }} className="btn-primary px-3 py-1.5 text-[11px]">
                        {copied ? <Check size={13} /> : <Copy size={13} />} copy reply
                    </button>
                )}
                <a href={c.link} target="_blank" rel="noreferrer" className="btn-ghost px-3 py-1.5 text-[11px]"><ExternalLink size={13} /> open comment</a>
                <button onClick={() => act('answered')} disabled={!!busy} className="btn-ghost px-3 py-1.5 text-[11px]"><CheckCircle2 size={13} /> done</button>
                <button onClick={() => act('hidden')} disabled={!!busy} className="btn-ghost px-3 py-1.5 text-[11px]"><EyeOff size={13} /> hide</button>
            </div>
        </div>
    );
}

export default function CommentsTab() {
    const [handle, setHandle] = useState('');
    const [data, setData] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    const check = async () => {
        setBusy(true);
        setError('');
        try {
            const q = handle.trim() ? `?handle=${encodeURIComponent(handle.trim())}` : '';
            const d = await apiJson(`/api/comments${q}`);
            setData(d);
            if (!handle.trim()) setHandle(d.handle || '');
        } catch (e) {
            setError(e.detail || 'Could not read the comments.');
        } finally {
            setBusy(false);
        }
    };

    const drop = (id) => setData((d) => ({ ...d, comments: d.comments.filter((c) => c.id !== id) }));

    return (
        <div className="h-full overflow-y-auto p-4 sm:p-8 animate-fade">
            <div className="max-w-3xl mx-auto space-y-5">
                <div>
                    <p className="eyebrow mb-1.5">COMMENTS</p>
                    <h1 className="font-display lowercase text-2xl text-ink">reply to your viewers</h1>
                    <p className="text-xs text-muted mt-1 max-w-2xl leading-relaxed">
                        Reads the new comments on your latest 8 Shorts and writes a reply for each in your channel&apos;s style.
                        Replies keep people coming back, and YouTube shows Shorts with lively comments to more people.
                    </p>
                </div>
                <div className="flex flex-wrap gap-2">
                    <input value={handle} onChange={(e) => setHandle(e.target.value)} placeholder="@YourChannel (blank = your brand handle)"
                        className="input-field flex-1 min-w-[12rem] text-sm py-1.5" aria-label="channel handle" />
                    <button onClick={check} disabled={busy} className="btn-primary px-4 py-2 text-sm">
                        {busy ? <Loader2 size={15} className="animate-spin" /> : <MessageCircle size={15} />} check comments
                    </button>
                </div>
                {busy && <p className="text-xs text-muted">Reading comments… this takes about half a minute.</p>}
                {error && <p className="text-sm text-danger" role="alert">{error}</p>}
                {data && data.comments.length === 0 && (
                    <div className="card p-6 text-sm text-muted text-center">
                        No new comments on your latest {data.shorts_read} Shorts. The question at the end of each Short asks viewers to comment; pin a comment from Ready to post to start the talk.
                    </div>
                )}
                {data && data.comments.length > 0 && (
                    <div className="space-y-3">
                        <p className="readout">{data.comments.length} to answer{data.more ? ` (newest; ${data.more} older ones after these)` : ''} · {data.handle}</p>
                        {data.comments.map((c) => <CommentCard key={c.id} c={c} canSend={data.can_send} onDone={drop} />)}
                    </div>
                )}
            </div>
        </div>
    );
}
