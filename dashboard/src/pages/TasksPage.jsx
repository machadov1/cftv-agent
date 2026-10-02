import { useCallback, useEffect, useMemo, useState } from 'react';
import { getTasks, getTasksVolumetria } from '../api';
import LoadingSpinner from '../components/LoadingSpinner';
import { Button, unitColor } from '../components/ui';
import VolumeChart from '../components/VolumeChart';

// TASKs de acesso a imagens (board "TASKs" do ServiceNow, só as de acesso). Somente visualização, sem automação.
const DONO = [
  { id: 'todas', label: 'Todas' },
  { id: 'meus', label: 'Comigo' },
  { id: 'sem', label: 'Sem responsável' },
];
const TIPO_TONE = { Visualização: 'border-line text-mute', Reprodução: 'border-accent text-accent', Exportação: 'border-warn text-warn' };
const tipoTone = (t) => (t?.includes('Exportação') ? TIPO_TONE.Exportação : TIPO_TONE[t] ?? 'border-mock text-mock');
const idadeTone = (d) => (d > 30 ? 'bg-bad text-white' : d > 7 ? 'border border-bad text-bad' : 'border border-line text-mute');
const idadeTxt = (d) => (d == null ? '—' : d === 0 ? 'hoje' : d === 1 ? '1 dia' : `${d} dias`);

function BigKpi({ label, value, tone = 'text-ink', hint, solid }) {
  return (
    <div className={`flex min-w-0 flex-1 flex-col gap-1 border-r-2 border-rule px-5 py-3 last:border-r-0 ${solid ? 'bg-bad text-white' : ''}`}>
      <span className={`font-display text-6xl font-extrabold leading-[0.85] tracking-tight tabular-nums ${solid ? '' : tone}`}>{value ?? '—'}</span>
      <span className="font-mono text-[13.75px] font-bold uppercase tracking-[0.12em]">{label}</span>
      {hint && <span className={`font-mono text-[12.5px] ${solid ? 'opacity-80' : 'text-mute'}`}>{hint}</span>}
    </div>
  );
}

function Card({ t }) {
  return (
    <article className="border-2 border-rule bg-panel" style={{ borderLeft: `8px solid ${unitColor(t.unidade)}` }}>
      <div className="flex items-center justify-between gap-2 px-2.5 pt-1.5">
        <a href={t.link} target="_blank" rel="noreferrer" title="Abrir no ServiceNow" className="font-mono text-[13.75px] font-bold text-accent hover:underline">
          {t.number}
        </a>
        <span className={`px-1.5 py-px font-mono text-[12.5px] font-bold ${idadeTone(t.idade_dias)}`}>{idadeTxt(t.idade_dias)}</span>
      </div>
      <div className="px-2.5 pt-1 font-display text-[15px] font-bold leading-tight">{t.area ?? 'Área não informada'}</div>
      <div className="px-2.5 font-mono text-[12.5px] text-mute">{t.unidade ?? 'sem localidade'} · {t.ritm}</div>
      <div className="px-2.5 pt-1 text-xs font-semibold">{t.solicitante ?? '—'}</div>
      {t.justificativa && <p className="line-clamp-2 px-2.5 text-xs text-mute" title={t.justificativa}>{t.justificativa}</p>}
      <div className="flex items-center justify-between gap-2 px-2.5 py-1.5">
        {t.tipo ? <span className={`border px-1.5 font-mono text-[11.25px] font-bold uppercase ${tipoTone(t.tipo)}`}>{t.tipo}</span> : <span />}
        <span className={`truncate font-mono text-[12.5px] ${t.meu ? 'font-bold text-ok' : t.responsavel ? 'text-mute' : 'text-warn'}`}>
          {t.meu ? 'comigo' : t.responsavel ?? 'sem responsável'}
        </span>
      </div>
    </article>
  );
}

// Uma coluna por unidade, mais antigas primeiro (o board do ServiceNow agrupa por estado, mas aqui está tudo "Aberto")
function Quadro({ rows }) {
  const cols = [...new Set(rows.map((r) => r.unidade ?? 'Sem localidade'))]
    .map((u) => ({ u, items: rows.filter((r) => (r.unidade ?? 'Sem localidade') === u) }))
    .sort((a, b) => b.items.length - a.items.length);
  return (
    <div className="flex min-h-0 flex-1 overflow-auto">
      {cols.length === 0 && <div className="m-auto p-10 font-display text-2xl font-extrabold uppercase">Nenhuma task neste filtro</div>}
      {cols.map(({ u, items }) => (
        <section key={u} className="flex min-w-[290px] flex-1 flex-col border-r-2 border-rule last:border-r-0">
          <h3 className="sticky top-0 z-10 flex items-baseline justify-between border-b-2 border-rule px-3 py-2 font-display text-sm font-bold uppercase tracking-wide text-white"
            style={{ background: unitColor(u) }}>
            {u}
            <span className="font-mono text-xs">{items.length}</span>
          </h3>
          <div className="space-y-2 p-2">
            {[...items].sort((a, b) => (b.idade_dias ?? 0) - (a.idade_dias ?? 0)).map((t) => <Card key={t.number} t={t} />)}
          </div>
        </section>
      ))}
    </div>
  );
}

