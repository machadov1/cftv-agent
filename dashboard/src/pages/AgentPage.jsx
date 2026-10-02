import { useCallback, useEffect, useRef, useState } from 'react';
import { agentChat, approveIncident } from '../api';
import { Button } from '../components/ui';
import { HOLD_MS } from '../components/HoldButton';

const LABEL = 'font-mono text-[12.5px] font-bold uppercase tracking-[0.14em] text-mute';
const EXEMPLOS = [
  'Trate o novo incidente que foi aberto na fila de Piracicaba',
  'Quais incidentes da fila LORA vencem hoje?',
  'Consulte o INC4003560 e me diga para onde ele vai',
];

// Reduz o print antes de enviar (menos tokens, mais rápido); mantém legível para OCR
function shrink(file, max = 1600) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * k);
      c.height = Math.round(img.height * k);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(img.src);
      resolve(c.toDataURL('image/png'));
    };
    img.onerror = reject;
    img.src = URL.createObjectURL(file);
  });
}

// Segurar para confirmar (mesmo gesto do Despachar)
function HoldButton({ onDone, disabled, children }) {
  const bar = useRef(null);
  const raf = useRef(0);
  const t0 = useRef(0);
  const stop = () => { cancelAnimationFrame(raf.current); if (bar.current) bar.current.style.width = '0'; };
  const tick = () => {
    const p = Math.min((performance.now() - t0.current) / HOLD_MS, 1);
    if (bar.current) bar.current.style.width = `${p * 100}%`;
    if (p >= 1) { stop(); onDone(); return; }
    raf.current = requestAnimationFrame(tick);
  };
  const start = () => { if (disabled) return; t0.current = performance.now(); raf.current = requestAnimationFrame(tick); };
  useEffect(() => stop, []);
  return (
    <button
      disabled={disabled}
      onMouseDown={start} onMouseUp={stop} onMouseLeave={stop} onTouchStart={start} onTouchEnd={stop}
      onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !e.repeat) { e.preventDefault(); start(); } }}
      onKeyUp={stop}
      className={`relative overflow-hidden px-4 py-2 text-left font-display text-sm font-extrabold uppercase tracking-wide ${
        disabled ? 'cursor-not-allowed bg-panel2 text-mute' : 'bg-invert text-invert-ink hover:opacity-90'
      }`}
    >
      {children}
      <span className="block font-mono text-[11.25px] font-normal normal-case tracking-[0.1em] opacity-75">mantenha pressionado</span>
      <span ref={bar} className="absolute bottom-0 left-0 h-1 w-0 bg-bad" />
    </button>
  );
}

