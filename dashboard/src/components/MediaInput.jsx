import React, { useState, useEffect, useRef } from 'react';
import { Link2, Info, Loader2, ChevronDown, Plus, X } from 'lucide-react';
import { getApiUrl } from '../config';

const SUPPORTED_PLATFORMS = [
    'YouTube', 'Vimeo', 'TikTok', 'X / Twitter', 'Twitch',
    'Facebook', 'Instagram', 'Dailymotion', 'Reddit', 'Streamable',
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
    const [showInfo, setShowInfo] = useState(false);
    // Advanced generation controls — empty string means "let the AI decide",
    // which keeps the default pipeline behavior untouched.
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [targetClips, setTargetClips] = useState('');
    const [clipMinSeconds, setClipMinSeconds] = useState('');
    const [clipMaxSeconds, setClipMaxSeconds] = useState('');
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

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!acknowledged) return;
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
        };
        try {
            localStorage.setItem('os_caption_script', captionScript);
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
                YouTube link
            </div>

            <form onSubmit={handleSubmit}>
                {!youtubeUrlEnabled && (
                    <p className="text-sm text-danger mb-3" role="alert">
                        Video links are disabled on this server (DISABLE_YOUTUBE_URL).
                    </p>
                )}
                {(
                    <div className="space-y-4" data-tutorial="drop-zone">
                        <div className="relative">
                            <input
                                type="url"
                                value={url}
                                onChange={(e) => setUrl(e.target.value)}
                                placeholder="https://... paste a video link"
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

                        {extraUrls.map((u, i) => (
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
                        {extraUrls.length < 4 && (
                            <button
                                type="button"
                                onClick={() => setExtraUrls((list) => [...list, ''])}
                                className="flex items-center gap-1.5 text-xs lowercase text-muted hover:text-brass transition-colors"
                            >
                                <Plus size={14} /> add another link to combine into one short
                            </button>
                        )}
                        {extraUrls.some((u) => u.trim()) && (
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
                    <p className="eyebrow mb-2">Output format</p>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
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
                    </div>
                    {outputFormat === 'framed' && (
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
                            <div className="flex flex-wrap items-center gap-2">
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
                            </div>
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
                <div className="mt-4 flex flex-wrap items-center gap-2">
                    <span className="eyebrow mr-1">number of shorts</span>
                    {['', '3', '5', '8', '10'].map((n) => (
                        <button
                            key={n || 'auto'}
                            type="button"
                            onClick={() => setTargetClips(n)}
                            className={`px-3 py-1.5 rounded-input border text-xs ${targetClips === n ? 'border-[color:var(--color-accent)] text-ink' : 'border-rule2 text-muted hover:border-[color:var(--color-accent)]'}`}
                        >
                            {n || 'Auto (best)'}
                        </button>
                    ))}
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2">
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
                    <span className="text-[11px] text-muted">titles use the same language · clips stay under 2 min</span>
                </div>

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
                                    type="number" min="5" max="114" step="1"
                                    value={clipMinSeconds}
                                    onChange={(e) => setClipMinSeconds(e.target.value)}
                                    placeholder="15"
                                    className="input-field"
                                />
                            </div>
                            <div>
                                <p className="eyebrow mb-1.5">max length (s)</p>
                                <input
                                    type="number" min="10" max="119" step="1"
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
                    disabled={isProcessing || !acknowledged || !url || !youtubeUrlEnabled}
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
