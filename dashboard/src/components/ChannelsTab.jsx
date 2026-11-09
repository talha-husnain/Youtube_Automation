import React, { useCallback, useEffect, useState } from 'react';
import {
    Loader2, Youtube, Plus, Play, Trash2, LogOut, Layers, X, Copy, Check, ExternalLink, Rocket, AlertTriangle,
    Trophy, Brain, Music, HelpCircle, Flame, Landmark, BookOpen, Share2, Coins, Ghost, Cat,
} from 'lucide-react';
import { apiJson } from '../lib/api';
import { getApiUrl } from '../config';
import ChannelKit from './ChannelKit';
import UpNext from './UpNext';
import RecentUploads from './RecentUploads';

// Every YouTube channel Shortkaar runs (GET /api/my-channels, my_channels.py):
// the main one (comedy, set up in Autopilot) and the others, each with its
// own Google connection, kind of Short, number a day and posting times.

const KIND_ICON = { comedy: Rocket, cricket: Trophy, quiz: HelpCircle, music: Music, controversy: Flame, history: Landmark, quran: BookOpen, money: Coins, toons: Cat };
// The Quran channel (quran_videos.py): what is on screen and which translation is read out.
const QURAN_SCREENS = [['both', 'Arabic, Urdu and English'], ['urdu', 'Arabic and Urdu'], ['english', 'Arabic and English']];
const QURAN_VOICES = [['urdu', 'Urdu'], ['english', 'English'], ['off', 'none (recitation only)']];
// Long videos (history_videos.py): minutes per video. Over 15 needs a phone-verified channel.
const MINUTES = [2, 3, 5, 8, 10, 12, 15, 20, 25, 30];
const STATUS = { running: 'making', done: 'waiting to upload', uploaded: 'uploaded', failed: 'failed', skipped: 'skipped' };
const PUBLISH_STEPS = `1. Open console.cloud.google.com and pick your Shortkaar project.
2. Go to: APIs & Services > OAuth consent screen (Google Auth Platform > Audience).
3. Under "Publishing status" press "Publish app", then confirm.
4. Back in Shortkaar (Channels tab), press "reconnect" once on each channel.`;

const when = (iso) => {
    if (!iso) return '';
    const d = typeof iso === 'number' ? new Date(iso * 1000) : new Date(iso);
    return d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
};

function CopyBox({ text }) {
    const [copied, setCopied] = useState(false);
    return (
        <div className="relative">
            <pre className="text-[11px] leading-relaxed text-ink2 bg-paper rounded-input border border-rule p-3 pr-10 whitespace-pre-wrap break-words">{text}</pre>
            <button onClick={async () => {
                try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1400); } catch { /* ignore */ }
            }} aria-label="copy steps" className="absolute top-2 right-2 p-1.5 text-muted hover:text-brass">
                {copied ? <Check size={14} className="text-ok" /> : <Copy size={14} />}
            </button>
        </div>
    );
}

function Times({ times, onChange, max }) {
    const [t, setT] = useState('');
    return (
        <div className="flex flex-wrap items-center gap-2">
            {times.map((x) => (
                <span key={x} className="inline-flex items-center gap-1 pl-3 pr-1 py-1 rounded-full border border-rule2 text-xs text-ink2">
                    {x}
                    <button onClick={() => onChange(times.filter((y) => y !== x))} aria-label={`remove ${x}`}
                        disabled={times.length <= 1} className="p-0.5 text-muted hover:text-danger"><X size={13} /></button>
                </span>
            ))}
            {times.length < max && (
                <>
                    <input type="time" value={t} onChange={(e) => setT(e.target.value)} className="input-field !w-auto text-xs py-1" aria-label="new posting time" />
                    <button onClick={() => t && !times.includes(t) && onChange([...times, t].sort())} className="btn-ghost px-2.5 py-1 text-xs">
                        <Plus size={13} /> add time
                    </button>
                </>
            )}
        </div>
    );
}

function Connection({ ch }) {
    const yt = ch.youtube || {};
    const connectUrl = getApiUrl(`/api/youtube/connect?back=${encodeURIComponent(window.location.origin)}`
        + (ch.main ? '' : `&channel=${encodeURIComponent(ch.id)}`));
    if (yt.connected && yt.channel) {
        return (
            <div className="flex items-center gap-3 min-w-0">
                {yt.channel.thumbnail && <img src={yt.channel.thumbnail} alt="" className="h-9 w-9 rounded-full shrink-0" />}
                <div className="min-w-0">
                    <p className="text-sm text-ink truncate">{yt.channel.title} <span className="text-muted">{yt.channel.handle}</span></p>
                    <p className="text-xs text-muted">{yt.channel.subscribers} subscribers · connected</p>
                </div>
                {/* A new sign-in replaces the token; nothing is revoked first. */}
                {yt.expires && <a href={connectUrl} className="btn-ghost px-3 py-1.5 text-xs shrink-0"><Youtube size={13} /> reconnect</a>}
            </div>
        );
    }
    if (!yt.configured) return <p className="text-xs text-warn">Set up YouTube first in My channel.</p>;
    return (
        <div className="space-y-1.5">
            <a href={connectUrl} className="btn-primary px-4 py-2 text-sm inline-flex"><Youtube size={15} /> connect youtube channel</a>
            {!ch.main && (
                <p className="text-[11px] text-muted leading-relaxed">
                    On Google&apos;s screen, pick the channel for {ch.name}. It starts making Shorts once it is connected.
                </p>
            )}
        </div>
    );
}

// my_channels.hand_over: no Google account left for a new channel, so this card takes another card's channel.
// That card is retired (its files kept in state/retired), its videos stay on YouTube.
function TakeOver({ ch, others, onChanged }) {
    const [from, setFrom] = useState('');
    const [sure, setSure] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    if (!others.length) return null;
    const picked = others.find((o) => o.id === from);
    const go = async () => {
        setBusy(true);
        setError('');
        try {
            await apiJson(`/api/my-channels/${ch.id}/take-over`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ from }),
            });
            await onChanged();
        } catch (e) {
            setError(e.detail || 'That did not work. Try again.');
        } finally {
            setBusy(false);
            setSure(false);
        }
    };
    return (
        <div className="space-y-1.5 text-xs text-ink2">
            <div className="flex flex-wrap items-center gap-2">
                or use the channel of
                <select value={from} onChange={(e) => { setFrom(e.target.value); setSure(false); }}
                    className="input-field !w-auto text-xs py-1" aria-label="take over the channel of">
                    <option value="">pick a card</option>
                    {others.map((o) => <option key={o.id} value={o.id}>{o.name} ({o.youtube?.channel?.title})</option>)}
                </select>
                {picked && !sure && <button onClick={() => setSure(true)} className="btn-ghost px-3 py-1.5 text-xs">use it</button>}
            </div>
            {picked && sure && (
                <div className="rounded-xl border border-warn/40 p-3 space-y-2">
                    <p>
                        {picked.youtube?.channel?.title} will post {ch.name} videos from now on, and the {picked.name} card
                        stops (its files are kept). Its old videos stay on YouTube.
                    </p>
                    <div className="flex gap-2">
                        <button onClick={go} disabled={busy} className="btn-primary px-3 py-1.5 text-xs">
                            {busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} yes, move it
                        </button>
                        <button onClick={() => setSure(false)} className="btn-ghost px-3 py-1.5 text-xs">cancel</button>
                    </div>
                </div>
            )}
            {error && <p className="text-danger" role="alert">{error}</p>}
        </div>
    );
}

