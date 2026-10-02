import { useEffect, useRef } from 'react';

export const HOLD_MS = 450;

// Segurar para confirmar: gesto deliberado, evita clique acidental num botão que grava no ServiceNow
export default function HoldButton({ onDone, disabled, children, hint = 'mantenha pressionado', ms = HOLD_MS, className = '' }) {
  const bar = useRef(null);
  const raf = useRef(0);
  const t0 = useRef(0);
  const cb = useRef(onDone);
  cb.current = onDone;

  const stop = () => { cancelAnimationFrame(raf.current); if (bar.current) bar.current.style.width = '0'; };
  const tick = () => {
    const p = Math.min((performance.now() - t0.current) / ms, 1);
    if (bar.current) bar.current.style.width = `${p * 100}%`;
    if (p >= 1) { stop(); cb.current(); return; }
    raf.current = requestAnimationFrame(tick);
  };
  const start = () => { if (disabled) return; t0.current = performance.now(); raf.current = requestAnimationFrame(tick); };
  useEffect(() => () => cancelAnimationFrame(raf.current), []);

  return (
    <button
      disabled={disabled}
      onMouseDown={start} onMouseUp={stop} onMouseLeave={stop} onTouchStart={start} onTouchEnd={stop} onBlur={stop}
      onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !e.repeat) { e.preventDefault(); start(); } }}
      onKeyUp={stop}
      className={`relative overflow-hidden px-4 py-2 text-left font-display text-sm font-extrabold uppercase tracking-wide ${
        disabled ? 'cursor-not-allowed bg-panel2 text-mute' : 'bg-invert text-invert-ink hover:opacity-90'
      } ${className}`}
    >
      {children}
      {hint && <span className="block font-mono text-[11.25px] font-normal normal-case tracking-[0.1em] opacity-75">{hint}</span>}
      <span ref={bar} className="absolute bottom-0 left-0 h-1 w-0 bg-bad" />
    </button>
  );
}
