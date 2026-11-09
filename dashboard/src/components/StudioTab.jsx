import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    Clapperboard, Scissors, Check, SkipForward, RotateCcw, Save, Loader2, AlertTriangle, ExternalLink,
    RefreshCw, Type, Eye, Sparkles, Upload, Undo2, History, Send,
} from 'lucide-react';
import { getApiUrl } from '../config';
import { apiJson } from '../lib/api';

// Studio (studio.py): open a channel's finished video (or upload your own), say what to change and the AI
// editor does it (ai_editor.py), or fix the title, captions or length by hand, and approve, skip or remake
// it before it goes up. Edits are made on the server with ffmpeg; the player reloads the new file when done.

const STATES = ['all', 'held for review', 'waiting', 'uploaded', 'failed', 'skipped', 'your upload'];
// One tap for the requests owners make most (captions, pauses, zoom, music, look, title: research, 29-oct-2026).
const SUGGESTIONS = ['Remove the long pauses', 'Bigger yellow captions', 'Zoom in on the key moment',
    'Slow motion on the funniest moment', 'Blur the logo / watermark', 'Bleep the bad words',
    'Whoosh at the start, ding on the punchline', 'Laughing emoji on the funny part', 'Clean up the audio',
    'Fade out at the end', 'Sad piano music under it', 'Darker, cinematic look', 'Write a better title',
    'Translate the captions to English', 'Undo the last edit'];
const REMAKE_SUGGESTION = 'Make the hook stronger and make it again';
const LIVE_SUGGESTIONS = ['Write a better title', 'Write a better description'];
const postJson = (path, body) => apiJson(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}),
});
const TITLE_MAX = 100;
const DESCRIPTION_MAX = 5000;
const bytes = (s) => new TextEncoder().encode(s || '').length;
// Live checks on the copy, by the rules seo_copy and the title tournament follow: a title reads whole on a
// phone at 25-70 characters, YouTube ignores every hashtag of a description with more than 15, and tags
// hold 500 characters, a tag with a space counting its quotes.
const copyChecks = (title, description, tags) => {
    const t = title.trim();
    const shouting = (t.match(/[A-Za-z]+/g) || []).some((w) => w.length > 4 && w === w.toUpperCase());
    const words = (description.match(/\S+/g) || []).length;
    const hashtags = (description.match(/#[\p{L}\p{N}_]+/gu) || []).length;
    const tagList = tags.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);
    const tagChars = tagList.reduce((n, x) => n + x.length + (x.includes(' ') ? 2 : 0), 0) + Math.max(0, tagList.length - 1);
    return [
        { ok: t.length >= 25 && t.length <= 70, text: `title ${t.length} characters (25-70 reads whole on a phone)` },
        { ok: !shouting, text: shouting ? 'a word in the title is shouting in capitals' : 'no shouting words in the title' },
        { ok: words >= 150, text: `description ${words} words (150+ helps search)` },
        { ok: hashtags <= 15, text: hashtags > 15 ? `${hashtags} hashtags: past 15 YouTube ignores them all`
            : `${hashtags} hashtag${hashtags === 1 ? '' : 's'} (the first 3 show above the title)` },
        { ok: tagChars <= 500, text: `tags ${tagChars}/500 characters` },
    ];
};
const clock = (t) => {
    if (!Number.isFinite(t)) return '0:00.0';
    const m = Math.floor(t / 60);
    return `${m}:${(t - m * 60).toFixed(1).padStart(4, '0')}`;
};
const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString(undefined, {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
}) : '');

function StateBadge({ state }) {
    const tone = state === 'failed' ? 'text-warn border-warn/40'
        : state === 'held for review' ? 'text-brass border-brass/40'
            : state === 'uploaded' ? 'text-ok border-ok/40' : 'text-muted border-rule';
    return <span className={`text-[10px] uppercase tracking-wide border rounded px-1.5 py-0.5 ${tone}`}>{state}</span>;
}

function Panel({ icon, title, children, aside }) {
    return (
        <section className="rounded-input border border-rule p-3 space-y-2 min-w-0">
            <div className="flex items-center gap-2">
                {React.createElement(icon, { size: 14, className: 'text-brass shrink-0' })}
                <h3 className="text-sm text-ink flex-1">{title}</h3>
                {aside}
            </div>
            {children}
        </section>
    );
}