function TookOver({ ch, save }) {
    const t = ch.took_over;
    if (!t) return null;
    const title = ch.youtube?.channel?.title || t.yt_title;
    const renamed = title && title.trim() === ch.name.trim();
    return (
        <div className="space-y-1 text-xs leading-relaxed">
            {!renamed && (
                <p className="text-warn">
                    This channel was {t.from} until {new Date(t.at * 1000).toLocaleDateString()}. In YouTube Studio
                    (Customization &gt; Profile) rename &quot;{title}&quot; to &quot;{ch.name}&quot;, pick a matching handle and
                    change the picture; the About text changes by itself.
                </p>
            )}
            {!t.hide && (
                <button onClick={() => save({ hide_old: true })} className="btn-ghost px-3 py-1.5 text-xs">
                    set the old {t.from} videos to private
                </button>
            )}
            {t.hide && !t.hide_done && (
                <p className="text-muted">
                    Setting the old {t.from} videos and playlists to private, a few at a time
                    {t.hidden ? ` (${t.hidden} done, ${t.hide_left} to go)` : ''}.
                </p>
            )}
            {t.hide_done && <p className="text-muted">The old {t.from} videos are private (YouTube Studio can make any public again).</p>}
        </div>
    );
}

// channel_doctor.py: what holds the channel back, each answer with its evidence; problems first, and what
// is still unknown said as unknown (the REA repo's method, 5-nov-2026).
const DOCTOR_STYLE = {
    problem: ['text-danger', 'problem'], tip: ['text-warn', 'chance'], unknown: ['text-muted', 'not known yet'],
    info: ['text-ink2', 'note'], good: ['text-ok', 'good'],
};

function Doctor({ ch }) {
    const [open, setOpen] = useState(false);
    const [shown, setShown] = useState('');
    const checks = ch.doctor || [];
    if (!checks.length) return null;
    const count = (s) => checks.filter((c) => c.status === s).length;
    const head = [['problem', 'problem'], ['tip', 'chance']].map(([s, w]) => count(s) ? `${count(s)} ${w}${count(s) > 1 ? 's' : ''}` : '')
        .filter(Boolean).join(', ') || 'nothing urgent';
    return (
        <div className="space-y-1.5">
            <button onClick={() => setOpen(!open)} className="text-xs text-ink2 flex items-center gap-1.5" aria-expanded={open}>
                <Brain size={13} /> What holds it back: <span className={count('problem') ? 'text-danger' : 'text-ok'}>{head}</span>
                <span className="text-muted">{open ? 'hide' : 'show'}</span>
            </button>
            {open && (
                <ul className="space-y-1.5">
                    {checks.map((c) => {
                        const [cls, word] = DOCTOR_STYLE[c.status] || DOCTOR_STYLE.info;
                        return (
                            <li key={c.key} className="text-xs leading-relaxed">
                                <p className="text-ink2">
                                    <span className={`${cls} uppercase tracking-wide text-[10px] mr-1.5`}>{word}</span>
                                    {c.question} <span className="text-ink">{c.finding}</span>
                                </p>
                                {c.next && c.status !== 'good' && <p className="text-muted pl-3">{c.next}</p>}
                                {c.evidence?.length > 0 && (
                                    <button onClick={() => setShown(shown === c.key ? '' : c.key)} className="text-muted underline pl-3">
                                        {shown === c.key ? 'hide the evidence' : `evidence (${c.evidence.length})`}
                                    </button>
                                )}
                                {shown === c.key && (
                                    <ul className="pl-3 text-muted">
                                        {c.evidence.map((e, k) => (
                                            <li key={k}>{typeof e === 'string' ? e : <a href={e.url} target="_blank" rel="noreferrer" className="underline">{e.label}</a>}</li>
                                        ))}
                                    </ul>
                                )}
                            </li>
                        );
                    })}
                </ul>
            )}
        </div>
    );
}

// engage.py switches; the main channel has them too (its replies default off:
// the Comments tab drafts them for you to send).
const ENGAGE = [
    ['first_comment', 'first comment with a question when each Short goes live'],
    ['auto_reply', 'reply to new comments (up to 15 a day; the quiz says who got it right)'],
    ['playlists', 'add each Short to a playlist for its kind'],
    ['cross_promo', 'name my other channels in the description ("More from us")'],
    ['podcasts', 'list the long-video playlists as YouTube podcasts (a square cover each, once)', 'long'],
];

function EngageSwitches({ ch, save }) {
    return (
        <div className="space-y-1">
            <p className="text-xs text-muted">
                Engagement after posting{ch.main ? ' (off until you switch them on: they post on your live channel)' : ''}
            </p>
            {ENGAGE.filter(([, , only]) => !only || (only === 'long' && ch.long && !ch.main)).map(([key, label]) => (
                <label key={key} className="flex items-start gap-2 text-xs text-ink2">
                    <input type="checkbox" checked={!!ch[key]} onChange={() => save({ [key]: !ch[key] })} aria-label={key} className="mt-0.5" />
                    {label}
                </label>
            ))}
        </div>
    );
}

// meta_publish.py: the same Shorts on the owner's Facebook Pages and Instagram. Since 5-nov-2026 a short
// wizard: paste the Meta app's keys (checked with Meta, saved to .env, no restart), connect, and every channel
// links itself to the Page named like it (my_channels.auto_link); "check" posts nothing.
const META_GUIDE = 'https://claude.ai/artifact/RDeepUwMHtaGfzbnabLDn4';

