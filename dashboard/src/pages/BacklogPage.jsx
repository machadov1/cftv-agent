import { useCallback, useEffect, useMemo, useState } from 'react';
import { closeIncident, getBacklog } from '../api';
import CameraPanel from '../components/CameraPanel';
import HoldButton from '../components/HoldButton';
import LoadingSpinner from '../components/LoadingSpinner';
import RitmPanel from '../components/RitmPanel';
import { Button, NO_UNIT_COLOR, unitColor } from '../components/ui';

const LABEL = 'font-mono text-[12.5px] font-bold uppercase tracking-[0.14em] text-mute';
const snLink = (n) => `https://amamericas.service-now.com/nav_to.do?uri=incident.do%3Fsysparm_query%3Dnumber%3D${n}`;

// Tratar um incidente do backlog sem sair da tela: os mesmos painéis da Operação (teste de câmera -> print ->
// work note/encerrar, RITM) e o Encerrar (segurar). Tudo lido/gravado direto no ServiceNow, respeitando o dry-run.
function Tratar({ r, onFechar, onEncerrado }) {
  const [nota, setNota] = useState('');
  const [fim, setFim] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const esc = (e) => e.key === 'Escape' && onFechar();
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [onFechar]);

  const encerrar = async () => {
    setBusy(true);
    try {
      const res = await closeIncident(r.number, nota.trim());
      setFim(res);
      if (!res.simulado) onEncerrado();
    } catch (e) { setFim({ erro: e.message }); }
    setBusy(false);
  };
  const novo = r.status === 'Novo';

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={onFechar}>
      <aside className="flex h-full w-full max-w-[760px] flex-col border-l-4 border-rule bg-bg shadow-[-6px_0_0_var(--c-rule)]"
        onClick={(e) => e.stopPropagation()}>
        <header className="flex items-start gap-3 border-b-2 border-rule bg-panel px-5 py-3"
          style={{ borderLeft: `8px solid ${teamColor(r.equipe)}` }}>
          <div className="min-w-0 flex-1">
            <a href={snLink(r.number)} target="_blank" rel="noreferrer" className="font-mono text-[13.75px] font-bold text-accent hover:underline">
              {r.number}
            </a>
            <span className="ml-2 font-mono text-[12.5px] text-mute">{r.status} · {r.grupo} · {r.prazo_txt}</span>
            <div className="mt-0.5 font-display text-xl font-extrabold leading-tight">{r.titulo}</div>
          </div>
          <Button onClick={onFechar}>Fechar</Button>
        </header>
        <div className="min-h-0 flex-1 overflow-auto">
          {novo && (
            <p className="border-b-2 border-rule px-5 py-2 font-mono text-[12.5px] font-bold text-warn">
              Ainda Novo: a primeira tratativa é pela Operação (Entrada). O encerramento só vale depois dela.
            </p>
          )}
          <CameraPanel number={r.number} />
          <div className="border-b-2 border-rule px-5 py-3">
            <RitmPanel key={r.number} incident={{ incident_number: r.number }} />
          </div>
          <div className="px-5 py-3">
            <div className={LABEL}>Encerramento</div>
            <p className="mt-1 text-xs text-mute">
              Resolve no ServiceNow (estado Resolvido, código Solved) com este texto como nota de encerramento e work note.
            </p>
            <textarea value={nota} onChange={(e) => setNota(e.target.value)} rows={4} disabled={fim?.sucesso && !fim.simulado}
              placeholder="Causa raiz: … / Resolução: … / Encerramento: Incidente encerrado."
              className="mt-2 w-full border-2 border-rule bg-panel px-2 py-1.5 font-mono text-[13.75px]" />
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <HoldButton onDone={encerrar} disabled={busy || !nota.trim() || novo || (fim?.sucesso && !fim.simulado)}
                className="border-l-8 border-bad">
                {busy ? 'Encerrando…' : 'Encerrar (Resolvido)'}
              </HoldButton>
              {fim?.erro && <span className="font-mono text-[12.5px] font-bold text-bad">{fim.erro}</span>}
              {fim?.sucesso && (
                <span className={`font-mono text-[12.5px] font-bold ${fim.simulado ? 'text-warn' : 'text-ok'}`}>{fim.mensagem}</span>
              )}
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}

