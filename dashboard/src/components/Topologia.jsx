import { useEffect, useMemo, useState } from 'react';
import { getTopologia, getTopologiaServidor } from '../api';
import LoadingSpinner from './LoadingSpinner';
import { Button, inputClass, unitColor } from './ui';

const LABEL = 'font-mono text-[12.5px] font-bold uppercase tracking-[0.14em] text-mute';
const fold = (s) => (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');

const ERRO = { credencial: 'credencial recusada', timeout: 'porta não atende', lento: 'servidor lento', rede: 'conexão recusada', config: 'Digifort não configurado', resposta: 'resposta inesperada' };

function Ponto({ cam }) {
  const [cls, t] = cam.active === false ? ['bg-mute', 'desativada no cadastro'] : cam.working === false ? ['bg-bad', 'sem sinal']
    : cam.working ? ['bg-ok', 'transmitindo'] : ['border-2 border-mute', 'sem estado'];
  return <span className={`inline-block h-2.5 w-2.5 shrink-0 ${cls}`} title={t} />;
}

function Selo({ e }) {
  if (!e) return <span className="font-mono text-[12.5px] text-mute">não lido</span>;
  if (e.carregando) return <span className="animate-pulse font-mono text-[12.5px] text-mute">lendo…</span>;
  if (!e.ok) return <span className="font-mono text-[12.5px] font-bold text-bad" title={e.erro}>{ERRO[e.tipo_erro] ?? e.erro}</span>;
  const r = e.resumo;
  if (r.total > 0 && r.desativadas === r.total) {
    return <span className="font-mono text-[12.5px] font-bold text-mute" title="Todas as câmeras desativadas: provável servidor reserva (failover)">{r.total} câm · todas desativadas (reserva?)</span>;
  }
  return (
    <span className="font-mono text-[12.5px] font-bold">
      <span className="text-ok">{r.total} câm</span>
      {r.sem_sinal > 0 && <span className="text-bad"> · {r.sem_sinal} sem sinal</span>}
      {r.desativadas > 0 && <span className="text-mute"> · {r.desativadas} desativ.</span>}
    </span>
  );
}

// Unidade -> servidores (lista de servidores) -> câmeras (Digifort, lido sob demanda). Mostra quais servidores
// aceitam nossa credencial e quais câmeras estão fora; câmera citada num incidente aberto leva ao teste dele.
export default function Topologia({ incidentes = [], onAbrir }) {
  const [topo, setTopo] = useState(null);
  const [erro, setErro] = useState(null);
  const [estado, setEstado] = useState({}); // ip -> resposta do servidor
  const [aberto, setAberto] = useState({}); // unidade/ip -> expandido
  const [q, setQ] = useState('');

  useEffect(() => { getTopologia().then(setTopo).catch((e) => setErro(e.message)); }, []);

  const ler = async (ip, forcar = false) => {
    setEstado((s) => ({ ...s, [ip]: { ...s[ip], carregando: true } }));
    try {
      const r = await getTopologiaServidor(ip, forcar);
      setEstado((s) => ({ ...s, [ip]: r }));
    } catch (e) {
      setEstado((s) => ({ ...s, [ip]: { ok: false, erro: e.message } }));
    }
  };
  const lerUnidade = async (u) => {
    setAberto((a) => ({ ...a, [u.unidade]: true }));
    for (const s of u.servidores) if (s.ip) await ler(s.ip, true); // um por vez: não inunda a rede da unidade
  };
  const alternar = (k, ip) => {
    setAberto((a) => ({ ...a, [k]: !a[k] }));
    if (ip && !estado[ip]) ler(ip);
  };

  // câmera citada no título/descrição de um incidente aberto
  const textos = useMemo(() => incidentes.map((i) => ({ n: i.number, t: fold(`${i.titulo} ${i.descricao}`) })), [incidentes]);
  const incDa = (nome) => { const f = fold(nome); return f.length >= 5 ? textos.find((x) => x.t.includes(f))?.n : undefined; };

  const filtro = fold(q);
  const unidades = useMemo(() => (topo?.unidades ?? []).filter((u) => !filtro || fold(u.unidade).includes(filtro)
    || u.servidores.some((s) => fold(s.nome).includes(filtro) || (estado[s.ip]?.cameras ?? []).some((c) => fold(c.nome).includes(filtro)))),
  [topo, filtro, estado]);

  if (erro) return <p className="p-4 text-xs font-semibold text-bad">{erro}</p>;
  if (!topo) return <LoadingSpinner />;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 space-y-1.5 border-b-2 border-rule p-3">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="filtrar unidade, servidor ou câmera…" className={inputClass} />
        {!topo.digifort_configurado && <p className="text-xs font-bold text-bad">Digifort não configurado (DIGIFORT_USER/PASSWORD no .env).</p>}
        <p className="font-mono text-[12.5px] text-mute">Clique num servidor para ler as câmeras (cache de 10 min). "Ler unidade" relê todos.</p>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {unidades.map((u) => {
          const lidos = u.servidores.filter((s) => estado[s.ip] && !estado[s.ip].carregando);
          const falhas = lidos.filter((s) => !estado[s.ip].ok).length;
          return (
            <section key={u.unidade} className="border-b-2 border-rule">
              <div className="flex items-stretch">
                <span className="w-1.5 shrink-0" style={{ background: unitColor(u.unidade) }} />
                <button onClick={() => alternar(u.unidade)} aria-expanded={!!aberto[u.unidade]}
                  className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-left hover:bg-panel2">
                  <span className="font-mono text-xs text-mute">{aberto[u.unidade] ? '▾' : '▸'}</span>
                  <span className="truncate font-display text-lg font-bold uppercase leading-tight">{u.unidade}</span>
                  <span className="ml-auto shrink-0 font-mono text-[12.5px] text-mute">
                    {u.servidores.length} serv.{lidos.length > 0 && <> · {lidos.length - falhas} ok{falhas > 0 && <span className="font-bold text-bad"> · {falhas} falha</span>}</>}
                  </span>
                </button>
                <Button onClick={() => lerUnidade(u)} className="m-1.5 shrink-0">Ler unidade</Button>
              </div>
              {aberto[u.unidade] && u.servidores.map((s) => {
                const e = estado[s.ip];
                const chave = `srv-${s.ip ?? s.nome}`;
                const cams = (e?.cameras ?? []).filter((c) => !filtro || fold(c.nome).includes(filtro) || fold(u.unidade).includes(filtro) || fold(s.nome).includes(filtro));
                return (
                  <div key={chave} className="border-t border-line">
                    <button onClick={() => s.ip && alternar(chave, s.ip)} disabled={!s.ip} aria-expanded={!!aberto[chave]}
                      className="flex w-full items-center gap-2 py-1.5 pl-7 pr-3 text-left hover:bg-panel2 disabled:opacity-60">
                      <span className="font-mono text-xs text-mute">{aberto[chave] ? '▾' : '▸'}</span>
                      <span className="font-mono text-sm font-bold">{s.nome}</span>
                      <span className="font-mono text-[12.5px] text-mute">{s.ip ?? 'sem IP'} · {s.tipo}</span>
                      <span className="ml-auto text-right">{s.ip && <Selo e={e} />}</span>
                    </button>
                    {aberto[chave] && e && !e.carregando && (
                      e.ok ? (
                        <div className="pb-2 pl-12 pr-3">
                          <div className="mb-1 flex items-center gap-2">
                            <span className={LABEL}>lido {e.lido_em}</span>
                            <button onClick={() => ler(s.ip, true)} className="font-mono text-[12.5px] underline">reler</button>
                          </div>
                          <ul className="columns-1 gap-4 sm:columns-2">
                            {cams.map((c) => {
                              const inc = incDa(c.nome);
                              return (
                                <li key={c.nome} className="flex break-inside-avoid items-center gap-1.5 py-0.5 font-mono text-[13.75px]" title={c.descricao || undefined}>
                                  <Ponto cam={c} />
                                  <span className="truncate">{c.nome}</span>
                                  {inc && <button onClick={() => onAbrir?.(inc)} className="shrink-0 font-bold text-accent underline">{inc}</button>}
                                </li>
                              );
                            })}
                          </ul>
                          {cams.length === 0 && <p className="text-xs text-mute">Nenhuma câmera{filtro ? ' com esse filtro' : ''}.</p>}
                        </div>
                      ) : <p className="pb-2 pl-12 pr-3 font-mono text-[12.5px] text-bad">{e.erro}</p>
                    )}
                  </div>
                );
              })}
            </section>
          );
        })}
        {unidades.length === 0 && <p className="p-6 text-center text-mute">Nada com esse filtro.</p>}
      </div>
    </div>
  );
}
