import React from 'react';
import { Upload, ExternalLink } from 'lucide-react';

// The channel's last uploads (uploads.json rows from my_channels.summary):
// when each goes public, and whether its thumbnail and caption tracks went
// up, so a failed step is seen without opening YouTube Studio.
const when = (iso) => new Date(iso).toLocaleString(undefined, {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
});

const STEP = { set: 'done', failed: 'failed', skipped: 'skipped (API quota)' };

function state(r, now) {
    if (r.status === 'failed') return { text: `failed: ${r.error || 'no reason given'}`, warn: true };
    if (r.status === 'uploading') return { text: 'uploading now' };
    if (r.blocked) return { text: 'blocked by a copyright claim', warn: true };
    if (r.publish_at && new Date(r.publish_at).getTime() > now) return { text: `goes public ${when(r.publish_at)}` };
    if (r.views != null) {
        const kept = r.retention != null ? `, ${Math.round(r.retention)}% watched` : '';
        return { text: `${r.views.toLocaleString()} views${kept}` };
    }
    return { text: 'public' };
}

export default function RecentUploads({ ch }) {
    const rows = (ch.uploads || []).slice(0, 6);
    if (!rows.length) return null;
    const now = Date.now();
    return (
        <div className="rounded-input border border-rule p-3 space-y-2">
            <p className="text-xs text-ink2 flex items-center gap-1.5"><Upload size={13} /> Recent uploads</p>
            {rows.map((r) => {
                const s = state(r, now);
                const steps = [['thumbnail', r.thumbnail, r.thumbnail_error], ['captions', r.captions, r.captions_error],
                    ['English subtitles', r.captions_en, r.captions_en_error]].filter(([, v]) => v);
                return (
                    <div key={r.id} className="text-xs space-y-0.5">
                        <div className="flex items-start gap-2">
                            <span className="flex-1 min-w-0 break-words text-ink2">{r.title || r.file}</span>
                            {r.url && (
                                <a href={r.url} target="_blank" rel="noreferrer" aria-label={`open ${r.title} on YouTube`}
                                    className="text-muted hover:text-brass p-0.5 shrink-0"><ExternalLink size={12} /></a>
                            )}
                        </div>
                        <p className={`text-[11px] break-words ${s.warn ? 'text-warn' : 'text-muted'}`}>
                            {s.text}
                            {steps.map(([name, v, err]) => (
                                <span key={name} className={v === 'failed' ? 'text-warn' : ''}>
                                    {' · '}{name} {v === 'failed' && err ? `failed: ${err}` : STEP[v] || v}
                                </span>
                            ))}
                        </p>
                    </div>
                );
            })}
        </div>
    );
}
