import { useEffect, useMemo, useState } from 'react';
import { getTopologia, getTopologiaMapa, getTopologiaServidor } from '../api';
import { Button, inputClass, unitColor } from './ui';

const LABEL = 'font-mono text-[12.5px] font-bold uppercase tracking-[0.14em] text-mute';
const fold = (s) => (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');
const ERRO = { credencial: 'credencial recusada', timeout: 'porta não atende', lento: 'servidor lento', rede: 'conexão recusada',
  config: 'Digifort não configurado', resposta: 'resposta inesperada' };

const CURTO = { credencial: 'senha recusada', timeout: 'não atende', lento: 'lento', rede: 'recusada', config: 'sem config', resposta: 'erro' };

// tom pela disponibilidade: >=95 verde, >=85 âmbar, abaixo vermelho
const tom = (p) => (p == null ? 'mute' : p >= 95 ? 'ok' : p >= 85 ? 'warn' : 'bad');
const TXT = { ok: 'text-ok', warn: 'text-warn', bad: 'text-bad', mute: 'text-mute' };
const STROKE = { ok: 'stroke-ok', warn: 'stroke-warn', bad: 'stroke-bad', mute: 'stroke-mute' };
const FILL = { ok: 'fill-ok', warn: 'fill-warn', bad: 'fill-bad', mute: 'fill-mute' };
const BG = { ok: 'bg-ok', warn: 'bg-warn', bad: 'bg-bad', mute: 'bg-mute' };
const pct = (p) => (p == null ? '—' : `${p.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`);

// estado do servidor no mapa: {tom, tracejado, rotulo}
function estadoServidor(s) {
  if (s.ok === null || s.ok === undefined) return { t: 'mute', dash: true, rot: s.ip ? 'lendo…' : 'sem IP' };
  if (s.ok === false) return { t: 'bad', dash: true, rot: CURTO[s.tipo_erro] ?? 'falha' };
  if (s.reserva) return { t: 'mute', dash: true, rot: 'reserva' };
  return { t: tom(s.cameras?.disponibilidade), dash: false, rot: pct(s.cameras?.disponibilidade) };
}

function IconeServidor({ t }) {
  return (
    <svg viewBox="0 0 40 50" width="38" height="48" aria-hidden="true" className="text-ink">
      <rect x="5" y="2" width="30" height="46" className="fill-panel stroke-current" strokeWidth="2.5" />
      {[13, 24, 35].map((y) => <line key={y} x1="5" x2="35" y1={y} y2={y} className="stroke-current" strokeWidth="1.5" />)}
      {[7.5, 18.5, 29.5].map((y) => (
        <g key={y}>
          <rect x="9" y={y - 1.75} width="3.5" height="3.5" className={FILL[t]} />
          <line x1="16" x2="31" y1={y} y2={y} className="stroke-current" strokeWidth="1" opacity="0.5" />
        </g>
      ))}
      <rect x="9" y="40" width="22" height="3" className="fill-current" opacity="0.35" />
    </svg>
  );
}

function IconeSwitch({ cor }) {
  return (
    <svg viewBox="0 0 34 22" width="34" height="22" aria-hidden="true" className="shrink-0 text-ink">
      <rect x="1.5" y="1.5" width="31" height="19" className="fill-panel stroke-current" strokeWidth="2.5" />
      {[7, 13, 19, 25].map((x) => <rect key={x} x={x - 1.5} y="11" width="3" height="5" className="fill-current" />)}
      <rect x="4" y="5" width="26" height="2.5" style={{ fill: cor }} />
    </svg>
  );
}

const SLOT = 112; // largura de cada servidor no desenho

function Cluster({ u, onAbrir }) {
  const c = u.cameras;
  const t = tom(c?.disponibilidade);
  const n = u.servidores.length;
  const largura = Math.max(n * SLOT, SLOT);
  const meio = largura / 2;
  const span = n > 5 ? 'md:col-span-2 xl:col-span-3' : n > 2 ? 'md:col-span-2' : '';
  const semLeitura = u.servidores_respondendo === 0 && u.servidores_total > 0;
  const motivo = semLeitura ? (CURTO[u.servidores.find((s) => s.ok === false)?.tipo_erro] ?? 'sem leitura') : null;
  const falhas = u.servidores.filter((s) => s.ok === false).length;
  return (
    <div className={`flex flex-col items-center ${span}`}>
      <button onClick={() => onAbrir(u)} title="Ver todas as câmeras da unidade"
        className="w-full max-w-[320px] border-2 border-rule bg-panel text-left shadow-[4px_4px_0_var(--c-rule)] transition-transform hover:-translate-y-0.5">
        <div className="flex items-center gap-2.5 border-b-2 border-rule px-3 py-2" style={{ borderLeft: `8px solid ${unitColor(u.unidade)}` }}>
          <IconeSwitch cor={unitColor(u.unidade)} />
          <span className="min-w-0 flex-1 truncate font-display text-lg font-extrabold uppercase leading-tight">{u.unidade}</span>
          <span className={`font-display text-2xl font-extrabold tabular-nums ${TXT[t]}`}>{c ? pct(c.disponibilidade) : '…'}</span>
        </div>
        <div className="px-3 py-1.5">
          <div className="h-1.5 w-full bg-panel2"><div className={`h-full ${BG[t]}`} style={{ width: `${c?.disponibilidade ?? 0}%` }} /></div>
          <div className="mt-1 flex justify-between font-mono text-[12.5px] text-mute">
            {semLeitura ? <span className="font-bold text-bad">nenhum servidor respondeu ({motivo})</span>
              : <span>{c ? `${c.ok.toLocaleString('pt-BR')}/${c.ativas.toLocaleString('pt-BR')} câmeras` : 'lendo…'}</span>}
            <span className={falhas ? 'font-bold text-bad' : ''}>{u.servidores_respondendo ?? '…'}/{u.servidores_total ?? n} serv.</span>
          </div>
        </div>
      </button>

      <div className="max-w-full overflow-x-auto">
        <svg width={largura} height="34" aria-hidden="true" className="block">
          <line x1={meio} x2={meio} y1="0" y2="16" className={STROKE[semLeitura ? 'bad' : t]} strokeWidth="3"
            strokeDasharray={semLeitura ? '5 4' : undefined} />
          {n > 1 && <line x1={SLOT / 2} x2={largura - SLOT / 2} y1="16" y2="16" className="stroke-current text-ink" strokeWidth="2" opacity="0.45" />}
          {u.servidores.map((s, i) => {
            const e = estadoServidor(s);
            const x = SLOT * i + SLOT / 2;
            return <line key={`${s.nome}-${i}`} x1={x} x2={x} y1="16" y2="34" className={STROKE[e.t]} strokeWidth="3"
              strokeDasharray={e.dash ? '5 4' : undefined} />;
          })}
        </svg>
        <div className="flex" style={{ width: largura }}>
          {u.servidores.map((s, i) => {
            const e = estadoServidor(s);
            return (
              <button key={`${s.nome}-${i}`} onClick={() => onAbrir(u, s.ip)} disabled={!s.ip}
                title={`${s.nome} · ${s.ip ?? 'sem IP'} · ${s.tipo}${s.erro ? `\n${s.erro}` : ''}`}
                style={{ width: SLOT }} className="flex flex-col items-center px-1 pb-1 hover:bg-panel2 disabled:opacity-60">
                <IconeServidor t={e.t} />
                <span className="w-full truncate text-center font-mono text-[11.25px] font-bold">{s.nome}</span>
                <span className={`w-full truncate text-center font-mono text-[11.25px] font-bold ${TXT[e.t]}`}>{e.rot}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

const dur = (s) => (s == null ? '' : s < 3600 ? `${Math.max(1, Math.round(s / 60))} min` : s < 86400 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} d`);

// Card da unidade: todas as câmeras, por servidor, com filtro de estado. Lê cada servidor do cache do backend.
function CardUnidade({ u, ipInicial, incDa, onTestar, onFechar }) {
  const [srv, setSrv] = useState(ipInicial ?? 'todos');
  const [dados, setDados] = useState({});
  const [filtro, setFiltro] = useState('');
  const [estado, setEstado] = useState('todas'); // todas | sem_sinal | desativadas | ok

  useEffect(() => {
    u.servidores.filter((s) => s.ip && s.ok).forEach((s) =>
      getTopologiaServidor(s.ip).then((r) => setDados((d) => ({ ...d, [s.ip]: r }))).catch(() => {}));
  }, [u]);
  useEffect(() => {
    const esc = (e) => e.key === 'Escape' && onFechar();
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [onFechar]);

  const f = fold(filtro);
  const passa = (c) => (!f || fold(`${c.nome} ${c.descricao}`).includes(f)) && (estado === 'todas'
    || (estado === 'sem_sinal' && c.active !== false && c.working === false)
    || (estado === 'desativadas' && c.active === false)
    || (estado === 'ok' && c.active !== false && c.working === true));
  const visiveis = u.servidores.filter((s) => s.ip && (srv === 'todos' || s.ip === srv));
  const t = tom(u.cameras?.disponibilidade);

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={onFechar}>
      <aside onClick={(e) => e.stopPropagation()} aria-label={`Câmeras de ${u.unidade}`}
        className="flex h-full w-full max-w-[720px] flex-col border-l-4 border-rule bg-bg shadow-2xl">
        <header className="flex items-start gap-3 border-b-2 border-rule bg-panel px-5 py-3" style={{ borderTop: `6px solid ${unitColor(u.unidade)}` }}>
          <div className="min-w-0 flex-1">
            <div className={LABEL}>Unidade</div>
            <div className="truncate font-display text-3xl font-extrabold uppercase leading-none">{u.unidade}</div>
            <div className="mt-1 font-mono text-[13.75px] text-mute">
              {u.cameras ? `${u.cameras.ok} de ${u.cameras.ativas} câmeras ativas transmitindo · ${u.cameras.sem_sinal} sem sinal · ${u.cameras.desativadas} desativadas` : '—'}
            </div>
          </div>
          <div className={`font-display text-5xl font-extrabold leading-none tabular-nums ${TXT[t]}`}>{pct(u.cameras?.disponibilidade)}</div>
          <button onClick={onFechar} aria-label="Fechar" className="border-2 border-rule px-2.5 py-1 font-display text-lg font-bold hover:bg-panel2">×</button>
        </header>

        <div className="flex flex-wrap gap-1.5 border-b-2 border-rule bg-panel2 px-5 py-2">
          {[{ ip: 'todos', nome: 'Todos', e: null }, ...u.servidores.map((s) => ({ ...s, e: estadoServidor(s) }))].map((s, i) => (
            <button key={`${s.ip}-${i}`} onClick={() => s.ip && setSrv(s.ip)} disabled={!s.ip}
              className={`border-2 px-2 py-1 font-mono text-[12.5px] font-bold ${srv === s.ip ? 'border-rule bg-invert text-invert-ink' : 'border-line bg-panel hover:border-rule'} disabled:opacity-50`}>
              {s.nome}{s.e && <span className={srv === s.ip ? '' : TXT[s.e.t]}> · {s.e.rot}</span>}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2 border-b-2 border-rule px-5 py-2">
          <input value={filtro} onChange={(e) => setFiltro(e.target.value)} placeholder="filtrar câmera…" className={`${inputClass} max-w-[240px]`} />
          {[['todas', 'Todas'], ['sem_sinal', 'Sem sinal'], ['desativadas', 'Desativadas'], ['ok', 'Transmitindo']].map(([id, nome]) => (
            <button key={id} onClick={() => setEstado(id)}
              className={`border-2 px-2 py-1 font-display text-sm font-bold uppercase ${estado === id ? 'border-rule bg-invert text-invert-ink' : 'border-line hover:border-rule'}`}>
              {nome}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-auto px-5 py-3">
          {visiveis.map((s) => {
            const e = estadoServidor(s);
            const d = dados[s.ip];
            const cams = (d?.cameras ?? []).filter(passa);
            return (
              <section key={s.ip}>
                <div className="flex items-baseline gap-2 border-b-2 border-rule pb-1">
                  <span className="font-mono text-sm font-bold">{s.nome}</span>
                  <span className="font-mono text-[12.5px] text-mute">{s.ip} · {s.tipo}</span>
                  <span className={`ml-auto font-mono text-[12.5px] font-bold ${TXT[e.t]}`}>{e.rot}</span>
                </div>
                {s.ok === false ? <p className="mt-1 font-mono text-[12.5px] text-bad">{s.erro}</p>
                  : s.reserva && estado !== 'desativadas' ? <p className="mt-1 font-mono text-[12.5px] text-mute">Servidor reserva: {s.cameras.total} câmeras, todas desativadas (filtre "Desativadas" para ver).</p>
                  : !d ? <p className="mt-1 animate-pulse font-mono text-[12.5px] text-mute">lendo câmeras…</p>
                  : cams.length === 0 ? <p className="mt-1 font-mono text-[12.5px] text-mute">Nenhuma câmera com esse filtro.</p> : (
                    <ul className="mt-1 columns-1 gap-5 sm:columns-2">
                      {cams.map((c) => {
                        const inc = incDa(c.nome);
                        const off = c.active !== false && c.working === false;
                        return (
                          <li key={c.nome} className="flex break-inside-avoid items-center gap-1.5 py-0.5 font-mono text-[13.75px]" title={c.descricao || undefined}>
                            <span className={`inline-block h-2.5 w-2.5 shrink-0 ${c.active === false ? 'bg-mute' : off ? 'bg-bad' : c.working ? 'bg-ok' : 'border-2 border-mute'}`} />
                            <span className="truncate">{c.nome}</span>
                            {off && c.inactive_s ? <span className="shrink-0 text-[12.5px] text-bad">{dur(c.inactive_s)}</span> : null}
                            {inc && <button onClick={() => onTestar(inc)} className="shrink-0 font-bold text-accent underline" title="Abrir o teste deste incidente">{inc}</button>}
                          </li>
                        );
                      })}
                    </ul>
                  )}
              </section>
            );
          })}
        </div>
      </aside>
    </div>
  );
}

// Topologia em mapa (estilo Packet Tracer): unidade -> servidores, com disponibilidade (câmeras transmitindo / ativas).
export default function TopologiaMapa({ incidentes = [], onTestar }) {
  const [mapa, setMapa] = useState(null);
  const [lendo, setLendo] = useState(false);
  const [erro, setErro] = useState(null);
  const [q, setQ] = useState('');
  const [aberto, setAberto] = useState(null); // {u, ip}
  const [ordem, setOrdem] = useState('nome'); // nome | pior

  const carregar = (forcar = false) => {
    setLendo(true); setErro(null);
    getTopologiaMapa(forcar).then(setMapa).catch((e) => setErro(e.message)).finally(() => setLendo(false));
  };
  useEffect(() => {
    // desenho imediato pela lista de servidores; a disponibilidade chega quando o Digifort responder
    getTopologia().then((t) => setMapa((m) => m ?? { esboco: true, digifort_configurado: t.digifort_configurado, unidades: t.unidades.map((u) => ({
      ...u, cameras: null, servidores_total: u.servidores.filter((s) => s.ip).length, servidores_respondendo: null,
      servidores: u.servidores.map((s) => ({ ...s, ok: null })) })) })).catch(() => {});
    carregar();
  }, []);

  const textos = useMemo(() => incidentes.map((i) => ({ n: i.number, t: fold(`${i.titulo} ${i.descricao}`) })), [incidentes]);
  const incDa = (nome) => { const f = fold(nome); return f.length >= 5 ? textos.find((x) => x.t.includes(f))?.n : undefined; };

  const unidades = useMemo(() => {
    const f = fold(q);
    const lista = (mapa?.unidades ?? []).filter((u) => !f || fold(u.unidade).includes(f) || u.servidores.some((s) => fold(s.nome).includes(f)));
    return ordem === 'pior' ? [...lista].sort((a, b) => (a.cameras?.disponibilidade ?? 101) - (b.cameras?.disponibilidade ?? 101)) : lista;
  }, [mapa, q, ordem]);

  const g = mapa?.geral;
  const gt = tom(g?.disponibilidade);
  const aberta = aberto && mapa?.unidades.find((u) => u.unidade === aberto.u);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-2 border-b-2 border-rule bg-panel px-5 py-3">
        <div>
          <div className={LABEL}>Rede CFTV · disponibilidade</div>
          <div className={`font-display text-4xl font-extrabold leading-none tabular-nums ${TXT[gt]}`}>{lendo && !g ? '…' : pct(g?.disponibilidade)}</div>
        </div>
        <div className="font-mono text-[13.75px] leading-relaxed">
          <div>{g ? `${g.ok.toLocaleString('pt-BR')} de ${g.ativas.toLocaleString('pt-BR')} câmeras ativas transmitindo` : 'lendo os servidores…'}</div>
          <div className="text-mute">{g ? `${g.servidores_respondendo} de ${g.servidores_total} servidores respondendo` : ''}</div>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="filtrar unidade ou servidor…" className={`${inputClass} w-56`} />
          <Button onClick={() => setOrdem((o) => (o === 'nome' ? 'pior' : 'nome'))}>Ordem: {ordem === 'nome' ? 'A–Z' : 'pior primeiro'}</Button>
          <Button tone="primary" onClick={() => carregar(true)} disabled={lendo}>{lendo ? 'Lendo…' : 'Atualizar'}</Button>
        </div>
        <div className="flex w-full flex-wrap items-center gap-4 font-mono text-[12.5px] text-mute">
          <span className="flex items-center gap-1.5"><span className="inline-block h-1 w-6 bg-ok" />≥ 95%</span>
          <span className="flex items-center gap-1.5"><span className="inline-block h-1 w-6 bg-warn" />85–95%</span>
          <span className="flex items-center gap-1.5"><span className="inline-block h-1 w-6 bg-bad" />&lt; 85% ou servidor sem leitura</span>
          <span className="flex items-center gap-1.5"><span className="inline-block h-0 w-6 border-t-[3px] border-dashed border-mute" />reserva / não lido</span>
          <span>Disponibilidade = câmeras transmitindo ÷ câmeras ativas. Clique na unidade ou no servidor para ver as câmeras.</span>
          {erro && <span className="font-bold text-bad">{erro}</span>}
          {mapa && !mapa.digifort_configurado && <span className="font-bold text-bad">Digifort não configurado no .env</span>}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-6"
        style={{ backgroundImage: 'radial-gradient(var(--c-line) 1.2px, transparent 1.2px)', backgroundSize: '20px 20px' }}>
        {!mapa ? <p className="font-mono text-mute">carregando…</p> : (
          <div className="grid grid-flow-row-dense grid-cols-1 gap-x-8 gap-y-10 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {unidades.map((u) => <Cluster key={u.unidade} u={u} onAbrir={(un, ip) => setAberto({ u: un.unidade, ip })} />)}
          </div>
        )}
      </div>

      {aberta && (
        <CardUnidade key={`${aberta.unidade}-${aberto.ip}`} u={aberta} ipInicial={aberto.ip} incDa={incDa}
          onTestar={(inc) => { setAberto(null); onTestar?.(inc); }} onFechar={() => setAberto(null)} />
      )}
    </div>
  );
}