function MetaKeys({ meta, onChanged, onDone }) {
    const [form, setForm] = useState({ app_id: '', app_secret: '', config_id: '' });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const save = async () => {
        setBusy(true);
        setError('');
        try {
            await apiJson('/api/meta/keys', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form),
            });
            await onChanged();
            if (onDone) onDone();
        } catch (e) {
            setError(e.detail || 'That did not work. Try again.');
        } finally {
            setBusy(false);
        }
    };
    const field = (key, label, hint, secret) => (
        <label className="block space-y-1">
            <span className="text-xs text-ink2">{label}</span>
            <input type={secret ? 'password' : 'text'} value={form[key]} autoComplete="off" spellCheck={false}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })} className="input-field text-xs py-1.5"
                aria-label={label} />
            <span className="text-[11px] text-muted">{hint}</span>
        </label>
    );
    return (
        <div className="space-y-3 rounded-xl border border-rule2 p-3">
            <p className="text-xs text-ink2">
                Paste the three values from your Meta app (the <a href={META_GUIDE} target="_blank" rel="noreferrer" className="underline">step-by-step guide</a> shows where each one is):
            </p>
            {field('app_id', 'App ID', 'App settings > Basic: the long number at the top.')}
            {field('app_secret', 'App Secret', 'App settings > Basic > App secret > Show (32 letters and digits).', true)}
            {field('config_id', 'Configuration ID', 'Facebook Login for Business > Configurations: the number of the one you made.')}
            <div className="space-y-1">
                <p className="text-xs text-ink2">And in Facebook Login for Business &gt; Settings, add this as a Valid OAuth Redirect URI:</p>
                <CopyBox text={meta.redirect || ''} />
            </div>
            <button onClick={save} disabled={busy || !form.app_id || !form.app_secret} className="btn-primary px-4 py-2 text-sm inline-flex items-center gap-1.5">
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} check and save the keys
            </button>
            {error && <p className="text-xs text-danger" role="alert">{error}</p>}
        </div>
    );
}

