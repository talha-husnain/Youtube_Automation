import React, { useState, useEffect, useRef } from 'react';
import { Link2, Info, Loader2, ChevronDown, Plus, X } from 'lucide-react';
import { getApiUrl } from '../config';

const SUPPORTED_PLATFORMS = [
    'YouTube', 'Vimeo', 'TikTok', 'X / Twitter', 'Twitch',
    'Facebook', 'Instagram', 'Dailymotion', 'Reddit', 'Streamable',
];

// Video types: comedy is the clip pipeline; songs, movie dubs and cricket
// have their own flows on the server (song_shorts / movie_dub / cricket_shorts).
// Songs is hidden (owner, 8-oct-2026: too slow to finish in the YouTube app);
// the server flow stays, remove `hidden` to bring it back.
const GENRES = [
    { id: 'comedy', label: 'Comedy', ready: true, hint: 'stand-up and funny clips' },
    { id: 'songs', label: 'Songs', ready: true, hint: 'a visual for a song', hidden: true },
    { id: 'movies', label: 'Movie dub', ready: true, hint: 'movie scenes with new funny Urdu dialogue' },
    { id: 'cricket', label: 'Cricket', ready: true, hint: 'an animated match story, no footage' },
];

const GENRE_NOTES = {
    songs: 'Without "I own this music" the short comes out silent: add the song in the YouTube app (each result says how). Lyrics only show for music you own.',
    movies: 'Each scene gets brand-new funny Roman Urdu dialogue and AI voices. The original sound is muted. Keep dubs under a minute.',
    cricket: 'A match: type it or paste its video link, and Shortkaar finds the facts and animates the scores. Facts & stats: rules, player stats, records, history. A voice tells it over our own animated background; no match footage is used.',
};

// Clip length presets (seconds, as strings like the inputs). Auto = blank:
// the server's default 15-60 s band.
const LENGTH_PRESETS = [
    { label: 'Auto', min: '', max: '' },
    { label: '15-30s', min: '15', max: '30' },
    { label: '30-60s', min: '30', max: '60' },
    { label: '60-90s', min: '60', max: '90' },
    { label: '90-150s', min: '90', max: '150' },
];

// Background presets for the framed look.
const BRAND = { handle: '@PunchlineBazaar', bg: '#2B0F3D' };
const FRAME_COLORS = ['#2B0F3D', '#14142B', '#000000', '#FFFFFF', '#0F3D3E', '#7B1E3A', '#F2C14E', '#1D4ED8'];