const TEAM_UNIT = { JDF: 'Juiz de Fora', MDE: 'João Monlevade', PIR: 'Piracicaba', RSD: 'Resende', BMA: 'Barra Mansa' };
const TEAM_EXTRA = { PEC: '#0369a1', LORA: '#0f766e', A4: '#6d28d9', '4 OLHOS': '#9a3412', Geral: '#57534e' };
const teamColor = (t) => (TEAM_UNIT[t] ? unitColor(TEAM_UNIT[t]) : TEAM_EXTRA[t] ?? NO_UNIT_COLOR);

const PRAZO_TONE = {
  vencido: 'bg-bad text-white',
  hoje: 'border-bad text-bad border',
  amanha: 'border-warn text-warn border',
  ok: 'border-line text-mute border',
  sem_prazo: 'border-line text-mute border',
};
const PRAZO_STRIPE = { vencido: 'var(--c-bad)', hoje: 'var(--c-bad)', amanha: 'var(--c-warn)', ok: 'transparent', sem_prazo: 'transparent' };

const DIA = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];
const diaLabel = (iso) => {
  const d = new Date(`${iso}T12:00:00`);
  return `${DIA[d.getDay()]} ${String(d.getDate()).padStart(2, '0')}`;
};

function BigKpi({ label, value, tone = 'text-ink', hint, solid }) {
  return (
    <div className={`flex min-w-0 flex-1 flex-col gap-1 border-r-2 border-rule px-5 py-3 last:border-r-0 ${solid ? 'bg-bad text-white' : ''}`}>
      <span className={`font-display text-6xl font-extrabold leading-[0.85] tracking-tight tabular-nums ${solid ? '' : tone}`}>{value ?? '—'}</span>
      <span className="font-mono text-[13.75px] font-bold uppercase tracking-[0.12em]">{label}</span>
      {hint && <span className={`font-mono text-[12.5px] ${solid ? 'opacity-80' : 'text-mute'}`}>{hint}</span>}
    </div>
  );
}

function Box({ title, children, className = '' }) {
  return (
    <section className={`border-2 border-rule bg-panel ${className}`}>
      <h2 className="border-b-2 border-rule bg-panel2 px-3 py-2 font-mono text-[13.75px] font-bold uppercase tracking-[0.14em] text-mute">{title}</h2>
      {children}
    </section>
  );
}

// Quadro por estado (como o board do ServiceNow): uma coluna por status, cartão por incidente, já ordenado por prazo
const STATUS_ORDER = ['Novo', 'Em Andamento', 'Em Espera'];

