// Shortkaar themes (the variables live in tokens.css).
export const THEMES = [
    { id: 'aurora', label: 'Aurora', from: '#8B5CF6', to: '#EC4899' },
    { id: 'ocean', label: 'Ocean', from: '#22D3EE', to: '#3B82F6' },
    { id: 'sunset', label: 'Sunset', from: '#FF6B4A', to: '#F7B538' },
    { id: 'mint', label: 'Mint', from: '#34E3A6', to: '#14B8C4' },
];
export const THEME_KEY = 'shortkaar_theme';

export function applySavedTheme() {
    try {
        // ?theme=ocean picks a theme from the address bar (and remembers it).
        const fromUrl = new URLSearchParams(window.location.search).get('theme');
        if (fromUrl && THEMES.some((x) => x.id === fromUrl)) localStorage.setItem(THEME_KEY, fromUrl);
        const t = localStorage.getItem(THEME_KEY);
        if (t && t !== 'aurora') document.documentElement.dataset.theme = t;
    } catch { /* ignore */ }
}