export default function MediaInput({ onProcess, isProcessing }) {
    // Links only: the file upload path was removed from this dashboard.
    const [youtubeUrlEnabled, setYoutubeUrlEnabled] = useState(true);
    const [url, setUrl] = useState('');
    // More links: the best moments of all of them become ONE short
    // (compilation.py). Empty = the normal one-link job, unchanged.
    const [extraUrls, setExtraUrls] = useState([]);
    const [compileSeconds, setCompileSeconds] = useState(() => {
        try { return localStorage.getItem('os_compile_seconds') || '170'; } catch { return '170'; }
    });
    const [acknowledged, setAcknowledged] = useState(false);
    // framed (colour background + title + captions) is the default look.
    const [outputFormat, setOutputFormat] = useState((() => { try { return localStorage.getItem('os_output_format') || 'framed'; } catch { return 'framed'; } })); // framed | vertical | horizontal | square
    const [frameBg, setFrameBg] = useState((() => { try { return localStorage.getItem('os_frame_bg_v2') || BRAND.bg; } catch { return BRAND.bg; } }));
    const [frameCrop, setFrameCrop] = useState((() => { try { return localStorage.getItem('os_frame_crop') || 'classic'; } catch { return 'classic'; } })); // wide | classic | square
    const [frameZoom, setFrameZoom] = useState((() => { try { return localStorage.getItem('os_frame_zoom') || '1.12'; } catch { return '1.12'; } }));
    // Caption + title language: roman (Roman Urdu / Hinglish), english, original.
    const [captionScript, setCaptionScript] = useState(() => {
        try { return localStorage.getItem('os_caption_script') || 'roman'; } catch { return 'roman'; }
    });
    const [frameHandle, setFrameHandle] = useState(() => {
        try { return localStorage.getItem('os_frame_handle') ?? BRAND.handle; } catch { return BRAND.handle; }
    });
    const [frameOutro, setFrameOutro] = useState(() => {
        try { return localStorage.getItem('os_frame_outro') !== '0'; } catch { return true; }
    });
    const [frameOutroSeconds, setFrameOutroSeconds] = useState(() => {
        try { return localStorage.getItem('os_frame_outro_s') || '3'; } catch { return '3'; }
    });
    const [frameTitle, setFrameTitle] = useState(() => {
        try { return localStorage.getItem('os_frame_title') !== '0'; } catch { return true; }
    });
    // Video type (only comedy is built) and the channel's AI take after each clip.
    const [genre, setGenre] = useState(() => {
        try {
            const saved = localStorage.getItem('os_genre') || 'comedy';
            return GENRES.some((g) => g.id === saved && !g.hidden) ? saved : 'comedy';
        } catch { return 'comedy'; }
    });
    const [songOwned, setSongOwned] = useState(false);
    const [cricketMatch, setCricketMatch] = useState('');
    // Cricket: a match (name or video link) or a topic (rules, stats, records).
    const [cricketMode, setCricketMode] = useState('match');
    const [bgMusic, setBgMusic] = useState(() => {
        try { return localStorage.getItem('os_bg_music') === '1'; } catch { return false; }
    });
    const [musicTracks, setMusicTracks] = useState(0);
    const [ideas, setIdeas] = useState([]);
    const [ideasState, setIdeasState] = useState('');

    const loadIdeas = () => {
        setIdeasState('loading');
        fetch(getApiUrl('/api/cricket/ideas'))
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
            .then((d) => { setIdeas(d.ideas || []); setIdeasState(d.ideas && d.ideas.length ? '' : 'none'); })
            .catch(() => setIdeasState('error'));
    };
    const [aiTake, setAiTake] = useState(() => {
        try { return localStorage.getItem('os_ai_take') !== '0'; } catch { return true; }
    });
    const [showInfo, setShowInfo] = useState(false);
    // Advanced generation controls — empty string means "let the AI decide",
    // which keeps the default pipeline behavior untouched.
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [targetClips, setTargetClips] = useState('');
    // Clip length range: the model picks each clip's length inside it.
    // Blank = the default 15-60 s band. Remembered like the other choices.
    const [clipMinSeconds, setClipMinSeconds] = useState(() => {
        try { return localStorage.getItem('os_clip_min') || ''; } catch { return ''; }
    });
    const [clipMaxSeconds, setClipMaxSeconds] = useState(() => {
        try { return localStorage.getItem('os_clip_max') || ''; } catch { return ''; }
    });
    const [customLength, setCustomLength] = useState(false);
    // Auto-hook: burn the AI hook text into every clip. On by default; the
    // choice persists so turning it off sticks across sessions.
    const [autoHook, setAutoHook] = useState(() => {
        try { return localStorage.getItem('os_auto_hook') !== '0'; } catch { return true; }
    });
    const [autoHookStyle, setAutoHookStyle] = useState(() => {
        // v2 key: the default became 'pill'; an old saved 'classic' was just the old default.
        try { return localStorage.getItem('os_auto_hook_style_v2') || 'pill'; } catch { return 'pill'; }
    });
    // Layout: 'auto' lets the AI pick per video (server default); the others
    // force one on so a podcast host who knows what they uploaded doesn't
    // depend on the detector, and 'none' keeps the plain single crop.
    const [layout, setLayout] = useState(() => {
        try { return localStorage.getItem('os_layout') || 'auto'; } catch { return 'auto'; }
    });
    const infoRef = useRef(null);

    // Close the compatibility popover on any outside click.
    useEffect(() => {
        if (!showInfo) return;
        const onClick = (e) => {
            if (infoRef.current && !infoRef.current.contains(e.target)) setShowInfo(false);
        };
        document.addEventListener('mousedown', onClick);
        return () => document.removeEventListener('mousedown', onClick);
    }, [showInfo]);

    useEffect(() => {
        fetch(getApiUrl('/api/config'))
            .then((r) => r.ok ? r.json() : null)
            .then((cfg) => {
                if (cfg && cfg.youtubeUrlEnabled === false) setYoutubeUrlEnabled(false);
                if (cfg && typeof cfg.musicTracks === 'number') setMusicTracks(cfg.musicTracks);
            })
            .catch(() => {});
    }, []);

    // A link pasted in the landing hero: preload it here so the user picks up
    // where they left off. Not auto-submitted — the rights attestation below
    // has to be ticked by the user.
    useEffect(() => {
        let pending = null;
        try {
            pending = localStorage.getItem('os_pending_url');
            if (pending) localStorage.removeItem('os_pending_url');
        } catch { /* ignore */ }
        if (pending) setUrl(pending);
    }, []);

    // Reuse check of the pasted YouTube link: its licence and how much of it
    // earlier Shorts already used. Advice only; a 404 (cloud) hides it.
    const [licence, setLicence] = useState(null);
    useEffect(() => {
        setLicence(null);
        const link = url.trim();
        if (genre === 'cricket' || !/(youtube\.com\/(watch|shorts|live)|youtu\.be\/)/.test(link)) return undefined;
        let alive = true;
        const t = setTimeout(() => {
            setLicence({ loading: true });
            fetch(getApiUrl(`/api/finder/licence?url=${encodeURIComponent(link)}`))
                .then((r) => (r.ok ? r.json() : null))
                .then((d) => { if (alive) setLicence(d); })
                .catch(() => { if (alive) setLicence(null); });
        }, 700);
        return () => { alive = false; clearTimeout(t); };
    }, [url, genre]);

    const lengthError = (() => {
        const lo = Number(clipMinSeconds || 0), hi = Number(clipMaxSeconds || 0);
        if (clipMinSeconds && (lo < 5 || lo > 172)) return 'Minimum length must be 5 to 172 seconds.';
        if (clipMaxSeconds && (hi < 10 || hi > 177)) return 'Maximum length must be 10 to 177 seconds (Shorts stop at 3 minutes).';
        if (clipMinSeconds && clipMaxSeconds && hi < lo + 5) return 'Maximum must be at least 5 seconds more than minimum.';
        return '';
    })();

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!acknowledged || lengthError) return;
        const advanced = {
            targetClips: targetClips || null,
            clipMinSeconds: clipMinSeconds || null,
            clipMaxSeconds: clipMaxSeconds || null,
            autoHook,
            autoHookStyle,
            layout,
            frameBg,
            frameCrop,
            frameZoom,
            frameTitle,
            frameHandle,
            frameOutro,
            frameOutroSeconds,
            captionScript,
            genre,
            aiTake: genre === 'comedy' ? aiTake : false,
            songOwned,
            cricketMatch,
            cricketMode,
            bgMusic,
        };
        try {
            localStorage.setItem('os_caption_script', captionScript);
            localStorage.setItem('os_ai_take', aiTake ? '1' : '0');
            localStorage.setItem('os_genre', genre);
            localStorage.setItem('os_bg_music', bgMusic ? '1' : '0');
            localStorage.setItem('os_clip_min', clipMinSeconds);
            localStorage.setItem('os_clip_max', clipMaxSeconds);
            localStorage.setItem('os_output_format', outputFormat);
            localStorage.setItem('os_frame_bg_v2', frameBg);
            localStorage.setItem('os_frame_handle', frameHandle);
            localStorage.setItem('os_frame_outro', frameOutro ? '1' : '0');
            localStorage.setItem('os_frame_outro_s', frameOutroSeconds);
            localStorage.setItem('os_frame_crop', frameCrop);
            localStorage.setItem('os_frame_zoom', frameZoom);
            localStorage.setItem('os_frame_title', frameTitle ? '1' : '0');
            localStorage.setItem('os_auto_hook', autoHook ? '1' : '0');
            localStorage.setItem('os_auto_hook_style_v2', autoHookStyle);
            localStorage.setItem('os_layout', layout);
        } catch { /* ignore */ }
        const links = [url, ...extraUrls].map((u) => u.trim()).filter(Boolean);
        if (genre === 'cricket') {
            if (cricketMatch.trim()) {
                onProcess({ type: 'url', payload: '', acknowledged: true, ...advanced, outputFormat: 'framed' });
            }
            return;
        }
        if (genre !== 'comedy') {
            // Songs (a mashup when the music is owned) and movie dubs: always framed.
            const many = genre === 'songs' && songOwned && links.length >= 2;
            onProcess({ type: 'url', payload: links[0], ...(many ? { urls: links } : {}),
                acknowledged: true, ...advanced, outputFormat: 'framed' });
            return;
        }
        if (links.length >= 2) {
            try { localStorage.setItem('os_compile_seconds', compileSeconds); } catch { /* ignore */ }
            onProcess({
                type: 'url', payload: links[0], urls: links, compileSeconds,
                acknowledged: true, ...advanced, targetClips: null, outputFormat: 'framed',
            });
        } else if (url) {
            onProcess({ type: 'url', payload: url, acknowledged: true, outputFormat, ...advanced });
        }
    };

    return (
        <div className="card p-4 sm:p-6 animate-fade">
            <div className="flex items-center gap-2 pb-3 mb-6 border-b border-rule text-sm lowercase text-ink" data-tutorial="source-tabs">
                <Link2 size={16} className="text-brass" />
                {genre === 'cricket' ? 'cricket match' : 'YouTube link'}
            </div>

            <form onSubmit={handleSubmit}>
                {/* Video type first: it decides what the AI does and what to paste. */}
                <div className="mb-4 flex flex-wrap items-center gap-2" data-tutorial="video-type">
                    <span className="eyebrow mr-1">video type</span>
                    {GENRES.filter((g) => !g.hidden).map((g) => (
                        <button
                            key={g.id}
                            type="button"
                            onClick={() => setGenre(g.id)}
                            title={g.hint}
                            aria-pressed={genre === g.id}
                            className={`px-3 py-1.5 rounded-input border text-xs ${genre === g.id ? 'border-[color:var(--color-accent)] text-ink' : 'border-rule2 text-muted hover:border-[color:var(--color-accent)]'}`}
                        >
                            {g.label}
                        </button>
                    ))}
                </div>
                {GENRE_NOTES[genre] && (
                    <p className="-mt-2 mb-4 text-[11px] leading-relaxed text-muted">{GENRE_NOTES[genre]}</p>
                )}
                {genre === 'cricket' && (
                    <div className="space-y-3">
                        <div className="flex flex-wrap items-center gap-2">
                            {[['match', 'A match'], ['topic', 'Facts & stats']].map(([id, label]) => (
                                <button key={id} type="button" onClick={() => setCricketMode(id)} aria-pressed={cricketMode === id}
                                    className={`px-3 py-1.5 rounded-input border text-xs ${cricketMode === id ? 'border-[color:var(--color-accent)] text-ink' : 'border-rule2 text-muted hover:border-[color:var(--color-accent)]'}`}>
                                    {label}
                                </button>
                            ))}
                            <button type="button" onClick={loadIdeas} disabled={ideasState === 'loading'}
                                className="ml-auto text-xs lowercase text-muted hover:text-brass transition-colors">
                                {ideasState === 'loading' ? 'finding ideas...' : 'ideas for this week'}
                            </button>
                        </div>
                        <input
                            type="text"
                            value={cricketMatch}
                            onChange={(e) => setCricketMatch(e.target.value)}
                            placeholder={cricketMode === 'topic'
                                ? 'Topic: Babar Azam ODI stats, the LBW rule, fastest centuries...'
                                : 'Paste a match video link, or type: Pakistan vs India, Asia Cup 2025 final'}
                            aria-label={cricketMode === 'topic' ? 'cricket topic' : 'which cricket match'}
                            maxLength={300}
                            className="input-field"
                            required
                        />
                        {ideas.length > 0 && (
                            <div className="flex flex-wrap gap-1.5">
                                {ideas.map((it) => (
                                    <button key={it.kind + it.text} type="button"
                                        onClick={() => { setCricketMode(it.kind === 'topic' ? 'topic' : 'match'); setCricketMatch(it.text); }}
                                        className="text-left text-[11px] px-2 py-1 rounded-input border border-rule2 text-ink2 hover:border-[color:var(--color-accent)]">
                                        <span className="eyebrow mr-1">{it.kind}</span>{it.text}
                                    </button>
                                ))}
                            </div>
                        )}
                        {ideasState === 'error' && <p className="text-[11px] text-danger">Could not fetch ideas right now; type your own.</p>}
                        <label className="flex items-start gap-2 text-xs text-ink2 cursor-pointer select-none">
                            <input type="checkbox" checked={bgMusic} onChange={(e) => setBgMusic(e.target.checked)}
                                className="mt-0.5 w-4 h-4 shrink-0 accent-[var(--color-accent)] cursor-pointer" />
                            <span>
                                background music under the voice
                                <span className="block text-[11px] text-muted">
                                    {musicTracks > 0
                                        ? `${musicTracks} track${musicTracks > 1 ? 's' : ''} in the music folder; a random one is used.`
                                        : 'Add royalty-free tracks (YouTube Audio Library, Pixabay) to the music folder first.'}
                                </span>
                            </span>
                        </label>
                    </div>
                )}
                {!youtubeUrlEnabled && genre !== 'cricket' && (
                    <p className="text-sm text-danger mb-3" role="alert">
                        Video links are disabled on this server (DISABLE_YOUTUBE_URL).
                    </p>
                )}
                {genre !== 'cricket' && (
                    <div className="space-y-4" data-tutorial="drop-zone">
                        <div className="relative">
                            <input
                                type="url"
                                value={url}
                                onChange={(e) => setUrl(e.target.value)}
                                placeholder={genre === 'songs' ? 'https://... paste the song\'s YouTube link'
                                    : genre === 'movies' ? 'https://... paste a movie scene link'
                                    : 'https://... paste a video link'}
                                className="input-field pr-11"
                                required
                            />
                            <div className="absolute inset-y-0 right-2 flex items-center" ref={infoRef}>
                                <button
                                    type="button"
                                    onClick={() => setShowInfo((v) => !v)}
                                    aria-label="Supported platforms"
                                    className="p-1.5 text-muted hover:text-brass transition-colors"
                                >
                                    <Info size={16} />
                                </button>
                                {showInfo && (
                                    <div className="absolute right-0 top-full mt-2 w-64 z-20 card p-4 text-left animate-fade">
                                        <p className="eyebrow mb-2">Paste a link from</p>
                                        <div className="flex flex-wrap gap-1.5">
                                            {SUPPORTED_PLATFORMS.map((p) => (
                                                <span key={p} className="text-xs px-2 py-0.5 rounded-full bg-paper3 text-ink2">
                                                    {p}
                                                </span>
                                            ))}
                                        </div>
                                        <p className="text-xs text-muted mt-2.5 leading-relaxed">
                                            …and 1,000+ more sites. If a link has a public video, we can usually fetch it.
                                        </p>
                                    </div>
                                )}
                            </div>
                        </div>

                        {licence && (
                            <div className="-mt-2 text-[11px] leading-relaxed" aria-live="polite">
                                {licence.loading ? (
                                    <span className="text-muted inline-flex items-center gap-1.5">
                                        <Loader2 size={12} className="animate-spin" /> checking if reuse is allowed…
                                    </span>
                                ) : (
                                    <>
                                        {licence.licence === 'creative_commons' && (
                                            <p className="text-ok">Reuse allowed: this video is Creative Commons. Check that {licence.channel || 'the channel'} is the real owner.</p>
                                        )}
                                        {licence.licence === 'standard' && (
                                            <p className="text-warn">Standard YouTube licence: reuse is not allowed by default, so Shorts from it can be claimed or removed.</p>
                                        )}
                                        {licence.licence === 'unknown' && (
                                            <p className="text-muted">Could not check the licence of this video.</p>
                                        )}
                                        {licence.used?.count > 0 && (
                                            <p className="text-muted">You already made {licence.used.count} {licence.used.count === 1 ? 'Short' : 'Shorts'} from this video; new ones will use other moments.</p>
                                        )}
                                    </>
                                )}
                            </div>
                        )}

                        {genre === 'songs' && (
                            <label className="flex items-start gap-2 text-xs text-ink2 cursor-pointer select-none">
                                <input type="checkbox" checked={songOwned} onChange={(e) => setSongOwned(e.target.checked)}
                                    className="mt-0.5 w-4 h-4 shrink-0 accent-[var(--color-accent)] cursor-pointer" />
                                I own this music or it is royalty-free: keep the sound, show the lyrics, and allow a mashup of several links
                            </label>
                        )}
                        {(genre === 'comedy' || (genre === 'songs' && songOwned)) && extraUrls.map((u, i) => (
                            <div key={i} className="relative">
                                <input
                                    type="url"
                                    value={u}
                                    onChange={(e) => setExtraUrls((list) => list.map((x, j) => (j === i ? e.target.value : x)))}
                                    placeholder={`link ${i + 2}`}
                                    className="input-field pr-11"
                                />
                                <button
                                    type="button"
                                    onClick={() => setExtraUrls((list) => list.filter((_, j) => j !== i))}
                                    aria-label={`remove link ${i + 2}`}
                                    className="absolute inset-y-0 right-2 flex items-center p-1.5 text-muted hover:text-danger transition-colors"
                                >
                                    <X size={16} />
                                </button>
                            </div>
                        ))}
                        {(genre === 'comedy' || (genre === 'songs' && songOwned)) && extraUrls.length < 4 && (
                            <button
                                type="button"
                                onClick={() => setExtraUrls((list) => [...list, ''])}
                                className="flex items-center gap-1.5 text-xs lowercase text-muted hover:text-brass transition-colors"
                            >
                                <Plus size={14} /> {genre === 'songs' ? 'add another song for a mashup' : 'add another link to combine into one short'}
                            </button>
                        )}
                        {genre === 'comedy' && extraUrls.some((u) => u.trim()) && (
                            <div className="rounded-input border border-rule bg-paper px-3 py-2.5 text-xs text-ink2 flex flex-wrap items-center gap-x-3 gap-y-2">
                                <span>
                                    {1 + extraUrls.filter((u) => u.trim()).length} links: their best moments become one framed short.
                                </span>
                                <label className="flex items-center gap-2">
                                    <span className="text-muted">length</span>
                                    <select
                                        value={compileSeconds}
                                        onChange={(e) => setCompileSeconds(e.target.value)}
                                        className="input-field py-1 px-2 text-xs w-auto"
                                    >
                                        <option value="60">up to 1 min</option>
                                        <option value="120">up to 2 min</option>
                                        <option value="170">up to 3 min (Shorts max)</option>
                                    </select>
                                </label>
                            </div>
                        )}
                    </div>
                )}

                {/* Output format selector */}
                <div className="mt-5" data-tutorial="output-format">
                    {genre === 'comedy' && <p className="eyebrow mb-2">Output format</p>}
                    {genre === 'comedy' && <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                        {[
                            { value: 'framed', label: 'Framed', hint: 'Colour bg · title · captions', w: 18, h: 32 },
                            { value: 'vertical', label: '9:16', hint: 'Face-tracked crop', w: 18, h: 32 },
                            { value: 'square', label: '1:1', hint: 'Feed posts', w: 28, h: 28 },
                            { value: 'horizontal', label: '16:9', hint: 'Keep landscape · YouTube', w: 36, h: 20 },
                        ].map((f) => {
                            const active = outputFormat === f.value;
                            return (
                                <button
                                    key={f.value}
                                    type="button"
                                    onClick={() => setOutputFormat(f.value)}
                                    className={`py-3 px-2 rounded-input border flex flex-col items-center gap-2 transition-colors
                                        ${active ? 'border-[color:var(--color-accent)] text-ink' : 'border-rule2 text-muted hover:border-[color:var(--color-accent)]'}`}
                                >
                                    {/* Aspect-ratio glyph */}
                                    <span
                                        className="rounded-[3px] border-2 transition-colors"
                                        style={{
                                            width: `${f.w}px`,
                                            height: `${f.h}px`,
                                            borderColor: active ? 'var(--color-accent)' : 'var(--color-rule-2)',
                                            backgroundColor: active ? 'color-mix(in srgb, var(--color-accent) 22%, transparent)' : 'transparent',
                                        }}
                                    />
                                    <span className="block font-mono text-sm leading-none">{f.label}</span>
                                    <span className="block text-[11px] sm:text-[10px] leading-tight text-center text-muted">{f.hint}</span>
                                </button>
                            );
                        })}
                    </div>}
                    {(outputFormat === 'framed' || genre !== 'comedy') && (
                        <div className="mt-3 space-y-3 rounded-input border border-rule p-3 animate-fade">
                            <div className="flex flex-wrap items-center gap-2">
                                <span className="text-xs text-ink2 w-24">background</span>
                                {FRAME_COLORS.map((c) => (
                                    <button
                                        key={c}
                                        type="button"
                                        aria-label={`background ${c}`}
                                        onClick={() => setFrameBg(c)}
                                        className={`w-7 h-7 rounded-full border-2 ${frameBg.toUpperCase() === c ? 'border-[color:var(--color-accent)]' : 'border-rule2'}`}
                                        style={{ backgroundColor: c }}
                                    />
                                ))}
                                <input
                                    type="color"
                                    value={frameBg}
                                    onChange={(e) => setFrameBg(e.target.value.toUpperCase())}
                                    aria-label="custom background colour"
                                    className="w-8 h-8 cursor-pointer bg-transparent"
                                />
                            </div>
                            {/* Songs and cricket draw their own picture: nothing to crop. */}
                            {(genre === 'comedy' || genre === 'movies') && <div className="flex flex-wrap items-center gap-2">
                                <span className="text-xs text-ink2 w-24">crop</span>
                                <select value={frameCrop} onChange={(e) => setFrameCrop(e.target.value)}
                                    className="input-field !w-auto text-xs py-1.5" aria-label="crop shape">
                                    <option value="classic">4:3 (bigger subject)</option>
                                    <option value="wide">16:9 (whole width)</option>
                                    <option value="square">1:1 (tightest)</option>
                                </select>
                                <select value={frameZoom} onChange={(e) => setFrameZoom(e.target.value)}
                                    className="input-field !w-auto text-xs py-1.5" aria-label="zoom">
                                    <option value="1.0">No zoom</option>
                                    <option value="1.12">Zoom 12%</option>
                                    <option value="1.25">Zoom 25%</option>
                                </select>
                            </div>}
                            <label className="flex items-center gap-2 text-xs text-ink2 cursor-pointer select-none">
                                <input type="checkbox" checked={frameTitle} onChange={(e) => setFrameTitle(e.target.checked)}
                                    className="w-4 h-4 shrink-0 accent-[var(--color-accent)] cursor-pointer" />
                                title above the video
                            </label>
                            <div className="flex flex-wrap items-center gap-2">
                                <span className="text-xs text-ink2 w-24">channel</span>
                                <input
                                    type="text"
                                    value={frameHandle}
                                    maxLength={30}
                                    onChange={(e) => setFrameHandle(e.target.value)}
                                    placeholder="@yourchannel"
                                    aria-label="channel handle"
                                    className="input-field !w-48 text-xs py-1.5"
                                />
                            </div>
                            <label className="flex items-center gap-2 text-xs text-ink2 cursor-pointer select-none">
                                <input type="checkbox" checked={frameOutro} onChange={(e) => setFrameOutro(e.target.checked)}
                                    className="w-4 h-4 shrink-0 accent-[var(--color-accent)] cursor-pointer" />
                                animated end card: &quot;follow for more&quot; + channel
                            </label>
                            {frameOutro && (
                                <select value={frameOutroSeconds} onChange={(e) => setFrameOutroSeconds(e.target.value)}
                                    className="input-field !w-auto text-xs py-1.5" aria-label="end card length">
                                    <option value="1">1 second</option>
                                    <option value="2">2 seconds</option>
                                    <option value="3">3 seconds</option>
                                </select>
                            )}
                            <p className="text-[11px] leading-relaxed text-muted">
                                Captions are added under the video automatically. Zoom also trims logos and
                                subtitles already burned into the source.
                            </p>
                        </div>
                    )}
                </div>

                {/* How many shorts: visible, since it is the main choice after the link. */}
                {genre !== 'cricket' && <div className="mt-4 flex flex-wrap items-center gap-2">
                    <span className="eyebrow mr-1">{genre === 'movies' ? 'scenes to dub' : 'number of shorts'}</span>
                    {(genre === 'comedy' ? ['', '3', '5', '8', '10']
                        : genre === 'songs' && songOwned && extraUrls.some((u) => u.trim()) ? ['']
                        : ['', '1', '2', '3']).map((n) => (
                        <button
                            key={n || 'auto'}
                            type="button"
                            onClick={() => setTargetClips(n)}
                            className={`px-3 py-1.5 rounded-input border text-xs ${targetClips === n ? 'border-[color:var(--color-accent)] text-ink' : 'border-rule2 text-muted hover:border-[color:var(--color-accent)]'}`}
                        >
                            {n || (genre === 'comedy' ? 'Auto (best)' : genre === 'songs' && extraUrls.some((u) => u.trim()) && songOwned ? '1 mashup' : 'Auto (2)')}
                        </button>
                    ))}
                </div>}

                {/* Clip length: the AI picks each clip's length inside this range. */}
                {(genre === 'comedy' || genre === 'songs') && <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span className="eyebrow mr-1">clip length</span>
                    {LENGTH_PRESETS.map((p) => {
                        const on = !customLength && clipMinSeconds === p.min && clipMaxSeconds === p.max;
                        return (
                            <button
                                key={p.label}
                                type="button"
                                onClick={() => { setCustomLength(false); setClipMinSeconds(p.min); setClipMaxSeconds(p.max); }}
                                className={`px-3 py-1.5 rounded-input border text-xs ${on ? 'border-[color:var(--color-accent)] text-ink' : 'border-rule2 text-muted hover:border-[color:var(--color-accent)]'}`}
                            >
                                {p.label}
                            </button>
                        );
                    })}
                    <button
                        type="button"
                        onClick={() => setCustomLength(true)}
                        className={`px-3 py-1.5 rounded-input border text-xs ${customLength || (clipMinSeconds && !LENGTH_PRESETS.some((p) => p.min === clipMinSeconds && p.max === clipMaxSeconds)) ? 'border-[color:var(--color-accent)] text-ink' : 'border-rule2 text-muted hover:border-[color:var(--color-accent)]'}`}
                    >
                        custom
                    </button>
                    {(customLength || (clipMinSeconds && !LENGTH_PRESETS.some((p) => p.min === clipMinSeconds && p.max === clipMaxSeconds))) && (
                        <span className="flex items-center gap-1.5 text-xs text-muted">
                            <input
                                type="number" min="5" max="172" step="1"
                                value={clipMinSeconds}
                                onChange={(e) => setClipMinSeconds(e.target.value)}
                                placeholder="min"
                                aria-label="minimum clip length in seconds"
                                className="input-field !w-20 text-xs py-1.5"
                            />
                            to
                            <input
                                type="number" min="10" max="177" step="1"
                                value={clipMaxSeconds}
                                onChange={(e) => setClipMaxSeconds(e.target.value)}
                                placeholder="max"
                                aria-label="maximum clip length in seconds"
                                className="input-field !w-20 text-xs py-1.5"
                            />
                            seconds
                        </span>
                    )}
                </div>}
                {lengthError && <p className="mt-1.5 text-[11px] text-danger" role="alert">{lengthError}</p>}

                {genre === 'comedy' && <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span className="eyebrow mr-1">subtitles</span>
                    <select
                        value={captionScript}
                        onChange={(e) => setCaptionScript(e.target.value)}
                        className="input-field !w-auto text-xs py-1.5"
                        aria-label="subtitle language"
                    >
                        <option value="roman">Roman Urdu / Hinglish</option>
                        <option value="english">English</option>
                        <option value="original">As spoken (original script)</option>
                    </select>
                    <span className="text-[11px] text-muted">titles and descriptions are always Roman Urdu</span>
                </div>}

                {genre === 'comedy' && <label className="mt-3 flex items-center gap-2 text-xs text-ink2 cursor-pointer select-none">
                    <input type="checkbox" checked={aiTake} onChange={(e) => setAiTake(e.target.checked)}
                        className="w-4 h-4 shrink-0 accent-[var(--color-accent)] cursor-pointer" />
                    AI take after each clip: a short voiced reaction + a question for the comments
                </label>}

                {/* Advanced generation controls — collapsed by default; blank = AI decides */}
                <div className="mt-4">
                    <button
                        type="button"
                        onClick={() => setShowAdvanced((v) => !v)}
                        className="flex items-center gap-1.5 text-xs text-muted hover:text-ink2 lowercase transition-colors"
                    >
                        <ChevronDown size={14} className={`transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
                        advanced options
                        {(targetClips || clipMinSeconds || clipMaxSeconds || !autoHook) && (
                            <span className="text-brass">·</span>
                        )}
                    </button>
                    {showAdvanced && (
                        /* Stacked on a phone: three number fields side by side leaves
                           ~100px each, which crushes both label and value. */
                        <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-2 animate-fade">
                            <div>
                                <p className="eyebrow mb-1.5">clips to aim for</p>
                                <input
                                    type="number" min="1" max="15" step="1"
                                    value={targetClips}
                                    onChange={(e) => setTargetClips(e.target.value)}
                                    placeholder="auto"
                                    className="input-field"
                                />
                            </div>
                            <div>
                                <p className="eyebrow mb-1.5">min length (s)</p>
                                <input
                                    type="number" min="5" max="172" step="1"
                                    value={clipMinSeconds}
                                    onChange={(e) => setClipMinSeconds(e.target.value)}
                                    placeholder="15"
                                    className="input-field"
                                />
                            </div>
                            <div>
                                <p className="eyebrow mb-1.5">max length (s)</p>
                                <input
                                    type="number" min="10" max="177" step="1"
                                    value={clipMaxSeconds}
                                    onChange={(e) => setClipMaxSeconds(e.target.value)}
                                    placeholder="60"
                                    className="input-field"
                                />
                            </div>
                            <p className="col-span-1 sm:col-span-3 text-[11px] leading-relaxed text-muted">
                                Targets, not guarantees: the AI returns fewer clips when the
                                material doesn't hold them. Leave blank to let it decide.
                            </p>
                            <div className="col-span-1 sm:col-span-3 flex flex-wrap items-center justify-between gap-3 pt-3 sm:pt-1 border-t border-rule">
                                <span className="text-xs text-ink2">vertical layout</span>
                                <select
                                    value={layout}
                                    onChange={(e) => setLayout(e.target.value)}
                                    className="input-field !w-auto text-xs py-1.5"
                                    aria-label="vertical layout"
                                >
                                    <option value="auto">Auto (AI picks per video)</option>
                                    <option value="split">Two speakers stacked</option>
                                    <option value="screencast">Screen over presenter</option>
                                    <option value="none">Single crop only</option>
                                </select>
                            </div>
                            <div className="col-span-1 sm:col-span-3 flex flex-wrap items-center justify-between gap-3 pt-3 sm:pt-1 border-t border-rule">
                                <label className="flex items-center gap-2 text-xs text-ink2 cursor-pointer select-none">
                                    <input
                                        type="checkbox"
                                        checked={autoHook}
                                        onChange={(e) => setAutoHook(e.target.checked)}
                                        className="w-4 h-4 shrink-0 accent-[var(--color-accent)] cursor-pointer"
                                    />
                                    auto hook titles on clips
                                </label>
                                {autoHook && (
                                    <select
                                        value={autoHookStyle}
                                        onChange={(e) => setAutoHookStyle(e.target.value)}
                                        className="input-field !w-auto text-xs py-1.5"
                                    >
                                        <option value="pill">Pills</option>
                                        <option value="classic">Classic</option>
                                        <option value="dark">Dark</option>
                                        <option value="yellow">Yellow</option>
                                        <option value="red">Red</option>
                                        <option value="outline">Outline</option>
                                        <option value="outline_yellow">Outline+</option>
                                    </select>
                                )}
                                {autoHook && (
                                    <p className="w-full text-[11px] leading-relaxed text-muted">
                                        You can change each clip&apos;s hook text, style, position and size
                                        afterwards with its hook button.
                                    </p>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                <label className="flex items-start gap-2.5 mt-5 text-left text-[13px] sm:text-xs leading-relaxed text-muted cursor-pointer select-none">
                    <input
                        type="checkbox"
                        checked={acknowledged}
                        onChange={(e) => setAcknowledged(e.target.checked)}
                        className="mt-0.5 w-4 h-4 shrink-0 accent-[var(--color-accent)] cursor-pointer"
                    />
                    <span>
                        I confirm I own this content or have the rights to process it. I am responsible for any content I submit. See our <a href="/terms" target="_blank" rel="noopener noreferrer" className="text-ink2 underline underline-offset-2 hover:text-brass transition-colors" onClick={(e) => e.stopPropagation()}>Terms</a> and <a href="/privacy" target="_blank" rel="noopener noreferrer" className="text-ink2 underline underline-offset-2 hover:text-brass transition-colors" onClick={(e) => e.stopPropagation()}>Privacy Policy</a>.
                    </span>
                </label>

                <button
                    type="submit"
                    data-tutorial="generate"
                    disabled={isProcessing || !acknowledged || !!lengthError
                        || (genre === 'cricket' ? !cricketMatch.trim() : (!url || !youtubeUrlEnabled))}
                    className="w-full btn-primary mt-4"
                >
                    {isProcessing ? (
                        <>
                            <Loader2 size={16} className="animate-spin" />
                            Processing Video...
                        </>
                    ) : (
                        <>
                            Generate Clips
                        </>
                    )}
                </button>
            </form>
        </div>
    );
}