export default function TasksPage() {
  const [data, setData] = useState(null);
  const [volumetria, setVolumetria] = useState(null);
  const [volErro, setVolErro] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [dono, setDono] = useState('todas');
  const [unidade, setUnidade] = useState(null);
  const [busca, setBusca] = useState('');
  const [view, setView] = useState('quadro');

  const load = useCallback(async (force = false) => {
    setBusy(true);
    try {
      setData(await getTasks(force));
      setError(null);
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  }, []);

  useEffect(() => {
    getTasksVolumetria(5).then((v) => { setVolumetria(v); setVolErro(null); }).catch((e) => setVolErro(e.message));
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [load]);

  const rows = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return (data?.rows ?? []).filter((t) =>
      (dono === 'todas' || (dono === 'meus' ? t.meu : !t.responsavel))
      && (!unidade || (t.unidade ?? 'Sem localidade') === unidade)
      && (!q || [t.number, t.ritm, t.solicitante, t.area, t.justificativa, t.gerencia].some((x) => x?.toLowerCase().includes(q))));
  }, [data, dono, unidade, busca]);
  const k = data?.kpis;
  const maxU = Math.max(1, ...(k?.por_unidade ?? []).map((u) => u.total));

  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto">
      {error && (
        <div className="flex items-center justify-between gap-3 border-b-2 border-rule bg-bad/10 px-4 py-2 text-xs font-bold text-bad">
          <span>{error}</span>
          <Button onClick={() => load(true)}>Tentar de novo</Button>
        </div>
      )}
      {!data && !error && <LoadingSpinner label="Lendo as TASKs no ServiceNow…" />}

      {data && (
        <>
          <div className="flex shrink-0 flex-wrap border-b-2 border-rule bg-panel">
            <BigKpi label="Acesso a imagens" value={k.total} hint="TASKs abertas nas filas CFTV" />
            <BigKpi label="Sem responsável" value={k.sem_responsavel} tone="text-warn" hint="ninguém pegou ainda" />
            <BigKpi label="Comigo" value={k.meus} tone="text-ok" hint="atribuídas a você" />
            <BigKpi label="Mais de 7 dias" value={k.mais_de_7_dias} solid={k.mais_de_7_dias > 0} hint="abertas há mais de uma semana" />
            <BigKpi label="Mais antiga" value={k.mais_antiga_dias != null ? `${k.mais_antiga_dias}d` : '—'} tone="text-bad" hint="dias desde a abertura" />
          </div>

          <section className="shrink-0 border-b-2 border-rule bg-panel">
            <h2 className="border-b-2 border-rule bg-panel2 px-3 py-2 font-mono text-[13.75px] font-bold uppercase tracking-[0.14em] text-mute">
              Por unidade · clique para filtrar
            </h2>
            <div className="grid grid-cols-1 gap-x-6 gap-y-1.5 p-3 md:grid-cols-2 xl:grid-cols-3">
              {k.por_unidade.map((u) => {
                const nome = u.nome === '—' ? 'Sem localidade' : u.nome;
                return (
                  <button key={nome} onClick={() => setUnidade(unidade === nome ? null : nome)}
                    className={`grid w-full grid-cols-[150px_1fr_36px] items-center gap-2 text-left ${unidade && unidade !== nome ? 'opacity-40' : ''}`}>
                    <span className="truncate font-mono text-xs font-bold">{nome}</span>
                    <span className="h-5 bg-panel2">
                      <span className="block h-full" style={{ width: `${(u.total / maxU) * 100}%`, background: unitColor(nome) }} />
                    </span>
                    <span className="text-right font-display text-xl font-extrabold tabular-nums">{u.total}</span>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="shrink-0 border-b-2 border-rule bg-panel">
            <h2 className="flex items-baseline justify-between border-b-2 border-rule bg-panel2 px-3 py-2 font-mono text-[13.75px] font-bold uppercase tracking-[0.14em] text-mute">
              Volumetria · TASKs de acesso, últimos 5 meses
              {volumetria && (
                <span className="normal-case tracking-normal">
                  {volumetria.total_encerrados} encerradas · {volumetria.total_entraram} abertas · * mês em andamento
                </span>
              )}
            </h2>
            <div className="p-3"><VolumeChart data={volumetria} error={volErro} height={190} /></div>
          </section>

          <div className="flex shrink-0 flex-wrap items-center border-b-2 border-rule" role="tablist" aria-label="Responsável">
            {DONO.map((d) => {
              const n = d.id === 'todas' ? k.total : d.id === 'meus' ? k.meus : k.sem_responsavel;
              return (
                <button key={d.id} role="tab" aria-selected={dono === d.id} onClick={() => setDono(d.id)}
                  className={`border-r border-line px-4 py-2 font-display text-xs font-bold uppercase tracking-wide ${dono === d.id ? 'bg-invert text-invert-ink' : 'text-ink hover:bg-panel2'}`}>
                  {d.label} <span className="font-mono">{n}</span>
                </button>
              );
            })}
            {unidade && (
              <button onClick={() => setUnidade(null)} className="border-r border-line px-3 py-2 font-mono text-[12.5px] font-bold text-accent">
                {unidade} ×
              </button>
            )}
            <label className="sr-only" htmlFor="busca-tasks">Buscar</label>
            <input id="busca-tasks" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="buscar TASK, RITM, solicitante, área…"
              className="mx-3 my-1 w-64 border-2 border-rule bg-panel px-2 py-1 font-mono text-[13.75px]" />
            <span className="ml-auto flex items-center gap-3 px-4 font-mono text-[12.5px] text-mute">
              <span className="flex" role="group" aria-label="Visão">
                {['quadro', 'tabela'].map((v) => (
                  <button key={v} onClick={() => setView(v)} aria-pressed={view === v}
                    className={`border-2 border-rule px-3 py-1 font-display text-xs font-bold uppercase ${view === v ? 'bg-invert text-invert-ink' : 'text-ink hover:bg-panel2'}`}>
                    {v}
                  </button>
                ))}
              </span>
              <a href={data.board_url} target="_blank" rel="noreferrer" className="text-accent hover:underline">board no ServiceNow</a>
              atualizado {new Date(data.atualizado_em).toLocaleTimeString('pt-BR')}
              <Button onClick={() => load(true)} disabled={busy}>{busy ? 'Lendo…' : 'Atualizar'}</Button>
            </span>
          </div>

          {view === 'quadro' ? <Quadro rows={rows} /> : (
            <div className="min-h-0 flex-1 overflow-auto">
              <table className="w-full border-collapse text-xs">
                <thead className="sticky top-0 z-10 bg-panel2">
                  <tr className="border-b-2 border-rule text-left font-mono text-[12.5px] uppercase tracking-[0.1em] text-mute">
                    <th className="w-1.5 p-0" />
                    <th className="py-2 pl-3 pr-3">Task</th>
                    <th className="pr-3">RITM</th>
                    <th className="pr-3">Unidade</th>
                    <th className="pr-3">Área das câmeras</th>
                    <th className="pr-3">Solicitante</th>
                    <th className="pr-3">Tipo</th>
                    <th className="pr-3">Aberta há</th>
                    <th className="pr-3">Responsável</th>
                    <th className="pr-3">Justificativa</th>
                  </tr>
                </thead>
                <tbody className="zebra">
                  {rows.map((t) => (
                    <tr key={t.number} className="border-b border-line hover:!bg-bg">
                      <td className="w-1.5 p-0" style={{ background: unitColor(t.unidade) }} />
                      <td className="py-2 pl-3 pr-3 font-mono font-bold">
                        <a className="text-accent hover:underline" href={t.link} target="_blank" rel="noreferrer" title="Abrir no ServiceNow">{t.number}</a>
                      </td>
                      <td className="pr-3 font-mono text-mute">{t.ritm}</td>
                      <td className="pr-3 font-semibold">{t.unidade ?? '—'}</td>
                      <td className="max-w-[220px] truncate pr-3 font-semibold" title={t.area ?? ''}>{t.area ?? '—'}</td>
                      <td className="max-w-[180px] truncate pr-3" title={t.gerencia ?? ''}>{t.solicitante ?? '—'}</td>
                      <td className="pr-3">{t.tipo && <span className={`border px-1.5 font-mono text-[11.25px] font-bold uppercase ${tipoTone(t.tipo)}`}>{t.tipo}</span>}</td>
                      <td className="pr-3"><span className={`inline-block px-1.5 py-px font-mono text-[13.75px] font-bold ${idadeTone(t.idade_dias)}`}>{idadeTxt(t.idade_dias)}</span></td>
                      <td className={`max-w-[180px] truncate pr-3 font-mono text-[13.75px] ${t.meu ? 'font-bold text-ok' : t.responsavel ? 'text-mute' : 'text-warn'}`}>
                        {t.meu ? 'comigo' : t.responsavel ?? 'sem responsável'}
                      </td>
                      <td className="max-w-[320px] truncate pr-3 text-mute" title={t.justificativa ?? ''}>{t.justificativa ?? '—'}</td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr><td colSpan={10} className="p-10 text-center font-display text-2xl font-extrabold uppercase">Nenhuma task neste filtro</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