// An uploaded video's own numbers from YouTube (yt_insights via /insights): the retention curve, where viewers
// left (with what was said there; click to jump), and the search words that found it (click to add as a tag).
function YouTubeNumbers({ jobId, addTag, player }) {
    const [data, setData] = useState(null);
    const [error, setError] = useState('');
    useEffect(() => {
        let live = true;
        setData(null);
        setError('');
        apiJson(`/api/studio/video/${jobId}/insights`).then((d) => live && setData(d))
            .catch((e) => live && setError(e.detail || 'YouTube did not answer.'));
        return () => { live = false; };
    }, [jobId]);
    if (error) return <Panel icon={Eye} title="On YouTube"><p className="text-xs text-muted">{error}</p></Panel>;
    if (!data || !data.on_youtube) return null;
    const curve = data.curve;
    const pts = curve?.points || [];
    const maxT = pts.length ? pts[pts.length - 1][0] || 1 : 1;
    const maxY = Math.max(100, ...pts.map((p) => p[1]));
    const line = pts.map(([t, y]) => `${(t / maxT) * 300},${80 - (y / maxY) * 76}`).join(' ');
    const jump = (t) => { if (player.current) { player.current.currentTime = t; player.current.play(); } };
    return (
        <Panel icon={Eye} title="On YouTube: where viewers leave" aside={
            <span className="text-[11px] text-muted readout">
                {data.views != null && `${data.views.toLocaleString()} views`}
                {data.retention != null && ` · ${data.retention}% watched`}
                {data.ctr != null && ` · ${data.ctr}% clicked the thumbnail`}
            </span>}>
            {pts.length > 1 ? (
                <>
                    <svg viewBox="0 0 300 82" className="w-full h-20 bg-paper2 rounded-input" preserveAspectRatio="none" aria-label="retention curve">
                        <polyline points={line} fill="none" stroke="currentColor" strokeWidth="1.5" className="text-brass" />
                        {(curve.drops || []).map((d, i) => (
                            <line key={i} x1={(d.at / maxT) * 300} x2={(d.at / maxT) * 300} y1="0" y2="82" stroke="currentColor" className="text-warn" strokeDasharray="2 2" />
                        ))}
                    </svg>
                    <p className="text-[11px] text-muted">
                        {curve.half_at != null ? `Half the viewers were gone by ${clock(curve.half_at)}. ` : ''}
                        {curve.vs_others != null && `Compared with YouTube videos of its length: ${curve.vs_others >= 0.5 ? 'better' : 'worse'} than usual (${curve.vs_others}).`}
                    </p>
                    {(curve.drops || []).map((d, i) => (
                        <button key={i} onClick={() => jump(d.at)} className="block text-left text-xs text-ink2 hover:text-brass">
                            <span className="readout text-warn">{clock(d.at)}-{clock(d.to)}</span> {d.lost}% left
                            {d.said && <span className="text-muted"> while it said &quot;{d.said}&quot;</span>}
                        </button>
                    ))}
                </>
            ) : (
                <p className="text-xs text-muted">YouTube shows the retention curve once a video has a few dozen views; Shortkaar reads it every few hours.</p>
            )}
            {data.search?.length > 0 && (
                <div className="space-y-1">
                    <p className="text-[11px] text-muted">People found it by searching (click to add as a tag):</p>
                    <div className="flex flex-wrap gap-1.5">
                        {data.search.map(([term, views]) => (
                            <button key={term} onClick={() => addTag(term)} className="text-[11px] rounded-full border border-rule px-2 py-0.5 text-ink2 hover:border-brass">
                                {term} <span className="text-muted">{views}</span>
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </Panel>
    );
}

// The AI editor: the owner types what to change, the server plans it, makes it and checks it; every edit
// is a version, and any version (or the original) can be put back.
function AiEditPanel({ detail, onChanged }) {
    const jobId = detail.job_id;
    const [prompt, setPrompt] = useState('');
    const [st, setSt] = useState(null);
    const [err, setErr] = useState('');
    const [sending, setSending] = useState(false);
    const [ideas, setIdeas] = useState(null);       // the AI's own suggestions for this video
    const [thinking, setThinking] = useState(false);
    const box = useRef(null);

    const suggest = async () => {
        setThinking(true);
        setErr('');
        try {
            const s = await postJson(`/api/studio/ai/${jobId}/suggest`);
            setIdeas(s.items || []);
        } catch (e) {
            setErr(e.detail || 'No suggestions right now.');
        } finally {
            setThinking(false);
        }
    };

    const load = useCallback(async () => {
        try {
            const s = await apiJson(`/api/studio/ai/${jobId}`);
            setSt(s);
            return s;
        } catch (e) {
            setErr(e.detail || 'Could not read the AI editor.');
            return null;
        }
    }, [jobId]);

    useEffect(() => { setSt(null); setPrompt(''); setErr(''); setIdeas(null); load(); }, [load]);

    // While an edit runs, ask every 2 s; when it ends the video and its details reload.
    useEffect(() => {
        if (!st?.running) return undefined;
        const t = setInterval(async () => {
            const s = await load();
            if (s && !s.running) onChanged();
        }, 2000);
        return () => clearInterval(t);
    }, [st?.running, load, onChanged]);

    const send = async (text) => {
        const words = (text ?? prompt).trim();
        if (!words || sending || st?.running) return;
        setSending(true);
        setErr('');
        try {
            await postJson(`/api/studio/ai/${jobId}`, { prompt: words });
            setPrompt('');
            await load();
        } catch (e) {
            setErr(e.detail || 'The edit could not start.');
        } finally {
            setSending(false);
        }
    };

    const restore = async (n) => {
        setSending(true);
        setErr('');
        try {
            setSt(await postJson(`/api/studio/ai/${jobId}/restore`, { n }));
            onChanged();
        } catch (e) {
            setErr(e.detail || 'Could not go back to that version.');
        } finally {
            setSending(false);
        }
    };

    const live = detail.state === 'uploaded';
    const remakable = !detail.upload && !detail.main && (detail.state === 'waiting' || detail.state === 'held for review');
    const chips = live ? LIVE_SUGGESTIONS : [...SUGGESTIONS, ...(remakable ? [REMAKE_SUGGESTION] : [])];
    const running = !!st?.running;
    const result = st?.result;
    const revisions = st?.revisions || [];
    const current = st?.current || 0;
    const ask = (text) => { setPrompt(text); setTimeout(() => box.current?.focus(), 0); };

    return (
        <Panel icon={Sparkles} title="Tell the AI what to change" aside={revisions.length > 0 && (
            <span className="text-[11px] text-muted readout">version {current} of {revisions.length}</span>)}>
            {detail.state === 'transcribing' && (
                <p className="text-xs text-muted">Reading the words of your video... cuts by time work already;
                    edits by what is said work in a minute.</p>
            )}
            {live && (
                <p className="text-xs text-muted">This video is on YouTube: the AI can change its title, description and
                    tags (and send them to YouTube), not the video file.</p>
            )}
            <div className="flex gap-2">
                <textarea ref={box} value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={2}
                    disabled={running}
                    onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) send(); }}
                    placeholder="e.g. pehle 2 second kaat do, captions peele aur bade kar do"
                    className="flex-1 min-w-0 bg-paper2 border border-rule rounded-input px-2 py-1.5 text-xs text-ink2 custom-scrollbar" />
                <button onClick={() => send()} disabled={running || sending || !prompt.trim()}
                    title="Do it (Ctrl+Enter)"
                    className="btn-primary px-3 text-xs inline-flex items-center gap-1.5 self-stretch">
                    {sending ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} do it
                </button>
            </div>
            {!running && (
                <div className="space-y-1.5">
                    <button onClick={suggest} disabled={thinking}
                        title="The AI watches the video and proposes the edits that would help most"
                        className="text-[11px] rounded-input border border-brass/60 px-2 py-0.5 text-brass hover:border-brass inline-flex items-center gap-1">
                        {thinking ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
                        {thinking ? 'Watching the video...' : 'Suggest edits for this video'}
                    </button>
                    {ideas && ideas.length === 0 && (
                        <p className="text-[11px] text-muted">The AI has nothing to suggest: this one looks ready.</p>
                    )}
                    {ideas && ideas.length > 0 && (
                        <div className="flex flex-col gap-1">
                            {ideas.map((s) => (
                                <button key={s.text} onClick={() => ask(s.text)} title={s.why}
                                    className="text-left text-[11px] rounded-input border border-rule2 px-2 py-1 text-ink2 hover:border-brass">
                                    {s.text}{s.why && <span className="text-muted"> - {s.why}</span>}
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            )}
            {!running && (
                <div className="flex flex-wrap gap-1.5">
                    {chips.map((c) => (
                        <button key={c} onClick={() => ask(c)}
                            className="text-[11px] rounded-input border border-rule px-2 py-0.5 text-muted hover:text-ink2 hover:border-rule2">
                            {c}
                        </button>
                    ))}
                </div>
            )}
            {running && (
                <p className="text-xs text-brass inline-flex items-center gap-1.5">
                    <Loader2 size={13} className="animate-spin" /> {st?.stage || 'Working'}...
                    <span className="text-muted">(about a minute for a Short)</span>
                </p>
            )}
            {err && <p className="text-xs text-warn break-words">{err}</p>}
            {!running && result && (
                <div className="space-y-1 text-xs border-t border-rule pt-2">
                    {result.prompt && <p className="text-muted break-words">You asked: {result.prompt}</p>}
                    {result.ok ? (
                        <>
                            <p className="text-ink2 break-words inline-flex gap-1.5"><Check size={13} className="text-ok shrink-0 mt-0.5" />
                                <span>{result.summary}</span></p>
                            {(result.assumptions || []).map((a, i) => (
                                <p key={`a${i}`} className="text-muted break-words">Assumed: {a}</p>))}
                            {[result.why_not, ...(result.notes || [])].filter(Boolean).map((n, i) => (
                                <p key={`n${i}`} className="text-warn break-words">{n}</p>))}
                            {result.check?.done === true && <p className="text-ok">Checked on the frames: the change shows.</p>}
                            {(result.check?.problems || []).map((p, i) => (
                                <p key={`p${i}`} className="text-warn break-words flex gap-1.5">
                                    <AlertTriangle size={12} className="shrink-0 mt-0.5" /><span>{p}</span></p>))}
                            {(result.actions || []).map((a, i) => <p key={`x${i}`} className="text-ok break-words">Also: {a}.</p>)}
                        </>
                    ) : (
                        <p className={`break-words ${result.question ? 'text-brass' : 'text-warn'}`}>
                            {result.question ? 'The AI asks: ' : ''}{result.message}</p>
                    )}
                </div>
            )}
            {revisions.length > 0 && (
                <div className="space-y-1 border-t border-rule pt-2">
                    <div className="flex items-center gap-2 text-[11px] text-muted">
                        <History size={12} /> <span className="flex-1">Versions (click one to put it back)</span>
                        {current > 0 && (
                            <button disabled={running || sending} onClick={() => restore(current - 1)}
                                className="btn-ghost px-2 py-0.5 text-[11px] inline-flex items-center gap-1">
                                <Undo2 size={12} /> undo
                            </button>
                        )}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                        {[{ n: 0, prompt: 'Original' }, ...revisions].map((r) => (
                            <button key={r.n} disabled={running || sending || r.n === current} onClick={() => restore(r.n)}
                                title={r.n ? `${r.prompt}\n${r.summary || ''}` : 'The video before any AI edit'}
                                className={`text-[11px] rounded-input border px-2 py-0.5 max-w-[14rem] truncate ${r.n === current ? 'border-brass text-brass' : 'border-rule text-muted hover:text-ink2'}`}>
                                {r.n ? `${r.n} · ${r.prompt}` : r.prompt}
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </Panel>
    );
}

export default function StudioTab() {
    const [videos, setVideos] = useState([]);
    const [listError, setListError] = useState('');
    const [loading, setLoading] = useState(true);
    const [channel, setChannel] = useState('all');
    const [state, setState] = useState('all');
    const [selected, setSelected] = useState(null);
    const [detail, setDetail] = useState(null);
    const [version, setVersion] = useState(0);
    const [busy, setBusy] = useState('');
    const [note, setNote] = useState({ text: '', bad: false });
    const [title, setTitle] = useState('');
    const [description, setDescription] = useState('');
    const [tags, setTags] = useState('');
    const [push, setPush] = useState(false);
    const [captions, setCaptions] = useState([]);
    const [trim, setTrim] = useState({ start: 0, end: 0 });
    const [uploading, setUploading] = useState(false);
    const [titleIdeas, setTitleIdeas] = useState(null);
    const [ideasBusy, setIdeasBusy] = useState(false);
    const player = useRef(null);
    const editor = useRef(null);
    const fileInput = useRef(null);
    // On a phone the editor sits under the list: picking a video brings it into view.
    const pick = (jobId) => {
        setSelected(jobId);
        if (window.innerWidth < 1024) setTimeout(() => editor.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 300);
    };

    const loadList = useCallback(async () => {
        setLoading(true);
        try {
            const r = await apiJson('/api/studio/videos');
            setVideos(r.videos || []);
            setListError('');
        } catch (e) {
            setListError(e.detail || 'Could not load the videos.');
        } finally {
            setLoading(false);
        }
    }, []);

    const loadDetail = useCallback(async (jobId) => {
        if (!jobId) return;
        try {
            const d = await apiJson(`/api/studio/video/${jobId}`);
            setDetail(d);
            setTitle(d.title || '');
            setDescription(d.description || '');
            setTags((d.tags || []).join(', '));
            setPush(false);
            setCaptions((d.captions || []).map((c) => c.text));
            setTrim({ start: 0, end: d.seconds || 0 });
        } catch (e) {
            setDetail(null);
            setNote({ text: e.detail || 'Could not open that video.', bad: true });
        }
    }, []);

    useEffect(() => { loadList(); }, [loadList]);
    useEffect(() => { setNote({ text: '', bad: false }); setTitleIdeas(null); loadDetail(selected); }, [selected, loadDetail]);

    // Other title angles (each checked: no number or name the video does not have) and YouTube's own search
    // suggestions for the topic. Nothing is saved until the owner picks one and presses save.
    const askTitles = async () => {
        setIdeasBusy(true);
        setNote({ text: '', bad: false });
        try {
            setTitleIdeas(await postJson(`/api/studio/video/${selected}/titles`, {}));
        } catch (e) {
            setNote({ text: e.detail || 'No title ideas this time. Try again in a minute.', bad: true });
        } finally {
            setIdeasBusy(false);
        }
    };
    const addTag = (phrase) => setTags((tg) => {
        const have = tg.split(/[,\n]/).map((x) => x.trim().toLowerCase());
        if (have.includes(phrase.toLowerCase())) return tg;
        return tg.trim() ? `${tg.trim().replace(/,$/, '')}, ${phrase}` : phrase;
    });
    const checks = useMemo(() => copyChecks(title, description, tags), [title, description, tags]);

    // After an AI edit or an undo: the new file, its details and the list.
    const onAiChanged = useCallback(async () => {
        await loadDetail(selected);
        await loadList();
        setVersion((v) => v + 1);
    }, [selected, loadDetail, loadList]);

    // An upload's words are read in the background: look again until they are there.
    useEffect(() => {
        if (detail?.state !== 'transcribing') return undefined;
        const t = setInterval(() => { loadDetail(selected); loadList(); }, 4000);
        return () => clearInterval(t);
    }, [detail?.state, selected, loadDetail, loadList]);

    const upload = async (file) => {
        if (!file) return;
        setUploading(true);
        setListError('');
        const fd = new FormData();
        fd.append('file', file);
        try {
            const r = await apiJson('/api/studio/upload', { method: 'POST', body: fd });
            setChannel('all');
            setState('all');
            await loadList();
            pick(r.job_id);
        } catch (e) {
            setListError(e.detail || 'The upload failed.');
        } finally {
            setUploading(false);
            if (fileInput.current) fileInput.current.value = '';
        }
    };

    const channels = useMemo(() => {
        const seen = new Map();
        videos.forEach((v) => seen.set(v.channel, v.channel_name));
        return [...seen.entries()];
    }, [videos]);
    const shown = videos.filter((v) => (channel === 'all' || v.channel === channel)
        && (state === 'all' || v.state === state));

    useEffect(() => {
        if (!selected && shown.length) setSelected(shown[0].job_id);
    }, [shown, selected]);

    const run = async (name, fn, okText) => {
        setBusy(name);
        setNote({ text: '', bad: false });
        try {
            const r = await fn();
            setNote({ text: (r && r.message) || okText, bad: false });
            await loadDetail(selected);
            await loadList();
            setVersion((v) => v + 1);
        } catch (e) {
            setNote({ text: e.detail || 'That did not work. Try again in a minute.', bad: true });
        } finally {
            setBusy('');
        }
    };

    const post = (path, body, method = 'POST') => apiJson(path, {
        method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}),
    });

    const editable = detail && detail.state !== 'uploaded';
    const dirtyCaptions = detail && captions.some((t, i) => t !== (detail.captions[i] || {}).text);
    const look = detail && detail.visual_check;

    return (
        <div className="space-y-4 max-w-7xl mx-auto">
            <header className="flex flex-wrap items-center gap-3">
                <Clapperboard size={20} className="text-brass" />
                <div className="flex-1 min-w-0">
                    <h1 className="text-xl font-display text-ink">Studio</h1>
                    <p className="text-xs text-muted">Tell the AI what to change, check and approve your channels' videos, or upload your own.</p>
                </div>
                <input ref={fileInput} type="file" accept="video/*" className="hidden" aria-label="video file"
                    onChange={(e) => upload(e.target.files?.[0])} />
                <button onClick={() => fileInput.current?.click()} disabled={uploading}
                    className="btn-primary px-3 py-1.5 text-xs inline-flex items-center gap-1.5">
                    {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
                    {uploading ? 'uploading...' : 'upload a video'}
                </button>
                <button onClick={loadList} className="btn-ghost px-3 py-1.5 text-xs inline-flex items-center gap-1.5">
                    <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> refresh
                </button>
            </header>

            <div className="flex flex-wrap items-center gap-2">
                <select value={channel} onChange={(e) => { setChannel(e.target.value); setSelected(null); }}
                    aria-label="channel" className="bg-paper2 border border-rule rounded-input px-2 py-1.5 text-xs text-ink2">
                    <option value="all">All channels</option>
                    {channels.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
                </select>
                {STATES.map((s) => (
                    <button key={s} onClick={() => { setState(s); setSelected(null); }}
                        className={`text-xs rounded-input border px-2.5 py-1 ${state === s ? 'border-brass text-brass' : 'border-rule text-muted hover:text-ink2'}`}>
                        {s}
                    </button>
                ))}
            </div>

            {listError && <p className="text-xs text-warn">{listError}</p>}

            <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
                <div className="space-y-2 lg:max-h-[78vh] lg:overflow-y-auto custom-scrollbar pr-1">
                    {!loading && !shown.length && (
                        <p className="text-xs text-muted rounded-input border border-rule p-3">
                            No videos here yet. Finished videos stay on this computer for a while after they are made.
                        </p>
                    )}
                    {shown.map((v) => (
                        <button key={v.job_id} onClick={() => pick(v.job_id)}
                            className={`w-full text-left flex gap-2.5 rounded-input border p-2 ${selected === v.job_id ? 'border-brass bg-brass/5' : 'border-rule hover:border-rule2'}`}>
                            <img src={getApiUrl(`/api/studio/poster/${v.job_id}?v=${v.done_at || v.at}`)} alt=""
                                loading="lazy" className="w-12 h-20 object-cover rounded bg-paper3 shrink-0" />
                            <span className="min-w-0 flex-1 space-y-1">
                                <span className="block text-xs text-ink2 break-words line-clamp-2">{v.label || 'Untitled'}</span>
                                <span className="block text-[11px] text-muted truncate">{v.channel_name} · {when(v.done_at || v.at)}</span>
                                <span className="flex flex-wrap items-center gap-1.5">
                                    <StateBadge state={v.state} />
                                    {v.look && <span className="text-[10px] text-muted">{v.look.replace('first frame', 'open')}</span>}
                                </span>
                            </span>
                        </button>
                    ))}
                </div>

                {detail ? (
                    <div ref={editor} className="grid gap-4 xl:grid-cols-[minmax(0,360px)_minmax(0,1fr)] min-w-0 scroll-mt-4">
                        <div className="space-y-3 min-w-0">
                            <div className={`mx-auto bg-black rounded-input overflow-hidden ${detail.vertical ? 'max-w-[360px] aspect-[9/16]' : 'aspect-video'}`}>
                                <video key={`${detail.url}-${version}`} ref={player} controls playsInline preload="metadata"
                                    src={getApiUrl(`${detail.url}?v=${version}`)} className="w-full h-full object-contain" />
                            </div>
                            <div className="flex flex-wrap items-center gap-2 text-xs">
                                <StateBadge state={detail.state} />
                                <span className="text-muted">{detail.channel_name} · {clock(detail.seconds)}</span>
                                {detail.video_id && (
                                    <a href={`https://youtu.be/${detail.video_id}`} target="_blank" rel="noreferrer"
                                        className="text-brass inline-flex items-center gap-1 hover:underline">
                                        on YouTube <ExternalLink size={11} />
                                    </a>
                                )}
                            </div>
                            {detail.error && <p className="text-xs text-warn break-words">{detail.error}</p>}
                            {(detail.state === 'waiting' || detail.state === 'held for review') && (
                                <div className="flex flex-wrap gap-2">
                                    {detail.state === 'held for review' && (
                                        <button disabled={!!busy} onClick={() => run('approve', () => post(`/api/studio/video/${detail.job_id}/approve`))}
                                            className="btn-primary px-3 py-1.5 text-xs inline-flex items-center gap-1.5">
                                            {busy === 'approve' ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} approve
                                        </button>
                                    )}
                                    <button disabled={!!busy} onClick={() => window.confirm(detail.main
                                        ? 'Skip this clip? It will not be posted.'
                                        : 'Skip this video? It will not go up, and the channel makes another.')
                                        && run('skip', () => post(`/api/studio/video/${detail.job_id}/skip`))}
                                        className="btn-ghost px-3 py-1.5 text-xs inline-flex items-center gap-1.5">
                                        <SkipForward size={13} /> skip
                                    </button>
                                    {!detail.main && (
                                        <button disabled={!!busy} onClick={() => window.confirm('Skip this video and make its topic again?')
                                            && run('remake', () => post(`/api/studio/video/${detail.job_id}/remake`))}
                                            className="btn-ghost px-3 py-1.5 text-xs inline-flex items-center gap-1.5">
                                            <RotateCcw size={13} /> make again
                                        </button>
                                    )}
                                </div>
                            )}
                            {detail.main && detail.state === 'skipped' && (
                                <button disabled={!!busy} onClick={() => run('approve', () => post(`/api/studio/video/${detail.job_id}/approve`))}
                                    className="btn-ghost px-3 py-1.5 text-xs inline-flex items-center gap-1.5">
                                    {busy === 'approve' ? <Loader2 size={13} className="animate-spin" /> : <RotateCcw size={13} />} put back in Ready to post
                                </button>
                            )}
                            {detail.main && detail.clips > 1 && (
                                <p className="text-[11px] text-muted">Clip {detail.clip} of {detail.clips} cut from the same show; each is its own Short.</p>
                            )}
                            {note.text && <p className={`text-xs break-words ${note.bad ? 'text-warn' : 'text-ok'}`}>{note.text}</p>}

                            {editable && detail.manual !== false && (
                                <Panel icon={Scissors} title="Trim" aside={<span className="text-[11px] text-muted readout">keeps {clock(Math.max(0, trim.end - trim.start))}</span>}>
                                    <div className="grid grid-cols-2 gap-2 text-xs">
                                        {['start', 'end'].map((k) => (
                                            <label key={k} className="space-y-1">
                                                <span className="text-muted">{k} (s)</span>
                                                <div className="flex gap-1">
                                                    <input type="number" step="0.1" min="0" max={detail.seconds} value={trim[k]}
                                                        onChange={(e) => setTrim({ ...trim, [k]: Number(e.target.value) })}
                                                        className="w-full bg-paper2 border border-rule rounded-input px-2 py-1 text-ink2" />
                                                    <button title="use the player's position" onClick={() => setTrim({ ...trim, [k]: Math.round((player.current?.currentTime || 0) * 10) / 10 })}
                                                        className="btn-ghost px-2 text-[11px]">here</button>
                                                </div>
                                            </label>
                                        ))}
                                    </div>
                                    <button disabled={!!busy || trim.end - trim.start < 3}
                                        onClick={() => run('trim', () => post(`/api/studio/video/${detail.job_id}/trim`, trim), 'Trimmed. The captions moved with it.')}
                                        className="btn-ghost px-3 py-1.5 text-xs inline-flex items-center gap-1.5">
                                        {busy === 'trim' ? <Loader2 size={13} className="animate-spin" /> : <Scissors size={13} />} apply trim
                                    </button>
                                    <p className="text-[11px] text-muted">Takes about a minute: the video and its captions are made again.</p>
                                </Panel>
                            )}
                        </div>

                        <div className="space-y-3 min-w-0">
                            <AiEditPanel detail={detail} onChanged={onAiChanged} />
                            {detail.video_id && <YouTubeNumbers jobId={detail.job_id} addTag={addTag} player={player} />}

                            {(look || detail.look) && (
                                <Panel icon={Eye} title="Visual check" aside={look && (
                                    <span className="text-[11px] text-muted readout">first frame {look.first_frame}/10 · polish {look.polish}/10</span>)}>
                                    {!look && <p className="text-xs text-muted">{detail.look}</p>}
                                    {look && look.best_fix && <p className="text-xs text-ink2">Idea: {look.best_fix}</p>}
                                    {look && (look.issues || []).map((i, n) => (
                                        <p key={n} className={`text-xs flex gap-1.5 ${i.severity === 'broken' ? 'text-warn' : 'text-muted'}`}>
                                            <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                                            <span className="break-words">{i.kind.replace('_', ' ')} (frame {i.frame}): {i.detail}</span>
                                        </p>
                                    ))}
                                </Panel>
                            )}

                            <Panel icon={Save} title="Title and description">
                                <div className="space-y-1 text-xs">
                                    <span className="flex items-center justify-between gap-2 text-muted"><span>Title</span>
                                        <span className="flex items-center gap-2">
                                            <button onClick={askTitles} disabled={ideasBusy || !!busy}
                                                title="Other angles for this title, and what people type into YouTube search"
                                                className="inline-flex items-center gap-1 text-[11px] text-brass hover:text-ink disabled:opacity-50">
                                                {ideasBusy ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />} title ideas
                                            </button>
                                            <span className={title.length > TITLE_MAX ? 'text-warn' : ''}>{title.length}/{TITLE_MAX}</span>
                                        </span></span>
                                    <input value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Title"
                                        className="w-full bg-paper2 border border-rule rounded-input px-2 py-1.5 text-ink2" />
                                    {titleIdeas && (
                                        <div className="space-y-1.5 pt-1">
                                            {(titleIdeas.options || []).length === 0 && (
                                                <p className="text-[11px] text-muted">No other angle passed the checks this time; the title stays the best one.</p>
                                            )}
                                            <div className="flex flex-wrap gap-1.5">
                                                {(titleIdeas.options || []).map((t) => (
                                                    <button key={t} onClick={() => setTitle(t)} title="use this title (press save to keep it)"
                                                        className={`text-left text-[11px] border rounded px-2 py-1 break-words ${t === title ? 'border-brass text-ink' : 'border-rule text-ink2 hover:border-brass'}`}>
                                                        {t}
                                                    </button>
                                                ))}
                                                {titleIdeas.current && titleIdeas.current !== title && (
                                                    <button onClick={() => setTitle(titleIdeas.current)}
                                                        className="text-[11px] border border-dashed border-rule rounded px-2 py-1 text-muted hover:text-ink2">
                                                        back to the saved title
                                                    </button>
                                                )}
                                            </div>
                                            {(titleIdeas.searches || []).length > 0 && (
                                                <div className="flex flex-wrap items-center gap-1">
                                                    <span className="text-[11px] text-muted">people search:</span>
                                                    {titleIdeas.searches.map((s) => (
                                                        <button key={s} onClick={() => addTag(s)} title="add to the tags"
                                                            className="text-[10px] text-muted border border-rule rounded px-1.5 py-0.5 hover:text-ink2">
                                                            + {s}
                                                        </button>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                                <label className="block space-y-1 text-xs">
                                    <span className="flex justify-between text-muted"><span>Description</span>
                                        <span className={bytes(description) > DESCRIPTION_MAX ? 'text-warn' : ''}>{bytes(description).toLocaleString()}/{DESCRIPTION_MAX.toLocaleString()} bytes</span></span>
                                    <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={7}
                                        className="w-full bg-paper2 border border-rule rounded-input px-2 py-1.5 text-ink2 custom-scrollbar" />
                                </label>
                                <label className="block space-y-1 text-xs">
                                    <span className="text-muted">Tags (comma between them)</span>
                                    <input value={tags} onChange={(e) => setTags(e.target.value)}
                                        className="w-full bg-paper2 border border-rule rounded-input px-2 py-1.5 text-ink2" />
                                </label>
                                <ul className="space-y-0.5">
                                    {checks.map((c) => (
                                        <li key={c.text} className={`flex items-start gap-1.5 text-[11px] ${c.ok ? 'text-muted' : 'text-warn'}`}>
                                            {c.ok ? <Check size={11} className="shrink-0 mt-0.5 text-ok" /> : <AlertTriangle size={11} className="shrink-0 mt-0.5" />}
                                            <span className="break-words">{c.text}</span>
                                        </li>
                                    ))}
                                </ul>
                                {detail.video_id && (
                                    <label className="flex items-center gap-2 text-xs text-ink2">
                                        <input type="checkbox" checked={push} onChange={(e) => setPush(e.target.checked)} />
                                        update the video on YouTube too (uses 50 of the day's 10,000 API units)
                                    </label>
                                )}
                                <button disabled={!!busy || !title.trim() || title.length > TITLE_MAX || bytes(description) > DESCRIPTION_MAX}
                                    onClick={() => run('details', () => post(`/api/studio/video/${detail.job_id}/details`,
                                        { title, description, tags, push }, 'PUT'), push ? 'Saved, and updated on YouTube.' : 'Saved.')}
                                    className="btn-primary px-3 py-1.5 text-xs inline-flex items-center gap-1.5">
                                    {busy === 'details' ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} save
                                </button>
                            </Panel>

                            {(detail.captions_editable || (detail.manual === false && detail.captions.length > 0)) && (
                                <Panel icon={Type} title="Captions" aside={<span className="text-[11px] text-muted">click a time to jump there</span>}>
                                    {!editable && <p className="text-xs text-muted">This video is already on YouTube, so its captions stay as they are.</p>}
                                    {editable && !detail.captions_editable && (
                                        <p className="text-xs text-muted">This clip shares its words with the other clips of the same show: to change a
                                            caption, tell the AI above, e.g. "caption mein 'X' ko 'Y' karo".</p>
                                    )}
                                    <div className="space-y-1.5 max-h-[46vh] overflow-y-auto custom-scrollbar pr-1">
                                        {detail.captions.map((c, i) => (
                                            <div key={i} className="flex items-start gap-2">
                                                <button onClick={() => { if (player.current) { player.current.currentTime = c.start; player.current.play(); } }}
                                                    className="readout text-[11px] text-brass hover:underline pt-1.5 w-12 shrink-0 text-left">{clock(c.start)}</button>
                                                <input value={captions[i] ?? ''} disabled={!editable || !detail.captions_editable}
                                                    onChange={(e) => setCaptions(captions.map((t, n) => (n === i ? e.target.value : t)))}
                                                    className={`flex-1 min-w-0 bg-paper2 border rounded-input px-2 py-1 text-xs text-ink2 ${captions[i] !== c.text ? 'border-brass' : 'border-rule'}`} />
                                            </div>
                                        ))}
                                    </div>
                                    {editable && detail.captions_editable && (
                                        <div className="flex flex-wrap items-center gap-2">
                                            <button disabled={!!busy || !dirtyCaptions}
                                                onClick={() => run('captions', () => post(`/api/studio/video/${detail.job_id}/captions`,
                                                    { captions: captions.map((text) => ({ text })) }), 'Captions burned in again.')}
                                                className="btn-primary px-3 py-1.5 text-xs inline-flex items-center gap-1.5">
                                                {busy === 'captions' ? <Loader2 size={13} className="animate-spin" /> : <Type size={13} />} save captions
                                            </button>
                                            {dirtyCaptions && (
                                                <button onClick={() => setCaptions(detail.captions.map((c) => c.text))} className="text-xs text-muted hover:text-ink2">undo changes</button>
                                            )}
                                            <span className="text-[11px] text-muted">Same word count keeps the timing; a different count spreads the words over the line.</span>
                                        </div>
                                    )}
                                </Panel>
                            )}
                        </div>
                    </div>
                ) : (
                    <p className="text-xs text-muted rounded-input border border-rule p-3 self-start">
                        {loading ? 'Loading...' : 'Pick a video on the left.'}
                    </p>
                )}
            </div>
        </div>
    );
}
