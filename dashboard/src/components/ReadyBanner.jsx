import React, { useEffect, useState } from 'react';
import { Send } from 'lucide-react';
import { apiJson } from '../lib/api';

// One line on Make Shorts when Shorts wait in Ready to post (post_queue.py),
// so a morning after Autopilot starts with "4 Shorts ready to post".
export default function ReadyBanner({ onOpen }) {
    const [summary, setSummary] = useState(null);
    useEffect(() => {
        let alive = true;
        apiJson('/api/queue/summary').then((d) => { if (alive) setSummary(d); }).catch(() => {});
        return () => { alive = false; };
    }, []);
    if (!summary?.ready) return null;
    return (
        <button type="button" onClick={onOpen}
            className="w-full card px-4 py-2.5 flex items-center justify-center gap-2 text-sm text-ink2 hover:text-brass transition-colors">
            <Send size={15} className="text-brass" />
            {summary.ready} {summary.ready === 1 ? 'Short is' : 'Shorts are'} ready to post
            {summary.autopilot ? ` (${summary.autopilot} from Autopilot)` : ''}
        </button>
    );
}
