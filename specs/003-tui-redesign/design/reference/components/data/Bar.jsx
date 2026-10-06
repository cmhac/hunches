import React from 'react';

const PARTS = ['', '▏', '▎', '▍', '▌', '▋', '▊', '▉'];

export function Bar({ value = 0, max = 1, width = 20, color = 'var(--bar-color, var(--primary))', track = true }) {
  const eighths = Math.max(0, Math.min(width * 8, Math.round((value / (max || 1)) * width * 8)));
  const full = Math.floor(eighths / 8);
  const part = PARTS[eighths % 8];
  const used = full + (part ? 1 : 0);
  return (
    <span style={{ whiteSpace: 'pre' }}>
      <span style={{ display: 'inline-block', width: full + 'ch', height: '0.8em', verticalAlign: '-0.08em', background: color }}></span>
      <span style={{ color }}>{part}</span>
      {track ? <span style={{ color: 'var(--bar-track, var(--ink-4))' }}>{'─'.repeat(Math.max(0, width - used))}</span> : null}
    </span>
  );
}
