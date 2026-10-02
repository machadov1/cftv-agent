import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid, LineChart, Line, Legend } from 'recharts';
import { getBreakdown, getIncidentesVolumetria, getInsights, getPainel } from '../api';
import VolumeChart from '../components/VolumeChart';
import useMetrics from '../hooks/useMetrics';
import LoadingSpinner from '../components/LoadingSpinner';
import { Kpi, NO_UNIT_COLOR, Panel, unitColor } from '../components/ui';
import { useThemeColors } from '../lib/theme';

// Métricas = o que fazer agora, onde dói e se o agente está ajudando. Todo número leva aos incidentes.

const EQUIPE_UNIDADE = { BMA: 'Barra Mansa', PIR: 'Piracicaba', MDE: 'João Monlevade', JDF: 'Juiz de Fora', RSD: 'Resende' };
const TONE = { bad: 'text-bad', warn: 'text-warn', ok: 'text-ok', accent: 'text-accent', mute: 'text-mute', ink: 'text-ink' };

const fmtDia = (iso) => {
  if (!iso) return '—';
  const d = new Date(`${iso}T12:00:00`);
  const hoje = new Date(); hoje.setHours(12, 0, 0, 0);
  const diff = Math.round((d - hoje) / 86400000);
  const dm = d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
  return diff === 0 ? `hoje (${dm})` : diff === 1 ? `amanhã (${dm})` : diff === -1 ? `ontem (${dm})` : dm;
};
const horas = (h) => (h >= 48 ? `${Math.round(h / 24)}d` : `${Math.round(h)}h`);

function Section({ title, hint }) {
  return (
    <div className="flex items-baseline gap-3 border-b-2 border-rule pb-1 lg:col-span-3">
      <h2 className="font-display text-2xl font-extrabold uppercase tracking-tight">{title}</h2>
      {hint && <span className="font-mono text-[12.5px] text-mute">{hint}</span>}
    </div>
  );
}

// Cartão de insight: número grande + uma frase + o que fazer
function Card({ tone = 'ink', value, label, children, className = '', right }) {
  return (
    <section className={`flex flex-col border-2 border-rule bg-panel ${className}`}>
      <header className="flex items-start justify-between gap-3 border-b-2 border-rule px-4 py-3">
        <div className="min-w-0">
          <div className={`font-display text-5xl font-extrabold leading-[0.85] tracking-tight tabular-nums ${TONE[tone]}`}>{value}</div>
          <div className="mt-1.5 font-mono text-[12.5px] font-bold uppercase tracking-[0.12em] text-ink">{label}</div>
        </div>
        {right}
      </header>
      <div className="flex-1 space-y-2 px-4 py-3 text-xs">{children}</div>
    </section>
  );
}

function Inc({ n, base, onCamera, title }) {
  const cls = 'border border-line bg-panel2 px-1.5 py-px font-mono text-[12.5px] hover:border-rule hover:bg-invert hover:text-invert-ink';
  if (onCamera) return <button title={title ?? 'Abrir na aba Câmeras'} onClick={() => onCamera(n)} className={cls}>{n}</button>;
  return (
    <a title={title ?? 'Abrir no ServiceNow'} className={cls} target="_blank" rel="noreferrer"
      href={`${base}/nav_to.do?uri=${encodeURIComponent(`incident.do?sysparm_query=number=${n}`)}`}>{n}</a>
  );
}

function Incs({ list, base, onCamera, max = 12 }) {
  if (!list?.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {list.slice(0, max).map((n) => <Inc key={n} n={n} base={base} onCamera={onCamera} />)}
      {list.length > max && <span className="font-mono text-[12.5px] text-mute">+{list.length - max}</span>}
    </div>
  );
}

const Note = ({ children }) => <p className="text-[13.75px] text-mute">{children}</p>;
const Row = ({ left, right, color }) => (
  <div className="flex items-center justify-between gap-2">
    <span className="flex min-w-0 items-center gap-2 truncate">
      {color && <span className="h-2.5 w-2.5 shrink-0" style={{ background: color }} />}{left}
    </span>
    <span className="shrink-0 font-mono tabular-nums">{right}</span>
  </div>
);

