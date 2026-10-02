import { useCallback, useEffect, useMemo, useState } from 'react';
import { processIncident, getIncidents, getSaida, getIncident, getMockIncidents, getSyncStatus, syncQueue, approveIncident, refreshPendentes } from '../api';
import IncidentDetail from '../components/IncidentDetail';
import HoldButton from '../components/HoldButton';
import LoadingSpinner from '../components/LoadingSpinner';
import { Badge, Button, inputClass, timeAgo, unitColor } from '../components/ui';

// Entrada = aguarda primeira tratativa (Novo na AMS-TI-CFTV, sem nota minha). Saída = já saiu da Entrada nas
// últimas 24 h: despachado pelo agente ou tratado direto no ServiceNow ("fora do agente").
const ENTRADA = (i) => i.status === 'analisado';
const FILTERS = [
  { id: 'entrada', label: 'Entrada', test: ENTRADA },
  { id: 'nodest', label: 'Sem destino', test: (i) => ENTRADA(i) && !i.grupo },
  { id: 'saida', label: 'Saída · 24h', test: (i) => i.status === 'aprovado' || i.status === 'tratado_fora' },
];

const ago = (epoch) => {
  if (!epoch) return '—';
  const s = Math.max(0, Math.round(Date.now() / 1000 - epoch));
  return s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)}m` : `${Math.floor(s / 3600)}h`;
};

// despachável em lote: pendente, com destino e título no padrão (os demais pedem revisão individual)
const batchable = (i) => i.status === 'analisado' && !!i.grupo && i.titulo_ok !== false;

function Ticket({ i, active, checked, onClick }) {
  const done = i.status === 'aprovado' || i.status === 'tratado_fora';
  const fora = i.status === 'tratado_fora';
  const conf = i.localidade_confianca ?? 0;
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`grid w-full select-none grid-cols-[52px_1fr_auto] border-b border-line text-left transition-colors ${
        active ? 'bg-invert text-invert-ink' : 'hover:!bg-bg'
      } ${done && !active ? 'opacity-60' : ''} ${checked ? 'outline outline-2 -outline-offset-2 outline-accent' : ''}`}
    >
      {/* picote na cor da unidade */}
      <div className="flex items-center justify-center border-r border-dashed border-current" style={{ background: unitColor(i.localidade) }}>
        <span className="rotate-180 font-mono text-[13.75px] font-bold tracking-[0.12em] text-white [writing-mode:vertical-rl]">
          {i.incident_number.slice(3)}
        </span>
      </div>
      <div className="min-w-0 px-3.5 py-3">
        <div className="font-mono text-xs font-bold text-bad">
          {checked && <span className="mr-1.5 bg-accent px-1 text-white">✓</span>}
          {i.incident_number}
        </div>
        <div className="my-0.5 truncate font-display text-[19px] font-bold leading-tight" title={`Original: ${i.short_description}`}>
          {i.titulo_padrao ?? i.short_description}
        </div>
        <div className={`truncate font-mono text-[13.75px] uppercase tracking-wide ${active ? 'opacity-70' : 'text-mute'}`}>
          {fora ? `agora em ${i.sn_grupo || '—'}${i.nota_autor ? ` · nota de ${i.nota_autor.split(',')[0]}` : ''}` : (
            <>
              {i.localidade ?? 'sem localidade'}
              {i.grupo_display && ` → ${i.grupo_display}`}
              {i.camera_codigo && ` · ${i.camera_codigo}`}
            </>
          )}
        </div>
        {i.opened_at && (
          <div className="mt-1 font-mono text-[12.5px] text-mute">
            {i.caller_id && <span>{i.caller_id} · </span>}
            {new Date(i.opened_at).toLocaleString('pt-BR', { timeZone: 'UTC', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
          </div>
        )}
      </div>
      <div className="flex flex-col items-end justify-between px-3.5 py-3 text-right">
        <span className={`font-display text-3xl font-extrabold leading-none tabular-nums ${conf >= 70 ? '' : conf > 0 ? 'text-warn' : 'text-bad'}`}>
          {conf}%
        </span>
        <div className="flex items-center gap-1.5 font-mono text-[12.5px]">
          {!!i.acesso && <span className="font-bold text-accent">ACESSO</span>}
          {!!i.a4 && <span className="font-bold text-[#8B5CF6]">A4 · {i.a4}</span>}
          {!!i.ritm_necessaria && <span className="font-bold text-warn">RITM</span>}
          {fora ? (
            <span className="border border-current px-1 font-bold uppercase text-mute">fora do agente</span>
          ) : done ? (
            <span className="border border-current px-1 font-bold uppercase text-ok">despachado</span>
          ) : !i.grupo ? (
            <span className="border border-bad bg-bad px-1 font-bold uppercase text-white">bloqueado</span>
          ) : (
            <span className={active ? 'opacity-70' : 'text-mute'}>{timeAgo(i.updated_at)}</span>
          )}
        </div>
      </div>
    </button>
  );
}

export default function IncidentsPage() {
  const [number, setNumber] = useState('');
  const [rows, setRows] = useState(null);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [meta, setMeta] = useState(null);
  const [filter, setFilter] = useState('entrada');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [mocks, setMocks] = useState([]);
  const [sync, setSync] = useState(null);
  const [syncBusy, setSyncBusy] = useState(false);
  const [reread, setReread] = useState(null); // { busy } | { text, ok }

  const loadRows = useCallback(
    () => Promise.all([getIncidents(100), getSaida()])
      .then(([entrada, saida]) => setRows([...entrada, ...saida]))
      .catch((e) => setError(e.message)),
    []
  );
  const loadDetail = useCallback((n) => getIncident(n).then(setDetail).catch(() => setDetail(null)), []);

  useEffect(() => {
    loadRows();
    getMockIncidents().then(setMocks).catch(() => {});
    const id = setInterval(loadRows, 10000);
    return () => clearInterval(id);
  }, [loadRows]);

  useEffect(() => {
    const poll = () => getSyncStatus().then(setSync).catch(() => {});
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, []);

  // a busca em segundo plano trouxe algo novo: recarrega a fila
  useEffect(() => { if (sync?.last_run) loadRows(); }, [sync?.last_run, loadRows]);

  const runSync = async () => {
    setSyncBusy(true);
    try { setSync(await syncQueue()); } catch (e) { setError(e.message); }
    setSyncBusy(false);
  };

  // relê no ServiceNow todos os pendentes (Número do Objeto, texto, destino): título com o código da câmera
  const runReread = async () => {
    setReread({ busy: true });
    try {
      const r = await refreshPendentes();
      setReread({ ok: !r.erros.length, text: `${r.relidos} relido(s) · ${r.mudaram.length} atualizado(s)${r.sairam?.length ? ` · ${r.sairam.length} já tratado(s) foram para a Saída` : ''}${r.erros.length ? ` · ${r.erros.length} erro(s)` : ''}`,
        title: r.erros.join('\n') });
      await loadRows();
      if (selected) loadDetail(selected);
    } catch (e) { setReread({ ok: false, text: e.message }); }
  };

  useEffect(() => {
    if (selected) loadDetail(selected);
  }, [selected, loadDetail]);

  const run = async (n = number) => {
    const target = n.trim().toUpperCase();
    if (!target) return;
    setBusy(true);
    setError(null);
    try {
      const r = await processIncident(target);
      setMeta({ chamou_claude: r.chamou_claude, tempo_ms: r.tempo_ms });
      if (r.aviso) setError(r.aviso);
      setFilter(r.status === 'analisado' ? 'entrada' : 'saida');
      setSelected(target);
      await loadDetail(target);
      await loadRows();
      setNumber('');
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };

  const onChanged = () => { loadRows(); if (selected) loadDetail(selected); };

  const shown = useMemo(() => {
    const f = FILTERS.find((x) => x.id === filter);
    return (rows ?? []).filter(f.test);
  }, [rows, filter]);

  // seleção em lote: Shift+clique = faixa a partir do último clique, Ctrl+clique = alterna um
  const [sel, setSel] = useState(() => new Set());
  const [anchor, setAnchor] = useState(null);
  const [batch, setBatch] = useState(null); // { running, done, total, ok, falhas[], dry }

  const pickable = useMemo(() => shown.filter(batchable), [shown]);
  const chosen = useMemo(() => (rows ?? []).filter((r) => sel.has(r.incident_number) && batchable(r)), [rows, sel]);

  const onTicket = (e, i, idx) => {
    if (e.shiftKey || e.ctrlKey || e.metaKey) {
      e.preventDefault();
      window.getSelection()?.removeAllRanges();
      const next = new Set(sel);
      if (e.shiftKey && anchor != null) {
        const [a, b] = [Math.min(anchor, idx), Math.max(anchor, idx)];
        shown.slice(a, b + 1).filter(batchable).forEach((r) => next.add(r.incident_number));
      } else if (batchable(i)) {
        next.has(i.incident_number) ? next.delete(i.incident_number) : next.add(i.incident_number);
      }
      setSel(next);
      setAnchor(idx);
      return;
    }
    setSelected(i.incident_number);
    setAnchor(idx);
  };

  const dispatchBatch = async () => {
    const list = chosen.map((r) => r.incident_number);
    if (!list.length || batch?.running) return;
    const res = { running: true, done: 0, total: list.length, ok: [], falhas: [], dry: false };
    setBatch({ ...res });
    for (const n of list) {
      try {
        const r = await approveIncident(n);
        res.ok.push(n);
        res.dry = res.dry || !!r.dry_run;
      } catch (err) {
        res.falhas.push(`${n}: ${err.message}`);
      }
      res.done += 1;
      setBatch({ ...res });
    }
    res.running = false;
    setBatch({ ...res });
    setSel((s) => { const next = new Set(s); res.ok.forEach((n) => next.delete(n)); return next; });
    await loadRows();
    if (selected) loadDetail(selected);
  };

  const counts = useMemo(
    () => Object.fromEntries(FILTERS.map((f) => [f.id, (rows ?? []).filter(f.test).length])),
    [rows]
  );

  return (
    <div className="grid h-full min-h-0 grid-cols-1 xl:grid-cols-[minmax(380px,1fr)_minmax(520px,1.15fr)]">
      {/* Fila */}
      <div className="flex min-h-0 flex-col border-rule xl:border-r-2">
        <div className="shrink-0 space-y-2.5 border-b-2 border-rule p-3">
          <div className="flex gap-2">
            <input
              value={number}
              onChange={(e) => setNumber(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === 'Enter' && run()}
              placeholder="INC3997102"
              spellCheck={false}
              aria-label="Número do incidente"
              className={`${inputClass} font-mono text-sm tracking-wide`}
            />
            <Button tone="primary" onClick={() => run()} disabled={busy || !number.trim()} className="shrink-0 px-5">
              {busy ? 'Consultando…' : 'Processar'}
            </Button>
          </div>
          <div className="flex items-center justify-between gap-2 border-t border-line pt-2.5">
            <span className={`min-w-0 truncate font-mono text-[13.75px] ${sync?.erro ? 'font-bold text-bad' : 'text-mute'}`} title={sync?.erro ?? ''}>
              {!sync ? '…'
                : sync.erro ? sync.erro
                : sync.last_ok
                  ? `Fila AMS-TI-CFTV · buscada há ${ago(sync.last_ok)} · ${sync.novos.length} novo(s)${sync.sairam?.length ? ` · ${sync.sairam.length} saiu(ram) para a Saída` : ''}${sync.ignorados.length ? ` · ${sync.ignorados.length} fora de CFTV` : ''}${sync.auto ? ` · auto ${sync.intervalo_s}s` : ''}`
                  : 'Fila AMS-TI-CFTV · ainda não buscada'}
            </span>
            <div className="flex shrink-0 gap-2">
              <Button onClick={runReread} disabled={reread?.busy || !counts.entrada}
                title="Confere a Entrada no ServiceNow (só leitura): o que já foi tratado vai para a Saída; o resto é relido">
                {reread?.busy ? 'Relendo…' : 'Reler Entrada'}
              </Button>
              <Button onClick={runSync} disabled={syncBusy || sync?.running}>
                {syncBusy || sync?.running ? 'Buscando…' : 'Buscar fila'}
              </Button>
            </div>
          </div>
          {reread?.text && (
            <div className={`font-mono text-[13.75px] ${reread.ok ? 'text-ok' : 'text-bad'}`} title={reread.title}>{reread.text}</div>
          )}
          {error && <div className="text-xs font-semibold text-bad">{error}</div>}
          {mocks.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge tone="mock">cenários mock</Badge>
              {mocks.map((m) => (
                <button
                  key={m.incident_number}
                  onClick={() => run(m.incident_number)}
                  title={m.short_description}
                  className="border border-line bg-panel2 px-1.5 py-0.5 font-mono text-[13.75px] text-mute transition-colors hover:border-mock hover:text-mock"
                >
                  {m.incident_number.slice(-3)} · {m.short_description.slice(0, 22)}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex shrink-0 border-b-2 border-rule bg-panel2" role="tablist" aria-label="Filtros da fila">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              role="tab"
              aria-selected={filter === f.id}
              onClick={() => setFilter(f.id)}
              className={`flex-1 border-r border-line px-2 py-2 font-display text-xs font-bold uppercase tracking-wide last:border-r-0 ${
                filter === f.id ? 'bg-invert text-invert-ink' : 'text-ink hover:bg-panel2'
              }`}
            >
              {f.label} <span className="font-mono">{counts[f.id]}</span>
            </button>
          ))}
        </div>

        {chosen.length > 0 || batch ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2 border-b-2 border-rule bg-panel2 px-3 py-2">
            <div className="min-w-0 flex-1 font-mono text-[13.75px]">
              {batch?.running ? (
                <span className="font-bold">Despachando {batch.done}/{batch.total}…</span>
              ) : chosen.length > 0 ? (
                <span><b>{chosen.length}</b> selecionado(s)</span>
              ) : null}
              {batch && !batch.running && (
                <div className={batch.falhas.length ? 'text-bad' : 'text-ok'} title={batch.falhas.join('\n')}>
                  {batch.ok.length} despachado(s){batch.dry ? ' (simulado: dry-run)' : ''}
                  {batch.falhas.length > 0 && ` · ${batch.falhas.length} falha(s): ${batch.falhas[0]}`}
                </div>
              )}
            </div>
            {chosen.length > 0 && !batch?.running && (
              <>
                <Button onClick={() => { setSel(new Set()); setBatch(null); }}>Limpar</Button>
                <HoldButton onDone={dispatchBatch} hint="mantenha pressionado">Despachar {chosen.length}</HoldButton>
              </>
            )}
            {batch && !batch.running && chosen.length === 0 && <Button onClick={() => setBatch(null)}>Ok</Button>}
          </div>
        ) : pickable.length > 1 ? (
          <div className="flex shrink-0 items-center justify-between gap-2 border-b border-line px-3 py-1.5 font-mono text-[12.5px] text-mute">
            <span>Shift+clique: faixa · Ctrl+clique: alterna · despacha em lote</span>
            <button onClick={() => setSel(new Set(pickable.map((r) => r.incident_number)))} className="font-bold uppercase underline">
              selecionar {pickable.length} prontos
            </button>
          </div>
        ) : null}

        <div className="zebra min-h-0 flex-1 overflow-auto">
          {!rows ? (
            <LoadingSpinner />
          ) : shown.length === 0 ? (
            <div className="p-10 text-center">
              <div className="font-display text-2xl font-extrabold uppercase">{filter === 'saida' ? 'Nada saiu hoje' : 'Fila limpa'}</div>
              <p className="mt-1 text-mute">{filter === 'saida' ? 'Nenhum despacho nem tratativa nas últimas 24 h.' : 'Nenhum incidente aguardando primeira tratativa.'}</p>
            </div>
          ) : (
            shown.map((i, idx) => (
              <Ticket key={i.id} i={i} active={selected === i.incident_number} checked={sel.has(i.incident_number)}
                onClick={(e) => onTicket(e, i, idx)} />
            ))
          )}
        </div>
      </div>

      {/* Decisão */}
      <div className="min-h-0 border-t-2 border-rule xl:border-t-0">
        <IncidentDetail incident={detail} meta={selected === detail?.incident_number ? meta : null} onChanged={onChanged} />
      </div>
    </div>
  );
}