function ActionCard({ action }) {
  const [res, setRes] = useState({});
  const [busy, setBusy] = useState(false);
  const prontos = action.itens.filter((i) => i.ok);

  const executar = async () => {
    setBusy(true);
    for (const i of prontos) {
      if (res[i.numero]?.ok) continue;
      try {
        const r = await approveIncident(i.numero, {});
        setRes((x) => ({ ...x, [i.numero]: { ok: true, txt: r.dry_run ? 'simulado (dry-run)' : 'gravado' } }));
      } catch (e) {
        setRes((x) => ({ ...x, [i.numero]: { ok: false, txt: e.message } }));
      }
    }
    setBusy(false);
  };
  const feito = prontos.length > 0 && prontos.every((i) => res[i.numero]?.ok);

  return (
    <div className="mt-2 border-2 border-rule bg-panel">
      <div className="flex items-center justify-between border-b-2 border-rule px-3 py-1.5">
        <span className={LABEL}>Proposta · primeira tratativa · {prontos.length} de {action.itens.length} prontos</span>
      </div>
      <div className="divide-y divide-line">
        {action.itens.map((i) => (
          <div key={i.numero} className="grid grid-cols-[110px_1fr_auto] items-center gap-3 px-3 py-2 text-xs">
            <span className="font-mono font-bold text-accent">{i.numero}</span>
            <span className="min-w-0">
              {i.ok ? (
                <>
                  <span className="block truncate font-semibold">{i.titulo}</span>
                  <span className="font-mono text-[13.75px] text-ok">→ {i.fila}</span>
                  {i.avisos?.map((w) => <span key={w} className="block font-mono text-[12.5px] text-warn">! {w}</span>)}
                </>
              ) : (
                <span className="font-semibold text-bad">{i.motivo}</span>
              )}
            </span>
            <span className={`font-mono text-[12.5px] font-bold ${res[i.numero]?.ok ? 'text-ok' : 'text-bad'}`}>{res[i.numero]?.txt}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-3 border-t-2 border-rule p-2">
        <HoldButton onDone={executar} disabled={busy || feito || prontos.length === 0}>
          {feito ? 'Despachado' : busy ? 'Enviando…' : `Despachar ${prontos.length} incidente(s)`}
        </HoldButton>
        <span className="font-mono text-[12.5px] text-mute">Passa pelas mesmas checagens do botão Despachar (dry-run, duplicidade).</span>
      </div>
    </div>
  );
}

function Trace({ trace }) {
  if (!trace?.length) return null;
  return (
    <details className="mt-2 border border-line bg-panel2 text-[13.75px]">
      <summary className="cursor-pointer px-2 py-1 font-mono text-mute">{trace.length} etapa(s) do agente</summary>
      <div className="space-y-1.5 p-2">
        {trace.map((s, k) => (
          <div key={k} className="font-mono">
            {s.tipo === 'visao' ? (
              <>
                <div className="font-bold text-mock">print lido por {s.modelo} ({Math.round(s.ms / 100) / 10}s)</div>
                <pre className="whitespace-pre-wrap text-mute">{s.texto}</pre>
              </>
            ) : (
              <>
                <div className="font-bold">{s.nome}({JSON.stringify(s.args)})</div>
                <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-mute">{JSON.stringify(s.resultado, null, 1).slice(0, 1500)}</pre>
              </>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}

export default function AgentPage() {
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState('');
  const [imgs, setImgs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const endRef = useRef(null);
  const fileRef = useRef(null);

  // Carregar histórico de conversas ao montar
  useEffect(() => {
    try {
      const saved = localStorage.getItem('agentHistory');
      if (saved) setMsgs(JSON.parse(saved));
    } catch (e) {
      console.error('Erro ao recuperar histórico do agente:', e);
    }
  }, []);

  // Salvar histórico quando mudar
  useEffect(() => {
    try {
      localStorage.setItem('agentHistory', JSON.stringify(msgs));
    } catch (e) {
      console.error('Erro ao salvar histórico do agente:', e);
    }
  }, [msgs]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs, busy]);

  const addFiles = useCallback(async (files) => {
    const list = [...files].filter((f) => f.type.startsWith('image/')).slice(0, 6);
    if (!list.length) return;
    try {
      const urls = await Promise.all(list.map((f) => shrink(f)));
      setImgs((x) => [...x, ...urls].slice(0, 6));
    } catch { setErr('Não consegui ler a imagem.'); }
  }, []);

  useEffect(() => {
    const onPaste = (e) => { if (e.clipboardData?.files?.length) addFiles(e.clipboardData.files); };
    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
  }, [addFiles]);

  const send = async (t = text) => {
    const content = t.trim();
    if ((!content && !imgs.length) || busy) return;
    const user = { role: 'user', content: content || 'Veja o print.', images: imgs };
    const next = [...msgs, user];
    setMsgs(next);
    setText('');
    setImgs([]);
    setErr(null);
    setBusy(true);
    try {
      const r = await agentChat(next.map(({ role, content: c }) => ({ role, content: c })), user.images);
      setMsgs((m) => [...m, { role: 'assistant', content: r.reply, trace: r.trace, actions: r.actions, meta: r }]);
    } catch (e) {
      setErr(e.message);
    }
    setBusy(false);
  };

  return (
    <div
      className="grid h-full min-h-0 grid-rows-[1fr_auto]"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => { e.preventDefault(); addFiles(e.dataTransfer.files); }}
    >
      <div className="min-h-0 overflow-auto px-4 py-4">
        <div className="mx-auto max-w-4xl space-y-4">
          {msgs.length === 0 && (
            <div className="border-2 border-rule bg-panel p-5">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-display text-3xl font-extrabold uppercase leading-none">Agente CFTV</div>
                  <p className="mt-2 max-w-2xl text-sm text-mute">
                    Peça em texto ou cole um print (Ctrl+V) da fila do ServiceNow. O agente consulta o ServiceNow só para ler e devolve uma
                    proposta; nada é gravado sem você confirmar.
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {EXEMPLOS.map((e) => (
                  <button key={e} onClick={() => send(e)} className="border-2 border-rule px-3 py-1.5 text-left text-xs font-semibold hover:bg-invert hover:text-invert-ink">
                    {e}
                  </button>
                ))}
              </div>
            </div>
          )}

          {msgs.map((m, k) => (
            <div key={k} className={m.role === 'user' ? 'ml-auto max-w-[80%]' : 'max-w-full'}>
              <div className={`${LABEL} mb-1 ${m.role === 'user' ? 'text-right' : ''}`}>
                {m.role === 'user' ? 'Você' : `Agente${m.meta?.model ? ` · ${m.meta.model}` : ''}${m.meta?.ms ? ` · ${Math.round(m.meta.ms / 100) / 10}s` : ''}`}
              </div>
              <div className={`border-2 border-rule px-3 py-2 text-sm leading-relaxed ${m.role === 'user' ? 'bg-invert text-invert-ink' : 'bg-panel'}`}>
                {m.images?.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-2">
                    {m.images.map((u, i) => <img key={i} src={u} alt={`print ${i + 1}`} className="h-24 border border-line object-cover" />)}
                  </div>
                )}
                <div className="whitespace-pre-wrap">
                  {m.content.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
                    part.startsWith('**') && part.endsWith('**') ? <strong key={i}>{part.slice(2, -2)}</strong> : part)}
                </div>
              </div>
              {m.actions?.map((a, i) => <ActionCard key={i} action={a} />)}
              <Trace trace={m.trace} />
            </div>
          ))}

          {busy && <div className={`${LABEL} animate-pulse`}>o agente está consultando…</div>}
          {err && <div className="border-2 border-bad bg-bad/10 px-3 py-2 text-xs font-bold text-bad">{err}</div>}
          <div ref={endRef} />
        </div>
      </div>

      <div className="border-t-2 border-rule bg-panel px-4 py-3">
        <div className="mx-auto max-w-4xl">
          {msgs.length > 0 && (
            <div className="mb-2 text-right">
              <button
                onClick={() => { if (confirm('Limpar histórico da conversa?')) setMsgs([]); }}
                className="font-mono text-[12.5px] text-mute hover:text-ink"
              >
                Limpar histórico
              </button>
            </div>
          )}
          {imgs.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {imgs.map((u, i) => (
                <div key={i} className="relative">
                  <img src={u} alt={`anexo ${i + 1}`} className="h-16 border-2 border-rule object-cover" />
                  <button
                    onClick={() => setImgs((x) => x.filter((_, j) => j !== i))}
                    aria-label="Remover imagem"
                    className="absolute -right-2 -top-2 h-5 w-5 bg-bad text-xs font-bold text-white"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="flex items-end gap-2">
            <label className="sr-only" htmlFor="agent-input">Pedido ao agente</label>
            <textarea
              id="agent-input"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
              rows={2}
              placeholder="Ex.: trate os incidentes do print · Enter envia, Shift+Enter quebra linha · Ctrl+V cola print"
              className="min-h-[52px] flex-1 resize-y border-2 border-rule bg-panel px-3 py-2 text-sm text-ink placeholder:text-mute focus:outline-2 focus:outline-accent"
            />
            <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={(e) => { addFiles(e.target.files); e.target.value = ''; }} />
            <Button onClick={() => fileRef.current?.click()} className="h-[52px]">Anexar print</Button>
            <Button tone="primary" onClick={() => send()} disabled={busy || (!text.trim() && !imgs.length)} className="h-[52px] px-6">
              {busy ? '…' : 'Enviar'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