export default function MetricsPage({ go }) {
  const { metrics: m } = useMetrics(30000);
  const c = useThemeColors();
  const AXIS = { fill: c.mute, fontSize: 11 };
  const TIP = { background: c.panel, border: `2px solid ${c.rule}`, borderRadius: 0, fontSize: 12, color: c.ink };
  const [p, setP] = useState(null);
  const [b, setB] = useState(null);
  const [ins, setIns] = useState(null);
  const [erro, setErro] = useState(null);
  const [vol, setVol] = useState(null);
  const [volErro, setVolErro] = useState(null);

  useEffect(() => {
    getIncidentesVolumetria(5).then((v) => { setVol(v); setVolErro(null); }).catch((e) => setVolErro(e.message));
  }, []);

  useEffect(() => {
    const load = () => {
      getPainel().then((d) => { setP(d); setErro(null); }).catch((e) => setErro(e.message));
      getBreakdown().then(setB).catch(() => {});
      getInsights().then(setIns).catch(() => {});
    };
    load();
    const id = setInterval(load, 60000); // o backlog tem cache de 60 s
    return () => clearInterval(id);
  }, []);

  if (erro && !p) return <p className="p-4 text-bad">{erro}</p>;
  if (!p) return <LoadingSpinner />;

  const { agir, doi, agente } = p;
  const base = p.sn_base;
  const camera = go ? (n) => go('cameras', n) : undefined;
  const onda = agir.onda;
  const eqColor = (e) => (e === 'LORA' ? c.mock : e === 'Geral' ? c.accent : EQUIPE_UNIDADE[e] ? unitColor(EQUIPE_UNIDADE[e]) : NO_UNIT_COLOR);
  const cam = agir.cameras;
  const rt = agir.ritms;
  const proxRitm = rt.itens.find((x) => x.dias !== null && x.dias >= 0);
  const tend = agente.tendencia;

  return (
    <div className="grid h-full grid-cols-1 content-start gap-3 overflow-auto p-3 lg:grid-cols-3">
      {p.avisos?.map((a) => (
        <div key={a} className="border-2 border-warn bg-warn/15 px-3 py-2 font-mono text-[13.75px] font-bold text-warn lg:col-span-3">! {a}</div>
      ))}

      {/* ---------------- A. Para agir agora ---------------- */}
      <Section title="Para agir agora" hint={`backlog aberto: ${p.backlog_total} · atualizado ${new Date(p.atualizado_em).toLocaleTimeString('pt-BR')}`} />

      <Card className="lg:col-span-2" tone={onda.vencidos.length ? 'bad' : 'warn'}
        value={onda.pico ? onda.pico.total : 0}
        label={onda.pico ? `vencem ${fmtDia(onda.pico.dia)} · ${onda.pico.de}–${onda.pico.ate}` : 'sem prazo concentrado'}
        right={onda.vencidos.length > 0 && (
          <div className="text-right">
            <div className="font-display text-5xl font-extrabold leading-[0.85] text-bad tabular-nums">{onda.vencidos.length}</div>
            <div className="mt-1.5 font-mono text-[12.5px] font-bold uppercase tracking-[0.12em] text-bad">vencido(s)</div>
          </div>
        )}>
        {onda.pico && (
          <p className="text-sm">
            <b>{onda.pico.fracao}% do backlog</b> vence no mesmo dia. Maior parte: {onda.pico.por_equipe.slice(0, 3).map((e) => `${e.equipe} ${e.total}`).join(' · ')}.
            {onda.pico.fracao >= 50 && ' Priorize os lotes grandes (encerrar ou justificar) antes do horário de corte.'}
          </p>
        )}
        <div style={{ width: '100%', height: 170 }}>
          <ResponsiveContainer>
            <BarChart data={onda.serie} margin={{ left: -18, right: 6, top: 4 }}>
              <CartesianGrid vertical={false} stroke={c.line} />
              <XAxis dataKey="dia" tickFormatter={(d) => fmtDia(d).replace(/ \(.*\)/, '')} tick={AXIS} stroke={c.line} />
              <YAxis allowDecimals={false} tick={AXIS} stroke={c.line} />
              <Tooltip contentStyle={TIP} cursor={{ fill: c.panel2 }} labelFormatter={fmtDia} />
              <Legend wrapperStyle={{ fontSize: 11 }} iconType="square" />
              {onda.equipes.map((e) => <Bar key={e} dataKey={e} stackId="a" fill={eqColor(e)} />)}
            </BarChart>
          </ResponsiveContainer>
        </div>
        {onda.vencidos.map((v) => (
          <div key={v.number} className="flex items-center gap-2 text-bad">
            <Inc n={v.number} base={base} /><span className="min-w-0 truncate">{v.equipe} · {v.prazo_txt} · {v.titulo}</span>
          </div>
        ))}
      </Card>

      <Card tone={cam.voltou.length ? 'ok' : 'mute'} value={cam.voltou.length} label="câmera voltou · pode encerrar">
        {cam.voltou.length ? (
          <>
            <p>O último teste no Digifort deu imagem e ainda não há work note de encerramento. Anexe o print e registre a nota na aba Câmeras.</p>
            <Incs list={cam.voltou.map((x) => x.number)} onCamera={camera} />
          </>
        ) : <Note>Nenhum teste recente com a câmera de volta. Teste os incidentes em andamento na aba Câmeras.</Note>}
        {cam.sem_sinal.length > 0 && (
          <div className="border-t border-line pt-2">
            <div className="font-bold text-warn">{cam.sem_sinal.length} ainda sem sinal no último teste</div>
            <Incs list={cam.sem_sinal.map((x) => x.number)} onCamera={camera} />
          </div>
        )}
      </Card>

      <Card tone={cam.desativada.length ? 'warn' : 'mute'} value={cam.desativada.length} label="câmera desativada no cadastro">
        {cam.desativada.length ? (
          <>
            <p><b>Não é queda de rede:</b> a câmera está desativada no Digifort. Quem resolve é quem administra o servidor, não o campo. Um pedido só cobre todas.</p>
            {cam.desativada.map((x) => (
              <div key={x.number} className="flex items-center gap-2">
                <Inc n={x.number} base={base} onCamera={camera} />
                <span className="truncate font-mono text-[12.5px] text-mute">{Object.keys(x.cameras).join(' · ')}</span>
              </div>
            ))}
          </>
        ) : <Note>Nenhuma câmera desativada nos testes.</Note>}
      </Card>

      <Card tone={agir.parados.total ? 'warn' : 'ok'} value={agir.parados.total} label="parados há 2+ dias sem nota">
        {agir.parados.total ? (
          <>
            <p>Em andamento sem anotação nova. {agir.parados.por_equipe.map((e) => `${e.equipe} ${e.total}`).join(' · ')}.</p>
            {agir.parados.itens.slice(0, 5).map((x) => (
              <div key={x.number} className="flex items-center gap-2">
                <Inc n={x.number} base={base} /><span className="shrink-0 font-mono font-bold text-warn">{horas(x.horas)}</span>
                <span className="min-w-0 truncate text-mute">{x.titulo}</span>
              </div>
            ))}
            {agir.parados.total > 5 && <Incs list={agir.parados.itens.slice(5).map((x) => x.number)} base={base} max={20} />}
          </>
        ) : <Note>Todo incidente em andamento teve nota nos últimos 2 dias.</Note>}
      </Card>

      <Card tone={rt.vencidas.length ? 'bad' : rt.vencendo.length ? 'warn' : 'ink'} value={rt.abertas} label="RITMs de acompanhamento abertas">
        {rt.vencidas.length > 0 && <p className="font-bold text-bad">{rt.vencidas.length} passou(aram) dos 20 dias: {rt.vencidas.map((x) => x.ritm).join(', ')}.</p>}
        {rt.vencendo.length > 0 && <p className="font-bold text-warn">{rt.vencendo.length} fecha(m) em até 5 dias: {rt.vencendo.map((x) => `${x.ritm} (${x.dias}d)`).join(', ')}.</p>}
        {!rt.vencidas.length && !rt.vencendo.length && proxRitm && (
          <p>Próximo fechamento: <b>{proxRitm.ritm}</b> em {proxRitm.dias} dias ({proxRitm.unidade}, {proxRitm.pendencia}).</p>
        )}
        <div className="space-y-1 border-t border-line pt-2">
          <div className="font-mono text-[12.5px] font-bold uppercase tracking-wider text-mute">Dependemos de</div>
          {rt.por_pendencia.map((x) => <Row key={x.pendencia} left={x.pendencia} right={x.total} />)}
        </div>
      </Card>

      <Card tone={agir.sem_destino.fila.length ? 'bad' : agir.sem_destino.backlog.length ? 'warn' : 'ok'}
        value={agir.sem_destino.backlog.length + agir.sem_destino.fila.length} label="sem localidade reconhecida">
        <p>{agir.sem_destino.fila.length} na fila local (bloqueados para despacho) · {agir.sem_destino.backlog.length} no backlog sem unidade pelas regras.</p>
        {agir.sem_destino.fila.length > 0 && <Incs list={agir.sem_destino.fila} base={base} />}
        {agir.sem_destino.sugestoes.filter((s) => s.resolveria > 0).map((s) => (
          <p key={s.prefixo} className="font-bold text-accent">Aceitar o prefixo {s.prefixo}- → {s.localidade} resolveria {s.resolveria} agora (aba Regras).</p>
        ))}
        {agir.sem_destino.backlog.length > 0 && (
          <Note>No backlog, unidade sem regra (ex.: Belgo Arames) cai aqui: crie a regra para o agente reconhecer da próxima vez.</Note>
        )}
      </Card>

      {/* ---------------- B. Onde dói ---------------- */}
      <Section title="Onde dói" hint="fila local + backlog + RITMs, cruzados pelo código da câmera" />

      <Panel title="Pontos quentes por setor" className="lg:col-span-2" bodyClass="p-0">
        {doi.pontos_quentes.length === 0 ? <div className="p-4 text-xs text-mute">Nenhum setor com 2+ incidentes.</div> : (() => {
          const max = Math.max(...doi.pontos_quentes.map((x) => x.incidentes.length));
          return doi.pontos_quentes.map((x) => (
            <div key={x.area} className="grid grid-cols-[110px_1fr_auto] items-center gap-3 border-b border-line px-4 py-2 text-xs last:border-b-0">
              <span className="font-mono font-bold">{x.area}</span>
              <div>
                <div className="h-3" style={{ width: `${(100 * x.incidentes.length) / max}%`, background: unitColor(x.unidade) }} />
                <div className="mt-1 truncate font-mono text-[12.5px] text-mute" title={x.cameras.join(', ')}>
                  {x.unidade} · {x.cameras.length} câmera(s): {x.cameras.slice(0, 6).join(' ')}{x.cameras.length > 6 ? ' …' : ''}
                </div>
              </div>
              <span className="font-display text-2xl font-extrabold tabular-nums" title={x.incidentes.join(', ')}>{x.incidentes.length}</span>
            </div>
          ));
        })()}
        <div className="border-t-2 border-rule px-4 py-2 text-[13.75px] text-mute">
          Setor com várias câmeras caindo costuma ter causa comum (switch, fibra, alimentação do quadro): vale uma RITM de infraestrutura para o setor em vez de incidente por câmera.
        </div>
      </Panel>

      <Panel title="Câmeras crônicas" bodyClass="space-y-3 p-4">
        {doi.cronicas.length === 0 && <div className="text-xs text-mute">Nenhuma câmera repetida.</div>}
        {doi.cronicas.map((x) => {
          const ritms = x.incidentes.filter((i) => i.fonte.startsWith('RITM'));
          return (
            <div key={x.camera} className="text-xs">
              <Row left={<><span className="font-mono font-bold">{x.camera}</span><span className="text-mute">· {x.unidade}</span></>}
                right={`${x.incidentes.length}×`} color={unitColor(x.unidade)} />
              {ritms.length > 1 && <div className="mt-0.5 font-bold text-warn">em {ritms.length} RITMs diferentes: {ritms.map((i) => i.fonte.replace('RITM ', '')).join(', ')}</div>}
              <div className="mt-1"><Incs list={x.incidentes.map((i) => i.number)} base={base} /></div>
            </div>
          );
        })}
      </Panel>

      <Panel title={`LORA · ${doi.lora.total} de ${doi.lora.de} do backlog`} bodyClass="space-y-2 p-4 text-xs">
        {doi.lora.total === 0 ? <div className="text-mute">Sem incidentes LORA abertos.</div> : (
          <>
            <div className="grid grid-cols-2 gap-2">
              <div><div className="font-display text-3xl font-extrabold tabular-nums">{doi.lora.idade_media_d}d</div><div className="font-mono text-[12.5px] uppercase text-mute">idade média</div></div>
              <div><div className="font-display text-3xl font-extrabold tabular-nums text-warn">{doi.lora.mais_antigo_d}d</div><div className="font-mono text-[12.5px] uppercase text-mute">mais antigo</div></div>
            </div>
            <Note>{Math.round((100 * doi.lora.total) / Math.max(1, doi.lora.de))}% do backlog é tag LORA. Tratar em lote (mesma nota, mesmo encaminhamento) libera a fila de câmeras.</Note>
            {doi.lora.tags_repetidas.map((t) => (
              <div key={t.tag}><span className="font-mono font-bold">TAG {t.tag}</span> em {t.incidentes.length}: <Incs list={t.incidentes} base={base} /></div>
            ))}
          </>
        )}
      </Panel>

      {ins && Object.keys(ins.temas).length > 0 && (
        <Panel title="Temas por unidade" className="lg:col-span-2" bodyClass="grid gap-4 p-4 md:grid-cols-3">
          {Object.entries(ins.temas).map(([tema, t]) => (
            <div key={tema} className="text-xs">
              <div className="flex justify-between font-bold"><span>{tema}</span><span className="font-mono">{t.total}</span></div>
              {t.por_unidade.map((u) => <Row key={u.localidade} left={<span className="text-mute">{u.localidade}</span>} right={u.total} color={unitColor(u.localidade)} />)}
            </div>
          ))}
        </Panel>
      )}

      {/* ---------------- C. O agente está ajudando? ---------------- */}
      <Section title="O agente está ajudando?" hint="fila local e histórico de ações" />

      <section className="flex flex-wrap border-2 border-rule bg-panel lg:col-span-3">
        <Kpi label="Despachados" value={agente.despachados} hint="primeira tratativa pelo painel" />
        <Kpi label="Até despachar" value={agente.mediana_ate_despacho_h ?? '—'} unit="h" hint="mediana: aberto no SN → despacho" />
        <Kpi label="Sem edição" value={agente.sem_edicao_pct ?? '—'} unit="%" tone="ok" hint="sugestão aceita como veio" />
        <Kpi label="Sem LLM" value={agente.sem_llm_pct ?? '—'} unit="%" tone="accent" hint="decidido só por regras" />
        <Kpi label="LLM hoje" value={m?.chamadas_claude_hoje ?? '—'} hint="chamadas ao 9router" />
        <Kpi label="Testes de câmera" value={agente.testes_camera} hint="Digifort, últimos 60 dias" />
        <Kpi label="Reanálises" value={agente.reanalises_media ?? '—'} unit="×" tone={agente.reanalises_media > 2 ? 'warn' : 'ink'} hint="análises por incidente" />
      </section>

      <Panel title="Backlog dia a dia" className="lg:col-span-2" bodyClass="p-3">
        {tend.pontos < 3 ? (
          <div className="p-6 text-center text-xs text-mute">
            Coletando {tend.coletando_desde ? `desde ${fmtDia(tend.coletando_desde)}` : 'a partir de hoje'} ({tend.pontos} dia(s)).
            Com 3 dias aparece a tendência: total, vencidos, quanto entra e quanto sai por dia.
            {tend.serie.length > 0 && (
              <div className="mt-2 font-mono">{tend.serie.map((s) => `${fmtDia(s.dia)}: ${s.total} abertos, ${s.vencidos} vencidos`).join(' · ')}</div>
            )}
          </div>
        ) : (
          <div style={{ width: '100%', height: 200 }}>
            <ResponsiveContainer>
              <LineChart data={tend.serie} margin={{ left: -18, right: 8, top: 6 }}>
                <CartesianGrid vertical={false} stroke={c.line} />
                <XAxis dataKey="dia" tickFormatter={(d) => d.slice(8, 10) + '/' + d.slice(5, 7)} tick={AXIS} stroke={c.line} />
                <YAxis allowDecimals={false} tick={AXIS} stroke={c.line} />
                <Tooltip contentStyle={TIP} labelFormatter={fmtDia} />
                <Legend wrapperStyle={{ fontSize: 11 }} iconType="square" />
                <Line dataKey="total" name="abertos" stroke={c.ink} strokeWidth={2.5} dot={false} />
                <Line dataKey="vencidos" stroke={c.bad} strokeWidth={2} dot={false} />
                <Line dataKey="entraram" stroke={c.warn} strokeWidth={1.5} dot={false} />
                <Line dataKey="sairam" name="saíram" stroke={c.ok} strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>

      <Panel title="Volumetria · incidentes, últimos 5 meses" bodyClass="p-3">
        {vol && (
          <div className="mb-1 font-mono text-[12.5px] text-mute">
            {vol.total_encerrados} encerrados · {vol.total_entraram} entraram · * mês em andamento
          </div>
        )}
        <VolumeChart data={vol} error={volErro} height={200} />
      </Panel>

      <Panel title="Fila local por localidade" bodyClass="space-y-1.5 p-4 text-xs">
        {!b?.por_localidade?.length && <div className="text-mute">—</div>}
        {b?.por_localidade?.map((r) => (
          <Row key={r.localidade} left={r.localidade} right={r.total} color={r.localidade === 'Sem destino' ? c.bad : unitColor(r.localidade)} />
        ))}
      </Panel>
    </div>
  );
}