function MetaPanel({ meta, onChanged }) {
    const [busy, setBusy] = useState('');
    const [checked, setChecked] = useState(null);
    const [error, setError] = useState('');
    const [editKeys, setEditKeys] = useState(false);
    const hash = window.location.hash || '';
    const err = /meta_error=([^&]*)/.exec(hash);
    if (!meta) return null;
    const run = async (key, path, method = 'POST') => {
        setBusy(key);
        setError('');
        try {
            const got = await apiJson(path, { method });
            if (key === 'check' || key === 'refresh') setChecked(got);
            await onChanged();
        } catch (e) {
            setError(e.detail || 'That did not work. Try again.');
        } finally {
            setBusy('');
        }
    };
    const posted = (meta.queue || []).filter((q) => q.fb?.status === 'posted' || q.ig?.status === 'posted').length;
    const waiting = (meta.queue || []).filter((q) => q.fb?.status === 'pending' || q.ig?.status === 'pending').length;
    const step = !meta.configured ? 1 : !meta.connected ? 2 : 3;
    return (
        <div className="card p-5 space-y-3">
            <p className="text-sm text-ink flex items-center gap-1.5"><Share2 size={15} /> Facebook and Instagram</p>
            <p className="text-xs text-muted leading-relaxed">
                Every Short also goes up as a Reel on its channel&apos;s Facebook Page, and on Instagram, marked as made with AI.
                Cricket gets its own Instagram; Controversy, Money and Horror share one and send it only the Shorts that beat
                their channel on YouTube in their first day. Songs and the Quran go to Facebook only. A new Instagram account
                starts slow: 1 Reel a day in its first week, 2 in the second, then 3.
            </p>
            <ol className="text-xs space-y-1">
                {['Paste the Meta app keys', 'Connect Facebook', 'Check where every channel posts'].map((t, k) => (
                    <li key={t} className={k + 1 < step ? 'text-ok' : k + 1 === step ? 'text-ink' : 'text-muted'}>
                        {k + 1 < step ? <Check size={12} className="inline mr-1" /> : `${k + 1}. `}{t}
                    </li>
                ))}
            </ol>
            {(step === 1 || editKeys) && <MetaKeys meta={meta} onChanged={onChanged} onDone={() => setEditKeys(false)} />}
            {step === 2 && !editKeys && (
                <div className="flex flex-wrap items-center gap-2">
                    <a href={getApiUrl(`/api/meta/connect?back=${encodeURIComponent(window.location.origin)}`)} className="btn-primary px-4 py-2 text-sm inline-flex items-center gap-1.5">
                        <Share2 size={15} /> connect Facebook
                    </a>
                    <button onClick={() => setEditKeys(true)} className="btn-ghost px-3 py-1.5 text-xs">change the keys</button>
                    <span className="text-[11px] text-muted">On Facebook&apos;s screen, tick every Page and Instagram account.</span>
                </div>
            )}
            {step === 3 && (
                <div className="space-y-2">
                    <p className="text-xs text-ok">
                        Connected{meta.user ? ` as ${meta.user}` : ''}: {meta.pages.map((p) => `${p.name}${p.instagram ? ` + Instagram @${p.instagram}` : ''}`).join(', ')}
                    </p>
                    <p className="text-xs text-muted">{waiting} waiting, {posted} posted in the last month.</p>
                    <div className="flex flex-wrap gap-2">
                        <button onClick={() => run('check', '/api/meta/check', 'GET')} disabled={!!busy} className="btn-primary px-3 py-1.5 text-xs inline-flex items-center gap-1">
                            {busy === 'check' ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} check everything
                        </button>
                        <button onClick={() => run('refresh', '/api/meta/refresh')} disabled={!!busy} className="btn-ghost px-3 py-1.5 text-xs">
                            read my Pages again (after linking an Instagram)
                        </button>
                        <button onClick={() => run('off', '/api/meta/disconnect')} disabled={!!busy} className="btn-ghost px-3 py-1.5 text-xs"><LogOut size={13} /> disconnect</button>
                    </div>
                    {checked?.pages && (
                        <ul className="text-xs space-y-0.5">
                            {checked.pages.map((p) => (
                                <li key={p.id} className={p.facebook === 'ok' && p.instagram !== null && p.instagram !== 'ok' ? 'text-warn' : 'text-ink2'}>
                                    {p.name}: Facebook {p.facebook === 'ok' ? 'ready' : p.facebook}
                                    {p.instagram === null ? ', no Instagram linked' : `, Instagram @${p.username} ${p.instagram === 'ok' ? 'ready' : p.instagram}`}
                                </li>
                            ))}
                        </ul>
                    )}
                    {checked?.links && (
                        <table className="text-xs w-full">
                            <thead><tr className="text-muted text-left"><th className="font-normal">Channel</th><th className="font-normal">Facebook Page</th><th className="font-normal">Instagram</th></tr></thead>
                            <tbody>
                                {checked.links.map((l) => (
                                    <tr key={l.card} className="text-ink2">
                                        <td>{l.name}</td><td>{l.page || <span className="text-warn">no Page named like it</span>}</td>
                                        <td>{l.instagram ? `@${l.instagram}` : 'Facebook only'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            )}
            {/meta_connected=1/.test(hash) && <p className="text-xs text-ok">Facebook connected. Press &quot;check everything&quot;.</p>}
            {(err || error) && <p className="text-xs text-danger" role="alert">{error || decodeURIComponent(err[1])}</p>}
            {(err || step === 2) && (
                <p className="text-[11px] text-muted">
                    Facebook said the redirect URI is not allowed?{' '}
                    <button className="underline" onClick={async () => {
                        const host = (meta.redirect || '').includes('127.0.0.1') ? 'localhost' : '127.0.0.1';
                        await apiJson('/api/meta/redirect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ host }) });
                        await onChanged();
                    }}>
                        {`switch to ${(meta.redirect || '').includes('127.0.0.1') ? 'localhost' : '127.0.0.1'}`}
                    </button>{' '}and press connect again (both addresses should be in the app's Valid OAuth Redirect URIs).
                </p>
            )}
        </div>
    );
}

function MetaTarget({ ch, meta, save }) {
    if (!meta?.connected || ch.main) return null;
    const pages = meta.pages || [];
    const page = pages.find((p) => p.id === ch.meta_page);
    const withIg = pages.filter((p) => p.instagram);
    const igPage = pages.find((p) => p.id === (ch.meta_ig_page || ch.meta_page));
    return (
        <div className="flex flex-wrap items-center gap-3 text-xs text-ink2">
            <span className="flex items-center gap-1"><Share2 size={13} /> Facebook Page</span>
            <select value={ch.meta_page || ''} onChange={(e) => save({ meta_page: e.target.value })}
                className="input-field !w-auto text-xs py-1" aria-label={`Facebook Page for ${ch.name}`}>
                <option value="">none</option>
                {pages.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            {page && <label className="flex items-center gap-1"><input type="checkbox" checked={!!ch.meta_fb} onChange={() => save({ meta_fb: !ch.meta_fb })} /> Facebook Reels</label>}
            <label className="flex items-center gap-1">
                <input type="checkbox" checked={!!ch.meta_ig && !!igPage?.instagram} disabled={!withIg.length}
                    onChange={() => save({ meta_ig: !ch.meta_ig })} /> Instagram
            </label>
            {ch.meta_ig && withIg.length > 0 && (
                <select value={ch.meta_ig_page || ''} onChange={(e) => save({ meta_ig_page: e.target.value })}
                    className="input-field !w-auto text-xs py-1" aria-label={`Instagram account for ${ch.name}`}>
                    <option value="">{page?.instagram ? `@${page.instagram} (its Page's)` : 'its Page has none'}</option>
                    {withIg.filter((p) => p.id !== ch.meta_page).map((p) => <option key={p.id} value={p.id}>{`@${p.instagram} (shared)`}</option>)}
                </select>
            )}
            {ch.meta_ig && igPage?.instagram && (
                <select value={ch.meta_ig_mode || 'auto'} onChange={(e) => save({ meta_ig_mode: e.target.value })}
                    className="input-field !w-auto text-xs py-1" aria-label={`which Shorts go to Instagram for ${ch.name}`}>
                    <option value="auto">{`automatic (now: ${ch.meta_ig_now === 'winners' ? 'only YouTube winners' : 'every Short'})`}</option>
                    <option value="all">every Short</option>
                    <option value="winners">only YouTube winners</option>
                </select>
            )}
            {ch.meta_ig && igPage?.instagram && igPage.ig_per_day < 3 && (
                <span className="text-muted">
                    {`new account: ${igPage.ig_per_day} Reel a day${igPage.ig_full_on ? ` until ${new Date(igPage.ig_full_on * 1000).toLocaleDateString()}` : ' for now'}`}
                </span>
            )}
        </div>
    );
}

// The song channel's moods (music_moods.py): every song is made for one, and goes into that mood's playlist.
const OFTEN = [['less', 'less often'], ['normal', 'normal'], ['more', 'more often']];

function MoodPlaylists({ ch, save, onChanged }) {
    const [adding, setAdding] = useState(false);
    const [draft, setDraft] = useState({ name: '', emoji: '', sound: '', themes: '' });
    const [note, setNote] = useState('');
    const [making, setMaking] = useState('');
    const settings = ch.mood_settings || { off: [], often: {}, custom: [] };
    const put = (next) => save({ moods: { ...settings, ...next } });
    const toggle = (key) => put({ off: settings.off.includes(key) ? settings.off.filter((k) => k !== key) : [...settings.off, key] });
    const often = (key, v) => put({ often: { ...settings.often, [key]: v === 'less' ? 1 : v === 'more' ? 4 : 2 } });
    const remove = (key) => put({ custom: settings.custom.filter((c) => c.key !== key), off: settings.off.filter((k) => k !== key) });
    const add = () => {
        if (!draft.name.trim()) return;
        put({ custom: [...settings.custom, { ...draft, themes: draft.themes }] });
        setDraft({ name: '', emoji: '', sound: '', themes: '' });
        setAdding(false);
    };
    const makeNow = async (key, mix = false) => {
        setMaking(mix ? `mix:${key}` : key);
        setNote('');
        try {
            const r = await apiJson(`/api/my-channels/${ch.id}/make`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(mix ? { mix: key } : { mood: key }),
            });
            setNote(r.queued ? r.message : (mix ? 'Making the mix now: about half an hour.' : 'Making it now: it shows under the channel in a few minutes.'));
            await onChanged();
        } catch (e) {
            setNote(e.detail || 'Could not start it. Try again.');
        } finally {
            setMaking('');
        }
    };
    const on = (ch.moods || []).filter((m) => m.on).length;
    return (
        <div className="rounded-input border border-rule p-3 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-ink flex items-center gap-1.5"><Music size={13} /> Moods and playlists</p>
                <span className="text-[11px] text-muted">
                    {on ? `each new song is made for one of ${on} moods and goes into its playlist` : 'all moods off: songs are made as before'}
                    {ch.next_mood && ` · next: ${(ch.moods || []).find((m) => m.key === ch.next_mood)?.name || ch.next_mood}`}
                </span>
            </div>
            <div className="space-y-1.5">
                {(ch.moods || []).map((m) => (
                    <div key={m.key} className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-xs ${m.on ? 'text-ink2' : 'text-muted'}`}>
                        <label className="flex items-center gap-2 min-w-[9rem]">
                            <input type="checkbox" checked={m.on} onChange={() => toggle(m.key)} aria-label={`${m.name} on`} />
                            <span>{m.emoji} {m.name}</span>
                        </label>
                        {m.mix_only ? (
                            <span className="text-[11px] text-muted">mix only · {m.mixes} mix{m.mixes === 1 ? '' : 'es'}</span>
                        ) : (
                            <>
                                <select value={m.often} disabled={!m.on} onChange={(e) => often(m.key, e.target.value)}
                                    className="input-field !w-auto text-xs py-0.5" aria-label={`how often ${m.name}`}>
                                    {OFTEN.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                                </select>
                                <span className="readout text-muted">{m.songs} song{m.songs === 1 ? '' : 's'}{m.mixes ? ` · ${m.mixes} mix${m.mixes === 1 ? '' : 'es'}` : ''}</span>
                            </>
                        )}
                        {m.url ? (
                            <a href={m.url} target="_blank" rel="noreferrer" className="text-brass inline-flex items-center gap-1 hover:underline truncate max-w-[16rem]">
                                {m.playlist} <ExternalLink size={11} />
                            </a>
                        ) : (
                            <span className="text-muted truncate max-w-[16rem]" title="made on YouTube with its first song">{m.playlist}</span>
                        )}
                        {!m.mix_only && (
                            <button disabled={!m.on || !!making} onClick={() => makeNow(m.key)} className="btn-ghost px-2 py-0.5 text-[11px]">
                                {making === m.key ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />} make one now
                            </button>
                        )}
                        <button disabled={!m.on || !!making} onClick={() => makeNow(m.key, true)} className="btn-ghost px-2 py-0.5 text-[11px]"
                            title={(ch.mix_status || {})[m.key] || ''}>
                            {making === `mix:${m.key}` ? <Loader2 size={12} className="animate-spin" /> : <Layers size={12} />} mix now
                        </button>
                        {!m.mix_only && (ch.mix_status || {})[m.key] && (
                            <span className="text-[11px] text-muted">{(ch.mix_status || {})[m.key]}</span>
                        )}
                        {m.custom && (
                            <button onClick={() => remove(m.key)} aria-label={`remove ${m.name}`} className="p-0.5 text-muted hover:text-danger"><Trash2 size={12} /></button>
                        )}
                    </div>
                ))}
            </div>
            {note && <p className="text-[11px] text-ink2">{note}</p>}
            {adding ? (
                <div className="grid gap-2 sm:grid-cols-[6rem_3rem_1fr] text-xs">
                    <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="name" maxLength={40}
                        className="input-field text-xs py-1" aria-label="mood name" />
                    <input value={draft.emoji} onChange={(e) => setDraft({ ...draft, emoji: e.target.value })} placeholder="🎵" maxLength={4}
                        className="input-field text-xs py-1" aria-label="mood emoji" />
                    <input value={draft.sound} onChange={(e) => setDraft({ ...draft, sound: e.target.value })} maxLength={160}
                        placeholder="how it sounds (e.g. Punjabi-style bhangra pop, dhol, 110 BPM)" className="input-field text-xs py-1" aria-label="how it sounds" />
                    <input value={draft.themes} onChange={(e) => setDraft({ ...draft, themes: e.target.value })} maxLength={400}
                        placeholder="what the songs are about, comma separated (e.g. wedding night, mehndi, dancing with cousins)"
                        className="input-field text-xs py-1 sm:col-span-3" aria-label="what the songs are about" />
                    <div className="flex gap-2 sm:col-span-3">
                        <button onClick={add} disabled={!draft.name.trim()} className="btn-primary px-3 py-1 text-xs"><Plus size={13} /> add mood</button>
                        <button onClick={() => setAdding(false)} className="btn-ghost px-3 py-1 text-xs">cancel</button>
                    </div>
                </div>
            ) : (
                (settings.custom || []).length < 8 && (
                    <button onClick={() => setAdding(true)} className="btn-ghost px-2.5 py-1 text-xs"><Plus size={13} /> add your own mood</button>
                )
            )}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink2 pt-1 border-t border-rule">
                <label className="flex items-center gap-2">
                    long mood mixes
                    <select value={(ch.mix_settings || {}).mixes ?? 1} onChange={(e) => put({ mixes: Number(e.target.value) })}
                        className="input-field !w-auto text-xs py-0.5" aria-label="mood mixes a week">
                        {[0, 1, 2, 3].map((n) => <option key={n} value={n}>{n === 0 ? 'off' : `${n} a week`}</option>)}
                    </select>
                </label>
                <label className="flex items-center gap-2">
                    study / sleep mix length
                    <select value={(ch.mix_settings || {}).mix_minutes ?? 30} onChange={(e) => put({ mix_minutes: Number(e.target.value) })}
                        className="input-field !w-auto text-xs py-0.5" aria-label="instrumental mix minutes">
                        {[20, 30, 45, 60].map((n) => <option key={n} value={n}>{n} min</option>)}
                    </select>
                </label>
                <label className="flex items-center gap-2">
                    up to
                    <select value={(ch.mix_settings || {}).mix_budget ?? 1.5} onChange={(e) => put({ mix_budget: Number(e.target.value) })}
                        className="input-field !w-auto text-xs py-0.5" aria-label="instrumental mix budget">
                        {[0, 1, 1.5, 2, 3, 5].map((n) => <option key={n} value={n}>{n === 0 ? '$0 (no study/sleep mixes)' : `$${n}`}</option>)}
                    </select>
                    of new tracks per study / sleep mix
                </label>
            </div>
            <p className="text-[11px] text-muted">Every song also stays in &quot;New AI songs&quot;. Songs made before moods are filed by their style and theme, a few each pass.
                A song mood&apos;s mix uses its uploaded songs that were in no mix yet (8 minutes at least), with lyrics on screen; study and sleep mixes make their own instrumental tracks (about $0.08 each). Never slowed or sped-up copies.</p>
        </div>
    );
}

function ChannelCard({ ch, maxPerDay, onChanged, onOpenAutopilot, meta, others = [] }) {
    const [busy, setBusy] = useState('');
    const [error, setError] = useState('');
    const [sure, setSure] = useState(false);
    const Icon = (ch.kind === 'history' && ch.mode === 'horror') ? Ghost : (KIND_ICON[ch.kind] || Layers);

    const act = async (key, path, options) => {
        setBusy(key);
        setError('');
        try {
            await apiJson(path, options);
            await onChanged();
        } catch (e) {
            setError(e.detail || 'That did not work. Try again.');
        } finally {
            setBusy('');
        }
    };
    const save = (patch) => act('save', `/api/my-channels/${ch.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
    });

    const stats = ch.stats || {};
    const formats = Object.entries(stats.formats || {}).sort((a, b) => b[1].median - a[1].median);
    return (
        <div className="card p-5 space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="text-sm text-ink flex items-center gap-1.5"><Icon size={15} /> {ch.name}</p>
                    <p className="text-xs text-muted">{ch.kind_label}</p>
                </div>
                {ch.main ? (
                    <button onClick={onOpenAutopilot} className="btn-ghost px-3 py-1.5 text-xs"><Rocket size={13} /> settings in Autopilot</button>
                ) : (
                    <label className="flex items-center gap-2 text-xs text-ink2">
                        <input type="checkbox" checked={ch.enabled} onChange={() => save({ enabled: !ch.enabled })} aria-label={`run ${ch.name}`} />
                        make and post by itself
                    </label>
                )}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3">
                <Connection ch={ch} />
                {!ch.main && ch.youtube?.connected && (
                    <button onClick={() => act('disconnect', `/api/my-channels/${ch.id}/disconnect`, { method: 'POST' })}
                        disabled={busy === 'disconnect'} className="btn-ghost px-3 py-1.5 text-xs"><LogOut size={13} /> disconnect</button>
                )}
            </div>
            {!ch.main && ch.youtube?.configured && !ch.youtube?.connected && (
                <TakeOver ch={ch} others={others} onChanged={onChanged} />
            )}
            {!ch.main && ch.youtube?.connected && <TookOver ch={ch} save={save} />}
            {!ch.main && <Doctor ch={ch} />}
            {error && <p className="text-xs text-danger" role="alert">{error}</p>}

            {ch.main ? (
                <>
                    <p className="text-xs text-ink2">
                        {ch.per_day} Shorts a day at {ch.post_times.join(', ')}. Ready to post and Autopilot run this channel as before.
                    </p>
                    <EngageSwitches ch={ch} save={save} />
                </>
            ) : (
                <>
                    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-ink2">
                        <label className="flex items-center gap-2">
                            {ch.long ? 'Videos a day' : 'Shorts a day'}
                            <select value={ch.per_day} onChange={(e) => save({ per_day: Number(e.target.value) })}
                                className="input-field !w-auto text-xs py-1" aria-label={ch.long ? 'videos a day' : 'shorts a day'}>
                                {Array.from({ length: ch.max_per_day || maxPerDay }, (_, k) => k + 1).map((n) => <option key={n} value={n}>{n}</option>)}
                            </select>
                        </label>
                        {ch.kind === 'quran' && ch.quran && (
                            <>
                                <label className="flex items-center gap-2">
                                    qari
                                    <select value={ch.quran.reciter} onChange={(e) => save({ quran: { reciter: Number(e.target.value) } })}
                                        className="input-field !w-auto text-xs py-1" aria-label="qari">
                                        {(ch.quran_options?.reciters || []).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
                                    </select>
                                </label>
                                <label className="flex items-center gap-2">
                                    on screen
                                    <select value={ch.quran.screen} onChange={(e) => save({ quran: { screen: e.target.value } })}
                                        className="input-field !w-auto text-xs py-1" aria-label="on screen">
                                        {QURAN_SCREENS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                                    </select>
                                </label>
                                <label className="flex items-center gap-2">
                                    translation read out
                                    <select value={ch.quran.voice} onChange={(e) => save({ quran: { voice: e.target.value } })}
                                        className="input-field !w-auto text-xs py-1" aria-label="translation read out">
                                        {QURAN_VOICES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                                    </select>
                                </label>
                                <label className="flex items-center gap-2">
                                    Urdu translation
                                    <select value={ch.quran.urdu} onChange={(e) => save({ quran: { urdu: Number(e.target.value) } })}
                                        className="input-field !w-auto text-xs py-1" aria-label="Urdu translation">
                                        {(ch.quran_options?.urdu || []).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
                                    </select>
                                </label>
                            </>
                        )}
                        {ch.kind === 'history' && (
                            <>
                                <label className="flex items-center gap-2">
                                    videos about
                                    <select value={ch.mode || 'history'} onChange={(e) => save({ mode: e.target.value })}
                                        className="input-field !w-auto text-xs py-1" aria-label="videos about">
                                        <option value="explainer">this week&apos;s hot topics, explained</option>
                                        <option value="history">history stories</option>
                                        <option value="horror">horror stories (original fiction)</option>
                                    </select>
                                </label>
                                <label className="flex items-center gap-2">
                                    minutes each
                                    <select value={ch.minutes} onChange={(e) => save({ minutes: Number(e.target.value) })}
                                        className="input-field !w-auto text-xs py-1" aria-label="minutes each">
                                        {MINUTES.map((n) => <option key={n} value={n}>{n}</option>)}
                                    </select>
                                </label>
                                <label className="flex items-center gap-2">
                                    language
                                    <select value={ch.lang} onChange={(e) => save({ lang: e.target.value })}
                                        className="input-field !w-auto text-xs py-1" aria-label="language">
                                        <option value="urdu">Urdu (Roman)</option>
                                        <option value="english">English</option>
                                    </select>
                                </label>
                            </>
                        )}
                        <label className="flex items-center gap-2">
                            <input type="checkbox" checked={ch.auto_upload} onChange={() => save({ auto_upload: !ch.auto_upload })} aria-label="upload by itself" />
                            upload by itself
                        </label>
                        <label className="flex items-center gap-2">
                            handle
                            <input defaultValue={ch.handle} onBlur={(e) => e.target.value !== ch.handle && save({ handle: e.target.value })}
                                placeholder={ch.youtube?.channel?.handle || '@yourchannel'} className="input-field !w-36 text-xs py-1" aria-label="handle" />
                        </label>
                        <label className="flex items-center gap-2">
                            colour
                            <input type="color" value={ch.color} onChange={(e) => save({ color: e.target.value })} className="h-7 w-9 rounded border border-rule bg-transparent" aria-label="colour" />
                        </label>
                    </div>
                    {ch.kind === 'cricket' && (
                        <label className="flex items-start gap-2 text-xs text-ink2">
                            <input type="checkbox" checked={!!ch.match_watch} onChange={() => save({ match_watch: !ch.match_watch })}
                                aria-label="fast match results" className="mt-0.5" />
                            fast results: when Pakistan or India finish a match, make its Short next and post it 20 minutes later (checked every 2 hours)
                        </label>
                    )}
                    {ch.kind === 'quiz' && (
                        <input defaultValue={ch.notes} onBlur={(e) => e.target.value !== ch.notes && save({ notes: e.target.value })}
                            placeholder="Favourite quiz topics, optional (e.g. Pakistan history, science)"
                            className="input-field text-xs py-1.5" aria-label="quiz topics" maxLength={300} />
                    )}
                    {ch.kind === 'money' && (
                        <input defaultValue={ch.notes} onBlur={(e) => e.target.value !== ch.notes && save({ notes: e.target.value })}
                            placeholder="Money topics you want, optional (e.g. Gulf salaries, Pakistan petrol and gold, big company mistakes)"
                            className="input-field text-xs py-1.5" aria-label="money topics" maxLength={300} />
                    )}
                    {ch.kind === 'toons' && (
                        <>
                            <input defaultValue={ch.notes} onBlur={(e) => e.target.value !== ch.notes && save({ notes: e.target.value })}
                                placeholder="Stories you want, optional (e.g. more Guddu episodes, wedding season, the World Cup on TV)"
                                className="input-field text-xs py-1.5" aria-label="cartoon story wishes" maxLength={300} />
                            <label className="flex items-center gap-2 text-xs text-ink2">
                                <input type="checkbox" checked={ch.toon_mix !== false} onChange={() => save({ toon_mix: ch.toon_mix === false })}
                                    aria-label="weekly compilation" />
                                also a weekly long video of the week&apos;s episodes back to back (watch hours for YouTube&apos;s Partner Program)
                            </label>
                        </>
                    )}
                    {ch.kind === 'music' && ch.moods && <MoodPlaylists ch={ch} save={save} onChanged={onChanged} />}
                    {ch.kind === 'quran' && (
                        <p className="text-xs text-ink2">
                            The recitation is always the qari&apos;s own recording (from Quran.com), never an AI voice. The AI voice only reads the translation, after each ayah. No music. Add a surah to &quot;Up next&quot; to make it sooner.
                        </p>
                    )}
                    {ch.kind === 'history' && (
                        <>
                            <input defaultValue={ch.notes} onBlur={(e) => e.target.value !== ch.notes && save({ notes: e.target.value })}
                                placeholder={ch.mode === 'horror'
                                    ? 'Stories you want (e.g. haunted havelis, highways at night, hostels, jinn stories)'
                                    : 'Topics you want (e.g. Rome, Karbala, the Caliphs, the US economy)'}
                                className="input-field text-xs py-1.5" aria-label="history topics" maxLength={300} />
                            {(ch.mode || 'history') === 'history' && (
                                <label className="flex items-center gap-2 text-xs text-ink2">
                                    <input type="checkbox" checked={ch.daily_short !== false} onChange={() => save({ daily_short: ch.daily_short === false })}
                                        aria-label="daily on this day Short" />
                                    also a daily &quot;Aaj ki tareekh&quot; Short (what happened on this date in history), on top of the long videos
                                </label>
                            )}
                            {ch.mode === 'horror' && (
                                <p className="text-xs text-ink2">
                                    Every story is original fiction, said so in each description: dark paintings and footage, a low narrator, no gore.
                                    Each video also gets a teaser Short and two moment Shorts. Horror channels do best with 15-30 minute stories.
                                </p>
                            )}
                            {ch.minutes > 15 && (
                                <p className="text-xs text-warn">
                                    Videos over 15 minutes need a verified channel: switch to this channel on YouTube, open youtube.com/verify and verify with your phone. The same unlocks custom thumbnails.
                                    {['eligible', 'disallowed'].includes(ch.long_uploads?.status) && ' YouTube says this channel is not verified yet, so videos are made 14 minutes long until it is.'}
                                    {ch.long_uploads?.status === 'allowed' && ' YouTube says this channel is verified: the full length is used.'}
                                </p>
                            )}
                        </>
                    )}
                    <div>
                        <p className="text-xs text-muted mb-2">Posting times (every day, this computer&apos;s time)</p>
                        <Times times={ch.post_times} max={ch.max_per_day || maxPerDay} onChange={(t) => save({ post_times: t })} />
                    </div>
                    <label className="flex flex-wrap items-center gap-2 text-xs text-ink2">
                        Hold each new video before it uploads, so you can watch it and skip it:
                        <select value={ch.review_hours || 0} onChange={(e) => save({ review_hours: Number(e.target.value) })}
                            className="input-field !w-auto text-xs py-1" aria-label={`review time for ${ch.name}`}>
                            {[0, 2, 6, 12, 24].map((h) => <option key={h} value={h}>{h ? `${h} hours` : 'no, upload right away'}</option>)}
                        </select>
                        {ch.review_hours > 0 && <span className="text-muted">(match results still go at once; Telegram tells you when one is ready, with a Skip button)</span>}
                    </label>
                    <EngageSwitches ch={ch} save={save} />
                    <MetaTarget ch={ch} meta={meta} save={save} />
                    <ChannelKit ch={ch} />
                    <UpNext ch={ch} onChanged={onChanged} />
                    <RecentUploads ch={ch} />

                    <div className="flex flex-wrap items-center justify-between gap-3 rounded-input border border-rule p-3">
                        <p className="text-xs text-ink2">
                            Today: {ch.made_today} of {ch.per_day} made, {ch.uploaded_today} uploaded, {ch.waiting} waiting to upload.
                            {ch.running?.length > 0 && <span className="text-brass"> Making now: {ch.running[0]}.</span>}
                            {ch.upload_paused_until * 1000 > Date.now() && (
                                <span className="text-warn"> YouTube&apos;s daily upload limit: uploads start again {when(ch.upload_paused_until)}.</span>
                            )}
                        </p>
                        <button onClick={() => act('make', `/api/my-channels/${ch.id}/make`, { method: 'POST' })}
                            disabled={busy === 'make' || ch.running?.length > 0} className="btn-ghost px-3 py-1.5 text-xs">
                            {busy === 'make' ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} make one now
                        </button>
                    </div>

                    {ch.jobs?.length > 0 && (
                        <div className="space-y-1.5">
                            <p className="text-xs text-ink">{ch.long ? 'Latest videos' : 'Latest Shorts'}</p>
                            {ch.jobs.slice(0, 8).map((j) => (
                                <div key={j.job_id || j.at} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
                                    <span className={`readout ${j.status === 'failed' ? 'text-danger' : j.status === 'uploaded' ? 'text-ok' : 'text-muted'}`}>
                                        {STATUS[j.status] || j.status}
                                    </span>
                                    <span className="text-ink2 min-w-0 break-words flex-1">{j.title || j.label}</span>
                                    {j.slot && <span className="text-muted">{when(j.slot)}</span>}
                                    {j.status === 'done' && ch.review_hours > 0 && !j.urgent
                                        && ((j.done_at || j.at) + ch.review_hours * 3600) * 1000 > Date.now() && (
                                        <span className="text-brass">held until {new Date(((j.done_at || j.at) + ch.review_hours * 3600) * 1000)
                                            .toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                                    )}
                                    {j.video_url && (
                                        <a href={getApiUrl(j.video_url)} target="_blank" rel="noreferrer" className="text-brass hover:underline">watch</a>
                                    )}
                                    {j.status === 'done' && (
                                        <button onClick={() => act('skip', `/api/my-channels/${ch.id}/skip/${j.job_id}`, { method: 'POST' })}
                                            disabled={busy === 'skip'} className="text-muted hover:text-danger" aria-label={`skip ${j.title || j.label}`}>skip</button>
                                    )}
                                    {j.video_id && (
                                        <a href={`https://studio.youtube.com/video/${j.video_id}/edit`} target="_blank" rel="noreferrer"
                                            className="text-brass hover:underline inline-flex items-center gap-0.5">Studio <ExternalLink size={11} /></a>
                                    )}
                                    {j.status === 'failed' && j.error && <span className="text-muted w-full">{j.error}</span>}
                                </div>
                            ))}
                        </div>
                    )}

                    {stats.at && (
                        <div className="space-y-1">
                            <p className="text-xs text-ink flex items-center gap-1.5"><Brain size={13} /> What it learned (every 6 hours)</p>
                            <p className="text-xs text-ink2">
                                {stats.tracked} Shorts tracked, {stats.counted} counted (public 2 days), {stats.views} views in all
                                {stats.counted > 0 ? `, median ${stats.median}` : ''}
                                {stats.watched != null ? `, people watch ${stats.watched}% of each on average` : ''}.
                            </p>
                            {formats.length > 1 && (
                                <p className="text-xs text-ink2">{formats.map(([f, v]) => `${f}: median ${v.median}${v.watched != null ? `, ${v.watched}% watched` : ''} (${v.shorts})`).join(' · ')}</p>
                            )}
                            {stats.best?.length > 0 && <p className="text-[11px] text-muted">Best: {stats.best.slice(0, 3).join(' · ')}</p>}
                        </div>
                    )}

                    <div className="flex justify-end">
                        {sure ? (
                            <span className="flex items-center gap-2 text-xs">
                                <span className="text-ink2">Remove {ch.name} from Shortkaar? Its videos stay on YouTube.</span>
                                <button onClick={() => act('remove', `/api/my-channels/${ch.id}`, { method: 'DELETE' })} className="btn-ghost px-2.5 py-1 text-xs text-danger">remove</button>
                                <button onClick={() => setSure(false)} className="btn-ghost px-2.5 py-1 text-xs">keep</button>
                            </span>
                        ) : (
                            <button onClick={() => setSure(true)} className="text-xs text-muted hover:text-danger inline-flex items-center gap-1"><Trash2 size={12} /> remove channel</button>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}

function AddChannel({ kinds, onAdded }) {
    const [kind, setKind] = useState('');
    const [name, setName] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const add = async () => {
        setBusy(true);
        setError('');
        try {
            await apiJson('/api/my-channels', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind, name }),
            });
            setKind('');
            setName('');
            await onAdded();
        } catch (e) {
            setError(e.detail || 'Could not add it.');
        } finally {
            setBusy(false);
        }
    };
    return (
        <div className="card p-5 space-y-3">
            <p className="text-sm text-ink flex items-center gap-1.5"><Plus size={15} /> Add a channel</p>
            <p className="text-xs text-muted leading-relaxed">
                Make the new channel on YouTube first (YouTube app or studio.youtube.com: your picture &gt; Settings &gt; Add or manage channels &gt; Create a channel). Then add it here and connect it.
            </p>
            <div className="grid gap-2 sm:grid-cols-3">
                {Object.entries(kinds).map(([k, v]) => {
                    const Icon = KIND_ICON[k] || Layers;
                    return (
                        <button key={k} onClick={() => { setKind(k); setName(v.label); }}
                            className={`text-left rounded-input border p-3 space-y-1 ${kind === k ? 'border-brass' : 'border-rule hover:border-rule2'}`}>
                            <span className="text-sm text-ink flex items-center gap-1.5"><Icon size={14} /> {v.label}</span>
                            <span className="block text-[11px] text-muted leading-relaxed">{v.about}</span>
                        </button>
                    );
                })}
            </div>
            {kind && (
                <div className="flex flex-wrap items-center gap-2">
                    <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} aria-label="channel name"
                        className="input-field flex-1 min-w-[12rem] text-sm py-1.5" />
                    <button onClick={add} disabled={busy || !name.trim()} className="btn-primary px-4 py-2 text-sm">
                        {busy ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />} add channel
                    </button>
                </div>
            )}
            {error && <p className="text-xs text-danger" role="alert">{error}</p>}
        </div>
    );
}

export default function ChannelsTab({ notice, onOpenAutopilot }) {
    const [data, setData] = useState(null);
    const [meta, setMeta] = useState(null);
    const [error, setError] = useState('');

    const load = useCallback(() => Promise.all([
        apiJson('/api/my-channels').then((d) => { setData(d); setError(''); })
            .catch((e) => setError(e.detail || 'Could not load your channels.')),
        apiJson('/api/meta/status').then(setMeta).catch(() => setMeta(null)),
    ]), []);
    useEffect(() => { load(); }, [load]);
    // While a Short is being made, follow it.
    const busy = (data?.channels || []).some((c) => c.running?.length > 0);
    useEffect(() => {
        if (!busy) return undefined;
        const t = setInterval(load, 15000);
        return () => clearInterval(t);
    }, [busy, load]);

    if (!data) {
        return <div className="card p-5 text-sm text-muted">{error || <><Loader2 size={14} className="animate-spin inline" /> loading…</>}</div>;
    }
    const expiring = data.channels.filter((c) => c.youtube?.expires);
    const soonest = expiring.reduce((m, c) => (m && m < c.youtube.expires ? m : c.youtube.expires), 0);
    return (
        <div className="space-y-4 max-w-4xl">
            <div className="card p-5 space-y-2">
                <p className="text-sm text-ink flex items-center gap-1.5"><Layers size={15} /> Your channels</p>
                <p className="text-xs text-muted leading-relaxed">
                    Each channel has its own YouTube connection, its own kind of Short and its own posting times. Shortkaar makes them one at a time while this computer is on, and uploads each one into the channel&apos;s next free time. YouTube publishes them at that time, even when the computer is off.
                </p>
                {data.channels.some((c) => !c.main && !c.youtube?.connected) && (
                    <a href={getApiUrl(`/api/youtube/connect-all?back=${encodeURIComponent(window.location.origin)}`)} className="btn-primary px-4 py-2 text-sm inline-flex items-center gap-1.5">
                        <Youtube size={15} /> connect all channels
                    </a>
                )}
                {notice?.connected && <p className="text-xs text-ok">Connected.</p>}
                {notice?.error && <p className="text-xs text-danger" role="alert">{notice.error}</p>}
            </div>

            {expiring.length > 0 && (
                <div className="card p-5 space-y-2 border-warn">
                    <p className="text-sm text-warn flex items-center gap-1.5"><AlertTriangle size={15} /> Your Google connection stops working {soonest ? `around ${when(soonest)}` : 'after 7 days'}</p>
                    <p className="text-xs text-ink2 leading-relaxed">
                        Your Google project is still in &quot;Testing&quot;, and Google ends those sign-ins 7 days after you connect. Change it to &quot;In production&quot; once and reconnect each channel, and it keeps working. Nothing is listed anywhere, and only someone with your project&apos;s keys can use it:
                    </p>
                    <CopyBox text={PUBLISH_STEPS} />
                    <p className="text-[11px] text-muted">Google may show &quot;Google hasn&apos;t verified this app&quot; when you connect: press Advanced, then Go to your project. It is your own app.</p>
                </div>
            )}

            <MetaPanel meta={meta} onChanged={load} />

            {data.channels.map((ch) => (
                <ChannelCard key={ch.id} ch={ch} maxPerDay={data.max_per_day} onChanged={load} onOpenAutopilot={onOpenAutopilot} meta={meta}
                    others={data.channels.filter((o) => !o.main && o.id !== ch.id && o.youtube?.connected)} />
            ))}
            <AddChannel kinds={data.kinds} onAdded={load} />
        </div>
    );
}