function Quadro({ rows, onAbrir }) {
  const cols = [...new Set(rows.map((r) => r.status))].sort((a, b) => {
    const ia = STATUS_ORDER.indexOf(a);
    const ib = STATUS_ORDER.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
  });
  return (
    <div className="flex min-h-0 flex-1 overflow-auto">
      {cols.length === 0 && <div className="m-auto p-10 font-display text-2xl font-extrabold uppercase">Nada aberto nesta equipe</div>}
      {cols.map((c) => {
        const items = rows.filter((r) => r.status === c);
        return (
          <section key={c} className="flex min-w-[300px] flex-1 flex-col border-r-2 border-rule last:border-r-0">
            <h3 className="sticky top-0 z-10 flex items-baseline justify-between border-b-2 border-rule bg-invert px-3 py-2 font-display text-sm font-bold uppercase tracking-wide text-invert-ink">
              {c}
              <span className="font-mono text-xs">{items.length}</span>
            </h3>
            <div className="space-y-2 p-2">
              {items.map((r) => (
                <article key={r.number} onClick={() => onAbrir(r)} title="Tratar / encerrar"
                  className="cursor-pointer border-2 border-rule bg-panel hover:bg-panel2" style={{ borderLeft: `8px solid ${teamColor(r.equipe)}` }}>
                  <div className="flex items-center justify-between gap-2 px-2.5 pt-1.5">
                    <span className="font-mono text-[13.75px] font-bold text-accent">{r.number}</span>
                    <span className={`px-1.5 py-px font-mono text-[12.5px] font-bold ${PRAZO_TONE[r.prazo_estado]}`}>{r.prazo_txt}</span>
                  </div>
                  <div className="px-2.5 py-1 font-display text-[15px] font-bold leading-tight">{r.titulo}</div>
                  <div className="flex items-center justify-between px-2.5 pb-1.5 font-mono text-[12.5px] text-mute">
                    <span>{r.grupo}</span>
                    {r.informal && <span className="font-bold uppercase text-mock">informal</span>}
                  </div>
                </article>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

export default function BacklogPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [team, setTeam] = useState('Todas');
  const [view, setView] = useState('tabela');
  const [aberto, setAberto] = useState(null);

  const load = useCallback(async (force = false) => {
    setBusy(true);
    try {
      setData(await getBacklog(force));
      setError(null);
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [load]);

  const rows = useMemo(() => (data?.rows ?? []).filter((r) => team === 'Todas' || r.equipe === team), [data, team]);
  const k = data?.kpis;
  const maxEq = Math.max(1, ...(k?.por_equipe ?? []).map((e) => e.total));
  const maxDia = Math.max(1, k?.vencidos_calendario ?? 0, ...(k?.calendario ?? []).map((d) => d.total));

  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto">
      {error && (
        <div className="flex items-center justify-between gap-3 border-b-2 border-rule bg-bad/10 px-4 py-2 text-xs font-bold text-bad">
          <span>{error}</span>
          <Button onClick={() => load(true)}>Tentar de novo</Button>
        </div>
      )}
      {!data && !error && <LoadingSpinner label="Lendo o backlog no ServiceNow…" />}

      {data && (
        <>
          {/* Cartões (mesmos do painel do ServiceNow, mais os vencidos) */}
          <div className="flex shrink-0 flex-wrap border-b-2 border-rule bg-panel">
            <BigKpi label="Backlog total" value={k.backlog_total} hint="incidentes abertos nas filas CFTV" />
            <BigKpi label="SLA violado" value={k.vencidos} solid={k.vencidos > 0} hint="SLA violado ou prazo estourado" />
            <BigKpi label="Encerrar hoje" value={k.encerrar_hoje} tone="text-bad" hint="prazo até o fim do dia" />
            <BigKpi label="Encerrar amanhã" value={k.encerrar_amanha} tone="text-warn" hint="prazo amanhã" />
            <BigKpi label="Encerrados no mês" value={k.encerrados_mes} tone="text-ok" hint="resolvidos + encerrados" />
          </div>

          <div className="grid shrink-0 grid-cols-1 gap-0 border-b-2 border-rule lg:grid-cols-2">
            <Box title="Backlog por equipe · clique para filtrar" className="border-0 border-b-2 border-rule lg:border-b-0 lg:border-r-2">
              <div className="space-y-1.5 p-3">
                {k.por_equipe.map((e) => (
                  <button
                    key={e.equipe}
                    onClick={() => setTeam(team === e.equipe ? 'Todas' : e.equipe)}
                    className={`grid w-full grid-cols-[52px_1fr_36px] items-center gap-2 text-left ${team !== 'Todas' && team !== e.equipe ? 'opacity-40' : ''}`}
                  >
                    <span className="font-mono text-xs font-bold">{e.equipe}</span>
                    <span className="h-6 bg-panel2">
                      <span className="block h-full" style={{ width: `${(e.total / maxEq) * 100}%`, background: teamColor(e.equipe) }} />
                    </span>
                    <span className="text-right font-display text-xl font-extrabold tabular-nums">{e.total}</span>
                  </button>
                ))}
              </div>
            </Box>

            <Box title="Prazos · vencidos e próximos 7 dias" className="border-0">
              <div className="flex h-[176px] items-end gap-2 p-3">
                <div className="flex h-full flex-1 flex-col justify-end text-center">
                  <span className="font-display text-xl font-extrabold text-bad">{k.vencidos_calendario}</span>
                  <span className="bg-bad" style={{ height: `${(k.vencidos_calendario / maxDia) * 100}px` }} />
                  <span className="mt-1 font-mono text-[12.5px] font-bold uppercase text-bad">vencidos</span>
                </div>
                {k.calendario.map((d, i) => (
                  <div key={d.dia} className="flex h-full flex-1 flex-col justify-end text-center">
                    <span className="font-display text-xl font-extrabold tabular-nums">{d.total}</span>
                    <span className={i === 0 ? 'bg-bad' : i === 1 ? 'bg-warn' : 'bg-accent'} style={{ height: `${(d.total / maxDia) * 100}px`, minHeight: d.total ? 4 : 1 }} />
                    <span className="mt-1 font-mono text-[12.5px] uppercase text-mute">{i === 0 ? 'hoje' : i === 1 ? 'amanhã' : diaLabel(d.dia)}</span>
                  </div>
                ))}
              </div>
            </Box>
          </div>

          {/* Tabela por prazo */}
          <div className="flex shrink-0 flex-wrap border-b-2 border-rule" role="tablist" aria-label="Equipes">
            {['Todas', ...data.equipes].map((t) => {
              const n = t === 'Todas' ? data.rows.length : data.rows.filter((r) => r.equipe === t).length;
              return (
                <button
                  key={t}
                  role="tab"
                  aria-selected={team === t}
                  onClick={() => setTeam(t)}
                  className={`border-r border-line px-4 py-2 font-display text-xs font-bold uppercase tracking-wide ${team === t ? 'bg-invert text-invert-ink' : 'text-ink hover:bg-panel2'}`}
                >
                  {t} <span className="font-mono">{n}</span>
                </button>
              );
            })}
            <span className="ml-auto flex items-center gap-3 px-4 font-mono text-[12.5px] text-mute">
              <span className="flex" role="group" aria-label="Visão">
                {['tabela', 'quadro'].map((v) => (
                  <button
                    key={v}
                    onClick={() => setView(v)}
                    aria-pressed={view === v}
                    className={`border-2 border-rule px-3 py-1 font-display text-xs font-bold uppercase ${view === v ? 'bg-invert text-invert-ink' : 'text-ink hover:bg-panel2'}`}
                  >
                    {v}
                  </button>
                ))}
              </span>
              atualizado {new Date(data.atualizado_em).toLocaleTimeString('pt-BR')}
              <Button onClick={() => load(true)} disabled={busy}>{busy ? 'Lendo…' : 'Atualizar'}</Button>
            </span>
          </div>

          {view === 'quadro' ? <Quadro rows={rows} onAbrir={setAberto} /> : (
          <div className="min-h-0 flex-1 overflow-auto">
            <table className="w-full border-collapse text-xs">
              <thead className="sticky top-0 z-10 bg-panel2">
                <tr className="border-b-2 border-rule text-left font-mono text-[12.5px] uppercase tracking-[0.1em] text-mute">
                  <th className="w-1.5 p-0" />
                  <th className="py-2 pl-3 pr-3">Incidente</th>
                  <th className="pr-3">Título</th>
                  <th className="pr-3">Solicitante</th>
                  <th className="pr-3">Prazo</th>
                  <th className="pr-3">Status</th>
                  <th className="pr-3">Equipe</th>
                  <th className="pr-3">Prior.</th>
                  <th className="pr-3">Último comentário</th>
                </tr>
              </thead>
              <tbody className="zebra">
                {rows.map((r) => (
                  <tr key={r.number} onClick={() => setAberto(r)} title="Clique para tratar / encerrar"
                    className="cursor-pointer border-b border-line hover:!bg-bg">
                    <td className="w-1.5 p-0" style={{ background: PRAZO_STRIPE[r.prazo_estado] }} />
                    <td className="py-2 pl-3 pr-3 font-mono font-bold">
                      <a
                        className="text-accent hover:underline"
                        href={snLink(r.number)}
                        target="_blank"
                        rel="noreferrer"
                        title="Abrir no ServiceNow"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {r.number}
                      </a>
                    </td>
                    <td className="max-w-[420px] truncate pr-3 font-semibold" title={r.titulo}>{r.titulo}</td>
                    <td className="max-w-[160px] truncate pr-3 text-mute">{r.solicitante}</td>
                    <td className="pr-3">
                      <span className={`inline-block px-1.5 py-px font-mono text-[13.75px] font-bold ${PRAZO_TONE[r.prazo_estado]}`}>{r.prazo_txt}</span>
                    </td>
                    <td className="pr-3">
                      {r.status}
                      {r.informal && <span className="ml-1.5 border border-mock px-1 font-mono text-[11.25px] font-bold uppercase text-mock">informal</span>}
                    </td>
                    <td className="pr-3">
                      <span className="inline-flex items-center gap-1.5 font-mono font-bold">
                        <span className="h-2.5 w-2.5" style={{ background: teamColor(r.equipe) }} />
                        {r.equipe}
                      </span>
                    </td>
                    <td className="pr-3 font-mono">{(r.prioridade ?? '').slice(0, 1)}</td>
                    <td className="max-w-[260px] truncate pr-3 font-mono text-[13.75px] text-mute" title={r.ultima_nota ?? ""}>{r.ultima_nota ?? "—"}</td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={9} className="p-10 text-center font-display text-2xl font-extrabold uppercase">Nada aberto nesta equipe</td></tr>
                )}
              </tbody>
            </table>
          </div>
          )}
        </>
      )}
      {aberto && <Tratar key={aberto.number} r={aberto} onFechar={() => setAberto(null)} onEncerrado={() => load(true)} />}
    </div>
  );
}
