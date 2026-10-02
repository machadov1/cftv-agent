// Primitivas da Mesa de Despacho: cantos retos, traço pesado, cor por estado e por unidade

const TONE_TEXT = {
  ok: 'text-ok', warn: 'text-warn', bad: 'text-bad', accent: 'text-accent', mute: 'text-mute', mock: 'text-mock',
};
const TONE_BG = {
  ok: 'bg-ok', warn: 'bg-warn', bad: 'bg-bad', accent: 'bg-accent', mute: 'bg-mute', mock: 'bg-mock',
};
const TONE_BADGE = {
  ok: 'text-ok border-ok bg-ok/10',
  warn: 'text-warn border-warn bg-warn/10',
  bad: 'text-bad border-bad bg-bad/10',
  accent: 'text-accent border-accent bg-accent/10',
  mute: 'text-mute border-line bg-panel2',
  mock: 'text-mock border-mock bg-mock/10',
};

export const toneText = (t) => TONE_TEXT[t] ?? TONE_TEXT.mute;

// Uma cor por unidade (todas legíveis com texto branco). Serve de tira no ticket e de série nos gráficos.
const UNIT_COLORS = {
  'Piracicaba': '#1636e0',
  'Resende': '#d9480f',
  'Barra Mansa': '#0b6b3a',
  'Juiz de Fora': '#7c2d9c',
  'Jaboatão': '#00796b',
  'João Monlevade': '#b45309',
  'Bauru': '#c2185b',
  'Sabará': '#4d7c0f',
  'Guarulhos': '#0369a1',
  'Candeias': '#9a3412',
  'Iracemápolis': '#166534',
  'Vega do Sul': '#1d4ed8',
  'Rio das Pedras': '#6d28d9',
  'Tubarão': '#0f766e',
  'Igarapé': '#57534e',
  'Projects (monitoramento)': '#374151',
  'Serra Azul': '#7f1d1d',
  'Pecém': '#0e7490',
};
export const NO_UNIT_COLOR = '#8a857a';

export function unitColor(localidade) {
  if (!localidade) return NO_UNIT_COLOR;
  const base = localidade.replace(/\s*\(LORA\)/i, '').trim();
  return UNIT_COLORS[base] ?? NO_UNIT_COLOR;
}

export function Dot({ tone = 'mute', pulse = false }) {
  return (
    <span className={`inline-block h-2.5 w-2.5 ${TONE_BG[tone]} ${pulse ? 'pulse-dot' : ''}`} />
  );
}

export function Badge({ tone = 'mute', children, title }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 border px-1.5 py-px font-mono text-[12.5px] font-bold uppercase tracking-[0.08em] ${TONE_BADGE[tone]}`}
    >
      {children}
    </span>
  );
}

export function Panel({ title, right, children, className = '', bodyClass = '' }) {
  return (
    <section className={`border-2 border-rule bg-panel ${className}`}>
      {(title || right) && (
        <header className="flex items-center justify-between border-b-2 border-rule bg-panel2 px-3 py-2">
          <h2 className="font-mono text-[13.75px] font-bold uppercase tracking-[0.14em] text-mute">{title}</h2>
          {right}
        </header>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

export function Kpi({ label, value, unit, tone = 'ink', hint }) {
  const color = tone === 'ink' ? 'text-ink' : toneText(tone);
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1 border-r-2 border-rule px-4 py-2.5 last:border-r-0">
      <span className={`font-display text-4xl font-extrabold leading-[0.9] tracking-tight tabular-nums ${color}`}>
        {value}
        {unit && <span className="ml-0.5 text-lg font-bold text-mute">{unit}</span>}
      </span>
      <span className="truncate font-mono text-[12.5px] font-bold uppercase tracking-[0.12em] text-ink">{label}</span>
      {hint && <span className="truncate font-mono text-[12.5px] text-mute">{hint}</span>}
    </div>
  );
}

export function ConfBar({ value = 0, showValue = true }) {
  const tone = value >= 70 ? 'ok' : value > 0 ? 'warn' : 'bad';
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-14 bg-line">
        <div className={`h-full ${TONE_BG[tone]}`} style={{ width: `${Math.max(value, 4)}%` }} />
      </div>
      {showValue && <span className={`font-mono text-[13.75px] font-bold tabular-nums ${toneText(tone)}`}>{value}%</span>}
    </div>
  );
}

export function Button({ tone = 'default', className = '', ...props }) {
  const styles = {
    default: 'border-rule bg-panel text-ink hover:bg-invert hover:text-invert-ink',
    primary: 'border-accent bg-accent text-white hover:opacity-85',
    ok: 'border-ok bg-ok text-white hover:opacity-85',
    bad: 'border-bad bg-bad text-white hover:opacity-85',
  };
  return (
    <button
      {...props}
      className={`border-2 px-3 py-1.5 font-display text-xs font-bold uppercase tracking-wide transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${styles[tone]} ${className}`}
    />
  );
}

export const inputClass =
  'w-full border-2 border-rule bg-panel px-2.5 py-1.5 text-xs text-ink placeholder:text-mute focus:outline-2 focus:outline-accent';

// created_at do SQLite vem em UTC sem fuso
export function parseUtc(s) {
  return s ? new Date(s.replace(' ', 'T') + 'Z') : null;
}

export function timeAgo(s) {
  const d = parseUtc(s);
  if (!d) return '—';
  const sec = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 86400)}d`;
}

export function statusTone(status) {
  return { aprovado: 'ok', analisado: 'warn', tratado_fora: 'mute', encerrado: 'mute' }[status] ?? 'mute';
}

// nome da etapa na tela (o status interno continua o mesmo no banco)
export function statusLabel(status) {
  return { analisado: 'entrada', aprovado: 'despachado', tratado_fora: 'fora do agente', encerrado: 'encerrado' }[status] ?? status;
}
