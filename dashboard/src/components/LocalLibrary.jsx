import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, Download, FolderOpen, Film, Layers, RefreshCw } from 'lucide-react';
import { apiJson } from '../lib/api';
import { getApiUrl } from '../config';

// Shortkaar's History and Gallery on a local install: the finished jobs still
// on this machine (GET /api/library). The cloud tabs read the database and R2
// instead, which a local install does not have.

const when = (ts) => {
    const d = new Date(ts * 1000);
    return d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
};
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;

function ClipTile({ clip }) {
    return (
        <div className="card overflow-hidden flex flex-col">
            <div className="relative bg-black aspect-[9/16]">
                <video
                    src={getApiUrl(clip.video_url)}
                    controls
                    preload="metadata"
                    className="absolute inset-0 w-full h-full object-contain"
                />
            </div>
            <div className="p-3 flex flex-col gap-2 flex-1">
                <p className="text-xs text-ink2 line-clamp-2 break-words" title={clip.title}>{clip.title}</p>
                <div className="mt-auto flex items-center justify-between gap-2">
                    <span className="readout">{mmss(clip.seconds)}</span>
                    <a
                        href={getApiUrl(clip.video_url)}
                        download
                        className="btn-primary px-3 py-1.5 text-[11px]"
                    >
                        <Download size={13} /> download
                    </a>
                </div>
            </div>
        </div>
    );
}

export default function LocalLibrary({ mode = 'history', onOpenJob }) {
    const [data, setData] = useState(null);
    const [error, setError] = useState('');
    const [opening, setOpening] = useState(null);
    const [reload, setReload] = useState(0);

    useEffect(() => {
        let alive = true;
        setError('');
        apiJson('/api/library')
            .then((d) => { if (alive) setData(d); })
            .catch((e) => { if (alive) setError(e.message || 'Could not load your library.'); });
        return () => { alive = false; };
    }, [reload]);

    const allClips = useMemo(
        () => (data?.jobs || []).flatMap((j) => j.clips.map((c) => ({ ...c, job_id: j.job_id, key: `${j.job_id}-${c.index}` }))),
        [data],
    );
    const keptFor = data?.retention_seconds
        ? (data.retention_seconds >= 86400 ? `${Math.round(data.retention_seconds / 86400)} day(s)` : `${Math.round(data.retention_seconds / 3600)} hour(s)`)
        : null;

    const open = async (job) => {
        setOpening(job.job_id);
        try {
            await onOpenJob(job);
        } catch (e) {
            setError(e.message || 'Could not open that job.');
        } finally {
            setOpening(null);
        }
    };

    const isGallery = mode === 'gallery';
    return (
        <div className="h-full overflow-y-auto p-4 sm:p-8 animate-fade">
            <div className="max-w-6xl mx-auto">
                <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
                    <div>
                        <p className="eyebrow mb-1.5">{isGallery ? '03 · GALLERY' : '02 · HISTORY'}</p>
                        <h1 className="font-display lowercase text-2xl text-ink">{isGallery ? 'every short you made' : 'your jobs'}</h1>
                        {keptFor && (
                            <p className="text-xs text-muted mt-1">
                                Kept on this computer for {keptFor}, then deleted. Download the ones you want to keep.
                            </p>
                        )}
                    </div>
                    <button onClick={() => setReload((n) => n + 1)} className="btn-ghost px-3 py-2 text-xs">
                        <RefreshCw size={14} /> refresh
                    </button>
                </div>

                {error && <p className="text-sm text-danger mb-4" role="alert">{error}</p>}
                {!data && !error && (
                    <div className="flex items-center gap-2 text-sm text-muted"><Loader2 size={16} className="animate-spin" /> loading…</div>
                )}
                {data && data.jobs.length === 0 && (
                    <div className="card p-8 text-center text-sm text-muted">
                        <Film size={28} className="mx-auto mb-3 text-brass" />
                        Nothing here yet. Make your first shorts and they will show up here.
                    </div>
                )}

                {data && isGallery && allClips.length > 0 && (
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                        {allClips.map((c) => <ClipTile key={c.key} clip={c} />)}
                    </div>
                )}

                {data && !isGallery && data.jobs.length > 0 && (
                    <div className="space-y-4">
                        {data.jobs.map((job) => (
                            <div key={job.job_id} className="card p-4 sm:p-5">
                                <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                                    <div className="min-w-0">
                                        <p className="text-sm text-ink truncate">{job.clips[0]?.title}</p>
                                        <div className="flex flex-wrap items-center gap-2 mt-1">
                                            <span className="readout">{when(job.created)}</span>
                                            <span className="readout">{job.clips.length} {job.clips.length === 1 ? 'short' : 'shorts'}</span>
                                            {job.compilation && (
                                                <span className="badge-brass inline-flex items-center gap-1"><Layers size={11} /> compilation</span>
                                            )}
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => open(job)}
                                        disabled={opening === job.job_id}
                                        className="btn-primary px-4 py-2 text-xs"
                                    >
                                        {opening === job.job_id
                                            ? <><Loader2 size={14} className="animate-spin" /> opening…</>
                                            : <><FolderOpen size={14} /> open</>}
                                    </button>
                                </div>
                                <div className="flex gap-3 overflow-x-auto custom-scrollbar pb-1">
                                    {job.clips.map((c) => (
                                        <video
                                            key={c.index}
                                            src={getApiUrl(c.video_url)}
                                            preload="metadata"
                                            muted
                                            title={c.title}
                                            className="h-40 aspect-[9/16] rounded-input bg-black object-cover shrink-0 border border-rule"
                                        />
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
