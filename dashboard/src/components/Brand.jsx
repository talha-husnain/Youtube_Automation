import React, { useEffect, useId, useState } from 'react';
import { THEMES, THEME_KEY } from '../lib/theme';

// Shortkaar brand pieces: the logo (coloured by the active theme) and the
// theme picker. The themes themselves live in tokens.css.

export function Logo({ size = 36, className = '' }) {
    const id = useId().replace(/:/g, '');
    return (
        <svg width={size} height={size} viewBox="0 0 64 64" className={className} aria-hidden="true">
            <defs>
                <linearGradient id={`sk-${id}`} x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0" style={{ stopColor: 'var(--color-accent)' }} />
                    <stop offset="1" style={{ stopColor: 'var(--color-accent-2)' }} />
                </linearGradient>
            </defs>
            <rect width="64" height="64" rx="16" fill={`url(#sk-${id})`} />
            <rect x="21" y="10" width="22" height="44" rx="6" fill="var(--color-paper)" />
            <path d="M28.5 24.5 L38.5 32 L28.5 39.5 Z" fill={`url(#sk-${id})`} />
            <rect x="28" y="46" width="8" height="2.5" rx="1.25" fill="var(--color-ink)" opacity="0.6" />
        </svg>
    );
}

export function Wordmark({ className = '' }) {
    return (
        <span className={`font-display lowercase tracking-tight ${className}`}>
            short<span className="text-gradient">kaar</span>
        </span>
    );
}

export function ThemePicker({ compact = false }) {
    const [theme, setTheme] = useState(() => {
        try { return localStorage.getItem(THEME_KEY) || 'aurora'; } catch { return 'aurora'; }
    });
    useEffect(() => {
        if (theme === 'aurora') delete document.documentElement.dataset.theme;
        else document.documentElement.dataset.theme = theme;
        try { localStorage.setItem(THEME_KEY, theme); } catch { /* ignore */ }
    }, [theme]);
    return (
        <div className={`flex items-center gap-2 ${compact ? 'justify-center' : ''}`}>
            {!compact && <span className="text-[11px] lowercase text-muted mr-1">theme</span>}
            {THEMES.map((t) => (
                <button
                    key={t.id}
                    type="button"
                    onClick={() => setTheme(t.id)}
                    title={t.label}
                    aria-label={`${t.label} theme`}
                    aria-pressed={theme === t.id}
                    className={`w-5 h-5 rounded-full transition-transform hover:scale-110 ${theme === t.id ? 'ring-2 ring-offset-2 ring-offset-[var(--color-paper-2)] ring-[var(--color-ink)]' : ''}`}
                    style={{ background: `linear-gradient(135deg, ${t.from}, ${t.to})` }}
                />
            ))}
        </div>
    );
}
