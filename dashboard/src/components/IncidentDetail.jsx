import { useCallback, useEffect, useRef, useState } from 'react';
import {
  approveIncident, closeIncident, emailA4Abrir, emailA4Preview, getDestinos, getIncidentHost, getPayload, pingEvidenceUrl, pingIncident, pingRegistrar, refreshIncident, teamsDraft,
} from '../api';
import { HOLD_MS } from './HoldButton';
import RitmPanel from './RitmPanel';
import CameraPanel from './CameraPanel';
import { Badge, Button, ConfBar, statusLabel, statusTone, timeAgo, unitColor } from './ui';

const LABEL = 'font-mono text-[12.5px] font-bold uppercase tracking-[0.14em] text-mute';

function Cell({ label, children, mono, className = '' }) {
  return (
    <div className={`min-w-0 border-b border-r border-line px-5 py-2.5 ${className}`}>
      <div className={LABEL}>{label}</div>
      <div className={`mt-0.5 truncate text-[13px] ${mono ? 'font-mono' : 'font-semibold'}`}>{children}</div>
    </div>
  );
}

// Segurar para confirmar: gesto deliberado, evita clique acidental num botão que grava no ServiceNow
function useHold(onComplete, disabled, ms = HOLD_MS) {
  const raf = useRef(0);
  const t0 = useRef(0);
  const bar = useRef(null);
  const cb = useRef(onComplete);
  cb.current = onComplete;

  const stop = useCallback(() => {
    cancelAnimationFrame(raf.current);
    if (bar.current) bar.current.style.width = '0';
  }, []);
  const tick = useCallback(() => {
    const p = Math.min((performance.now() - t0.current) / ms, 1);
    if (bar.current) bar.current.style.width = `${p * 100}%`;
    if (p >= 1) { stop(); cb.current(); return; }
    raf.current = requestAnimationFrame(tick);
  }, [ms, stop]);
  const start = () => {
    if (disabled) return;
    t0.current = performance.now();
    raf.current = requestAnimationFrame(tick);
  };
  useEffect(() => stop, [stop]);

  return {
    bar,
    handlers: {
      onMouseDown: start, onMouseUp: stop, onMouseLeave: stop, onTouchStart: start, onTouchEnd: stop, onBlur: stop,
      onKeyDown: (e) => { if ((e.key === 'Enter' || e.key === ' ') && !e.repeat) { e.preventDefault(); start(); } },
      onKeyUp: stop,
    },
  };
}

export default function IncidentDetail({ incident, meta, onChanged }) {
  const [editing, setEditing] = useState(false);
  const [ritm, setRitm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [payload, setPayload] = useState(null);
  const [scom, setScom] = useState(null); // resultado do ping automático (alerta SCOM)
  const [scomBusy, setScomBusy] = useState(false);
  const [registro, setRegistro] = useState(null);
  const [payloadTick, setPayloadTick] = useState(0);
  const [det, setDet] = useState(null);
  const [fired, setFired] = useState(null);
  const [destinos, setDestinos] = useState([]);
  const [dest, setDest] = useState('');
  const [title, setTitle] = useState('');
  const [nota, setNota] = useState('');
  const [reler, setReler] = useState(null); // { busy } | { text, ok }
  const [acesso, setAcesso] = useState(null);
  const [emailA4, setEmailA4] = useState(null);
  const [a4Prev, setA4Prev] = useState(null);
  const [closeNote, setCloseNote] = useState('');
  const [closing, setClosing] = useState(null);
  const [impact, setImpact] = useState('');
  const [urgency, setUrgency] = useState('');

  useEffect(() => {
    if (editing && destinos.length === 0) getDestinos().then(setDestinos).catch(() => {});
    if (!editing) {
      setDest('');
      setTitle(incident?.short_description || '');
      setNota('');
    }
  }, [editing, incident?.short_description]);

  useEffect(() => {
    setEditing(false);
    setMsg(null);
    setFired(null);
    setRitm(!!incident?.ritm_necessaria);
    setTitle(incident?.short_description || '');
    setNota('');
    setAcesso(null);
    setEmailA4(null);
    setImpact('');
    setUrgency('');
  }, [incident?.incident_number, incident?.ritm_necessaria, incident?.short_description]);

  useEffect(() => { setReler(null); }, [incident?.incident_number]);

  useEffect(() => {
    if (!incident?.grupo || incident.status !== 'analisado') { setPayload(null); return; }
    getPayload(incident.incident_number).then(setPayload).catch((e) => setPayload({ error: e.message }));
  }, [incident?.incident_number, incident?.grupo, incident?.status, incident?.titulo_padrao, payloadTick]);

  useEffect(() => {
    setDet(null);
    setScom(null);
    setRegistro(null);
    if (!incident) return;
    getIncidentHost(incident.incident_number).then(setDet).catch(() => setDet(null));
  }, [incident?.incident_number]);

  // Alerta SCOM: ping de 10 pacotes + imagem da saída real; a prévia passa a mostrar a nota de validação
  const runPing = useCallback(async () => {
    if (!incident) return;
    setScomBusy(true);
    setRegistro(null);
    try { setScom({ ...(await pingIncident(incident.incident_number)), at: Date.now() }); } catch (e) { setScom({ erro: e.message }); }
    setScomBusy(false);
    setPayloadTick((t) => t + 1);
  }, [incident?.incident_number]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (det?.scom && det.host && incident?.status === 'analisado') runPing();
  }, [det, runPing]); // eslint-disable-line react-hooks/exhaustive-deps

  const hasGroup = !!incident?.grupo;
  // etapa: Entrada (despachar/editar) -> Saída (despachado ou tratado fora: RITM, e-mail, nota, encerrar) -> encerrado
  const etapa = incident?.status === 'analisado' ? 'entrada'
    : incident?.status === 'aprovado' || incident?.status === 'tratado_fora' ? 'saida' : 'encerrado';
  const approved = etapa !== 'entrada';  // fora da Entrada não há despacho nem edição
  // destino escolhido à mão na edição (para incidentes sem localidade ou com sugestão errada)
  const chosen = editing ? destinos.find((d) => d.localidade === dest) : null;
  const canDispatch = hasGroup || !!chosen;
  const targetGroup = chosen ? chosen.grupo_display : incident?.grupo_display;

  const approve = async () => {
    if (busy || !incident) return;
    setBusy(true);
    setMsg(null);
    try {
      // a linha de severidade (impacto/urgência) é montada no backend e somada à nota escolhida
      const overrides = editing
        ? {
            ritm_necessaria: ritm,
            ...(chosen ? { localidade: chosen.localidade, grupo: chosen.grupo, grupo_display: chosen.grupo_display } : {}),
            ...(title && title !== incident?.short_description ? { short_description: title } : {}),
            ...(nota.trim() ? { work_notes: nota.trim() } : {}),
            ...(impact ? { impact } : {}),
            ...(urgency ? { urgency } : {}),
          }
        : {};
      const r = await approveIncident(incident.incident_number, overrides);
      const extra = [r.editado && 'editado', r.anexo && `evidência ${r.anexo}`,
        r.fields?.work_notes?.startsWith('Causa base') && 'nota de validação SCOM'].filter(Boolean);
      setFired({ sub: r.dry_run ? 'simulado · dry-run' : 'gravado no servicenow', at: Date.now() });
      setMsg({ ok: true, text: `${r.dry_run ? 'Simulado (dry-run)' : 'Aplicado no ServiceNow'} em ${Math.round(r.tempo_ms)} ms${extra.map((x) => ` · ${x}`).join('')}` });
      onChanged?.();
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    }
    setBusy(false);
  };

  const hold = useHold(approve, busy || !canDispatch || approved);

  const registrar = async () => {
    if (!incident || registro?.busy) return;
    setRegistro({ busy: true });
    try {
      const r = await pingRegistrar(incident.incident_number);
      setRegistro({ ok: true, text: `${r.status} · evidência ${r.anexo}${r.dry_run ? ' · simulado (dry-run)' : ''}` });
    } catch (e) { setRegistro({ ok: false, text: e.message }); }
  };
  const holdReg = useHold(registrar, !scom?.ok || !!registro?.busy || !!registro?.ok);
  const holdClose = useHold(() => runClose(), !closeNote.trim() || !!closing?.busy);

  // e-mail A4: prévia montada no backend (modelo do .oft) assim que o chamado A4 está na Saída
  useEffect(() => {
    setA4Prev(null);
    setEmailA4(null);
    if (!incident?.a4 || etapa !== 'saida') return;
    emailA4Preview(incident.incident_number).then(setA4Prev).catch((e) => setA4Prev({ erro: e.message }));
  }, [incident?.incident_number, incident?.a4, etapa]);

  if (!incident) {
    return (
      <section className="flex h-full items-center justify-center p-8 text-center">
        <div>
          <div className="font-display text-3xl font-extrabold uppercase tracking-tight">Nenhum ticket aberto</div>
          <p className="mt-2 text-mute">Selecione um incidente na fila ou processe um número para ver a decisão sugerida.</p>
        </div>
      </section>
    );
  }

  const isScom = !!det?.scom || incident.localidade === 'Projects (monitoramento)';
  const ficha = scom?.ficha ?? det?.ficha;

  const runReler = async () => {
    setReler({ busy: true });
    try {
      const r = await refreshIncident(incident.incident_number);
      setReler({ ok: true, text: r.mudou ? `atualizado${r.camera_codigo ? ` · ${r.camera_codigo}` : ''}` : 'sem mudança' });
      onChanged?.();
    } catch (e) { setReler({ ok: false, text: e.message }); }
  };
  const runAcesso = async (abrir) => {
    try { setAcesso(await teamsDraft(incident.incident_number, { modelo: 'acesso', abrir })); }
    catch (e) { setAcesso({ erro: e.message }); }
  };
  const runA4Email = async () => {
    try {
      const r = await emailA4Abrir(incident.incident_number);
      window.location.href = r.mailto;  // app de e-mail padrão (Outlook clássico ou novo): só rascunho
      setEmailA4(r);
    }
    catch (e) { setEmailA4({ erro: e.message }); }
  };
  const runClose = async () => {
    if (closing?.busy) return;
    setClosing({ busy: true });
    try {
      const r = await closeIncident(incident.incident_number, closeNote.trim());
      setClosing(r);
      if (!r.simulado) onChanged?.();
    } catch (e) { setClosing({ erro: e.message }); }
  };

  const titleWarn = payload?.warnings?.some((w) => /^Título/.test(w));
  const showStamp = fired || incident.status === 'aprovado';
  const origem = meta?.chamou_claude === undefined ? '—' : meta.chamou_claude ? 'Regras + LLM' : 'Regras locais';

  return (
    <section className="relative flex h-full min-h-0 flex-col overflow-hidden">
      {showStamp && (
        <div key={fired?.at ?? 'static'} className={`stamp ${fired ? 'fire' : ''}`} aria-hidden="true">
          Despachado<small>{fired?.sub ?? 'aprovado'}</small>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-auto">
        {/* Cabeça */}
        <div className="border-b-2 border-rule px-5 py-3">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[13px] font-bold text-bad">{incident.incident_number}</span>
            <div className="flex items-center gap-2">
              {reler?.text && <span className={`font-mono text-[12.5px] ${reler.ok ? 'text-ok' : 'text-bad'}`}>{reler.text}</span>}
              {incident.status === 'analisado' && (
                <button onClick={runReler} disabled={reler?.busy} title="Relê o incidente e o Número do Objeto no ServiceNow (só leitura) e reaplica as regras"
                  className="border-2 border-rule px-2 py-0.5 font-mono text-[12.5px] font-bold uppercase tracking-wider hover:bg-panel2 disabled:opacity-50">
                  {reler?.busy ? 'relendo…' : 'Reler'}
                </button>
              )}
              <Badge tone={statusTone(incident.status)}>{statusLabel(incident.status)}</Badge>
            </div>
          </div>
          <h1 className="mt-1 font-display text-4xl font-extrabold uppercase leading-[0.98] tracking-tight">
            {incident.titulo_padrao ?? incident.short_description}
          </h1>
          {incident.titulo_padrao && incident.titulo_padrao !== incident.short_description && (
            <p className="mt-1.5 font-mono text-[13.75px] text-mute">
              título original: <span className="text-ink">{incident.short_description}</span>
            </p>
          )}
          {incident.titulo_padrao && !incident.titulo_ok && (
            <p className="mt-1 font-mono text-[13.75px] font-bold text-warn">! título fora do padrão: confira antes de despachar</p>
          )}
          {(incident.description || incident.descricao_util) && (
            <div className="mt-3">
              <div className={LABEL}>Descrição</div>
              <pre className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap break-words border border-line bg-panel2 px-3 py-2 font-sans text-xs leading-snug">
                {incident.description || incident.descricao_util}
              </pre>
            </div>
          )}
        </div>

        {/* Roteamento */}
        <div className="grid grid-cols-[1fr_auto_1fr] items-stretch border-b-2 border-rule">
          <div className="border-l-[10px] px-5 py-3" style={{ borderColor: unitColor(incident.localidade) }}>
            <div className={LABEL}>Localidade</div>
            {editing ? (
              <select
                value={dest}
                onChange={(e) => setDest(e.target.value)}
                aria-label="Localidade de destino"
                className="mt-1 w-full border-2 border-rule bg-panel px-2 py-1.5 font-display text-xl font-bold"
              >
                <option value="">{incident.localidade ? `manter: ${incident.localidade}` : '— escolha a localidade —'}</option>
                {destinos.map((d) => <option key={d.localidade} value={d.localidade}>{d.localidade}</option>)}
              </select>
            ) : (
              <div className={`mt-1 font-display text-3xl font-extrabold leading-none ${incident.localidade ? '' : 'text-bad'}`}>
                {incident.localidade ?? 'Sem localidade'}
              </div>
            )}
          </div>
          <div className="flex items-center border-x border-line px-3 font-display text-5xl font-extrabold text-mute">→</div>
          <div className="px-5 py-3">
            <div className={LABEL}>Fila de destino{chosen && ' (escolhida por você)'}</div>
            <div className={`mt-1 font-display text-3xl font-extrabold leading-none ${canDispatch ? 'text-ok' : 'text-warn'}`}>
              {targetGroup ?? 'sem grupo'}
            </div>
          </div>
        </div>

        {/* Dados */}
        <div className="grid grid-cols-2 border-b-2 border-rule [&>div:nth-child(2n)]:border-r-0">
          <Cell label="Confiança da localidade"><ConfBar value={incident.localidade_confianca ?? 0} /></Cell>
          <Cell label="Origem da decisão">{origem}</Cell>
          <Cell label="RITM">
            {editing ? (
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={ritm} onChange={(e) => setRitm(e.target.checked)} className="accent-[var(--c-accent)]" />
                necessária
              </label>
            ) : incident.ritm_necessaria ? <span className="text-warn">SIM</span> : 'NÃO'}
          </Cell>
          <Cell label="Categoria">{incident.categoria ?? '—'}</Cell>
          <Cell label="Pendência">{incident.pendencia ?? '—'}</Cell>
          <Cell label="Analisado há" mono>{timeAgo(incident.updated_at)}</Cell>
          <Cell label="Solicitante">{incident.caller_id ?? '—'}</Cell>
          {incident.opened_at && (
            <Cell label="Aberto em" mono>
              {new Date(incident.opened_at).toLocaleString('pt-BR', { timeZone: 'UTC' })}
            </Cell>
          )}
          <Cell label="Por quê" mono truncate>
            <span>{incident.motivo || '—'}</span>
            {incident.camera_codigo && <span className="ml-2 text-mute">(ref: {incident.camera_codigo})</span>}
          </Cell>
          {!incident.opened_at && <Cell label="sys_id" mono className="col-span-2 !border-r-0">{incident.sys_id ?? '—'}</Cell>}
          {incident.opened_at && <Cell label="sys_id" mono className="col-span-2 !border-r-0">{incident.sys_id ?? '—'}</Cell>}
        </div>

        {incident.status === 'tratado_fora' && (
          <div className="border-b-2 border-rule bg-panel2 px-5 py-2.5 font-mono text-[13.75px]">
            <b>Tratado fora do agente</b> · agora em {incident.sn_grupo || '—'}
            {incident.nota_autor && <> · última nota de {incident.nota_autor}</>}
            <span className="text-mute"> · despacho desligado; RITM, e-mail e encerramento seguem abaixo</span>
          </div>
        )}
        {incident.status === 'encerrado' && (
          <div className="border-b-2 border-rule bg-panel2 px-5 py-2.5 font-mono text-[13.75px]">
            <b>Encerrado no ServiceNow</b> · só leitura{incident.sn_grupo && ` · ${incident.sn_grupo}`}
          </div>
        )}

        {incident.pistas?.length > 0 && (
          <div className="border-b-2 border-rule px-5 py-2.5">
            <div className={LABEL}>Pistas fora do texto</div>
            <ul className="mt-1 space-y-0.5 font-mono text-[13.75px]">
              {incident.pistas.map((p) => {
                const bate = p.unidade === incident.localidade || `${p.unidade} (LORA)` === incident.localidade;
                return (
                  <li key={p.fonte} className={bate ? '' : 'text-warn'}>
                    <span className="text-mute">{p.fonte}:</span> {p.valor} → <b>{p.unidade}</b>
                    {bate ? <span className="text-ok"> · confere</span> : <span className="font-bold"> · diferente da localidade</span>}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {!canDispatch && !approved && (
          <div className="border-b-2 border-rule bg-warn/15 px-5 py-3 text-xs font-semibold text-warn">
            {incident.pendencia?.startsWith('Mover só')
              ? incident.pendencia
              : 'Sem grupo de destino. Clique em Editar para escolher a fila à mão, ou crie uma regra na aba Regras: nada será movido enquanto isso.'}
          </div>
        )}
        {(chosen || editing) && (
          <div className="space-y-2 border-b-2 border-rule bg-accent/10 px-5 py-3">
            {chosen && (
              <div className="font-mono text-[13.75px] font-bold">
                Destino manual: o título, o IC e a fila serão os de {chosen.localidade}. A prévia do PATCH não se aplica à edição.
              </div>
            )}
            {editing && (
              <div className="space-y-1.5">
                <div>
                  <label className="font-mono text-[12.5px] font-bold uppercase tracking-wider text-mute">Título editável</label>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className="mt-0.5 w-full border-2 border-rule bg-panel px-2 py-1.5 text-sm font-bold"
                  />
                </div>
                <div>
                  <label className="font-mono text-[12.5px] font-bold uppercase tracking-wider text-mute">Work note (opcional)</label>
                  <textarea
                    value={nota}
                    onChange={(e) => setNota(e.target.value)}
                    rows={2}
                    className="mt-0.5 w-full border-2 border-rule bg-panel px-2 py-1.5 font-mono text-[13.75px]"
                    placeholder="Em branco: vai a nota da prévia (validação SCOM, teste da câmera ou Encaminhado para equipe.)"
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="font-mono text-[12.5px] font-bold uppercase tracking-wider text-mute">Impacto (opcional)</label>
                    <select
                      value={impact}
                      onChange={(e) => setImpact(e.target.value)}
                      className="mt-0.5 w-full border-2 border-rule bg-panel px-2 py-1.5 font-display text-sm font-bold"
                    >
                      <option value="">não alterar</option>
                      <option value="1">1 · Altíssimo</option>
                      <option value="2">2 · Alto</option>
                      <option value="3">3 · Médio</option>
                      <option value="4">4 · Baixo</option>
                    </select>
                  </div>
                  <div>
                    <label className="font-mono text-[12.5px] font-bold uppercase tracking-wider text-mute">Urgência (opcional)</label>
                    <select
                      value={urgency}
                      onChange={(e) => setUrgency(e.target.value)}
                      className="mt-0.5 w-full border-2 border-rule bg-panel px-2 py-1.5 font-display text-sm font-bold"
                    >
                      <option value="">não alterar</option>
                      <option value="1">1 · Imediato</option>
                      <option value="2">2 · Muito alto</option>
                      <option value="3">3 · Alto</option>
                      <option value="4">4 · Baixo</option>
                    </select>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* PATCH */}
        {hasGroup && !chosen && !approved && payload && (
          <div className="ruled border-b-2 border-rule px-5 py-3">
            <div className={`${LABEL} mb-1.5`}>Ao despachar, enviar (PATCH único)</div>
            {payload.error ? (
              <p className="bg-bad/15 px-2.5 py-2 text-xs font-semibold text-bad">{payload.error}</p>
            ) : (
              <>
                <div className="font-mono text-xs leading-[22px]">
                  {Object.entries(payload.fields).map(([k, v]) => (
                    <div key={k} className="break-all">
                      {k}:{' '}
                      <span className={k === 'short_description' && titleWarn ? 'bg-warn/30 px-1 font-bold text-ink' : ''}>{String(v)}</span>
                    </div>
                  ))}
                </div>
                {payload.warnings.map((w) => (
                  <p key={w} className="mt-1 font-mono text-[13.75px] font-bold text-warn">! {w}</p>
                ))}
              </>
            )}
          </div>
        )}

        {det?.scom && det.host && (
          <div className="border-b-2 border-rule px-5 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className={`${LABEL} mr-auto`}>
                Alerta SCOM · validação automática <span className="ml-2 text-ink">{det.host}</span>
              </div>
              {!scomBusy && (
                <button onClick={runPing} className="font-mono text-[12.5px] text-mute underline hover:text-ink">
                  {scom ? 'testar de novo' : 'testar agora'}
                </button>
              )}
            </div>
            {scomBusy && <p className="mt-2 animate-pulse font-mono text-[13.75px] text-mute">pingando 10 pacotes (~12 s)…</p>}
            {scom?.erro && <p className="mt-2 text-xs font-bold text-bad">{scom.erro}</p>}
            {scom?.ping && !scomBusy && (
              <div className="mt-2 space-y-2 text-xs">
                <div className={`font-mono font-bold ${scom.ok ? 'text-ok' : 'text-bad'}`}>
                  {scom.host} · {scom.ping.ip ?? 'sem IP'} · perda {scom.ping.perda_percentual ?? '—'}%
                  {scom.ok && !approved ? ' · a nota de validação e a imagem vão no despacho' : ''}
                </div>
                {scom.aviso && <div className="font-semibold text-warn">{scom.aviso} O despacho segue com "Encaminhado para equipe.".</div>}
                {scom.ok && (
                  <img src={pingEvidenceUrl(incident.incident_number, scom.at)} alt={`Evidência do ping de ${scom.host}`}
                    className="max-w-full border-2 border-rule" />
                )}
                {scom.ok && <div className="text-[13.75px] text-mute">{scom.ressalva}</div>}
                {scom.ok && etapa === 'saida' && (
                  <div className="flex items-center gap-3">
                    <button {...holdReg.handlers} disabled={!!registro?.busy || !!registro?.ok}
                      className="relative overflow-hidden bg-invert px-4 py-2 text-left font-display text-sm font-extrabold uppercase tracking-wide text-invert-ink hover:opacity-90 disabled:opacity-50">
                      {registro?.busy ? 'Registrando…' : 'Registrar validação'}
                      <span className="block font-mono text-[11.25px] font-normal normal-case tracking-[0.1em] opacity-75">anexa a imagem + work note · mantenha pressionado</span>
                      <span ref={holdReg.bar} className="absolute bottom-0 left-0 h-1 w-0 bg-bad" />
                    </button>
                    {registro?.text && <span className={`font-mono text-[12.5px] font-bold ${registro.ok ? 'text-ok' : 'text-bad'}`}>{registro.text}</span>}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        {ficha && (
          <div className="border-b-2 border-rule px-5 py-2 font-mono text-[13.75px] text-mute">
            <span className={`${LABEL} mr-2`}>Servidor</span>
            {[ficha.nome, ficha.unidade, ficha.tipo, ficha.ip, ficha.so, ficha.modelo].filter(Boolean).join(' · ')}
            {ficha.obs && <span> · {ficha.obs}</span>}
          </div>
        )}

        {incident.camera_codigo && (
          <CameraPanel key={`cam-${incident.incident_number}`} number={incident.incident_number} hint={incident.camera_codigo} />
        )}

        {incident.acesso && etapa === 'saida' && (
          <div className="border-b-2 border-rule px-5 py-3">
            <div className={LABEL}>Pedido de acesso às câmeras (LGPD)</div>
            <p className="mt-1 text-xs text-mute">
              O acesso depende de aprovação gerencial: o despacho registra a orientação na work note e o solicitante abre a
              requisição pelo portal. Não encerrar sem pedido explícito.
            </p>
            <div className="mt-2 flex gap-2">
              <Button onClick={() => runAcesso(false)}>Ver mensagem Teams</Button>
              <Button onClick={() => runAcesso(true)}>Abrir no Teams</Button>
            </div>
            {acesso?.erro && <p className="mt-1 text-xs text-bad">{acesso.erro}</p>}
            {acesso?.mensagem && (
              <>
                <p className="mt-1 text-[13.75px] text-mute">Para {acesso.solicitante} · {acesso.email} · cole o link da requisição no lugar de [LINK]</p>
                <pre className="mt-1 whitespace-pre-wrap border border-line px-2 py-1.5 font-mono text-[13.75px] text-mute">{acesso.mensagem}</pre>
                <p className="text-[13.75px] text-warn">{acesso.aberto ? 'Chat aberto com a mensagem pré-preenchida. ' : ''}{acesso.aviso}</p>
              </>
            )}
          </div>
        )}

        {incident.a4 && (
          <div className="border-b-2 border-rule px-5 py-3">
            <div className={LABEL}>Chamado A4 ({incident.a4})</div>
            <p className="mt-1 text-xs text-mute">
              Fila: {incident.a4_fila ?? '—'}. O e-mail abre como rascunho no seu app de e-mail: você confere e envia.
            </p>
            {etapa === 'saida' ? (
              <>
                {a4Prev?.erro && <p className="mt-1 text-xs font-bold text-bad">{a4Prev.erro}</p>}
                {!a4Prev && <p className="mt-1 animate-pulse font-mono text-[12.5px] text-mute">montando o e-mail…</p>}
                {a4Prev?.corpo && (
                  <div className="mt-2 border border-line bg-panel2 font-mono text-[13.75px]">
                    <div className="border-b border-line px-2 py-1"><span className="text-mute">Para:</span> {a4Prev.para}</div>
                    <div className="border-b border-line px-2 py-1"><span className="text-mute">Cc:</span> {a4Prev.cc}</div>
                    <div className="border-b border-line px-2 py-1 font-bold"><span className="font-normal text-mute">Assunto:</span> {a4Prev.assunto}</div>
                    <pre className="max-h-64 overflow-auto whitespace-pre-wrap px-2 py-1.5 font-mono text-[13.75px]">{a4Prev.corpo}</pre>
                  </div>
                )}
                <div className="mt-2 flex gap-2">
                  <Button onClick={runA4Email} disabled={!a4Prev?.corpo}>Abrir no e-mail</Button>
                  <Button onClick={() => navigator.clipboard?.writeText(a4Prev?.corpo ?? '')} disabled={!a4Prev?.corpo}>Copiar texto</Button>
                </div>
              </>
            ) : etapa === 'entrada' && (
              <p className="mt-1 font-mono text-[12.5px] text-mute">O e-mail fica disponível depois do despacho.</p>
            )}
            {emailA4?.erro && <p className="mt-1 text-xs text-bad">{emailA4.erro}</p>}
            {emailA4?.sucesso && (
              <p className="mt-1 text-xs text-ok">
                Rascunho aberto no app de e-mail. Confira e envie você mesmo.
                {emailA4.ja_aberto_antes > 0 && <span className="text-warn"> Já foi aberto {emailA4.ja_aberto_antes}x antes para este incidente.</span>}
              </p>
            )}
          </div>
        )}

        {etapa === 'saida' && (
          <div className="border-b-2 border-rule px-5 py-3">
            <div className={LABEL}>Encerramento</div>
            <p className="mt-1 text-xs text-mute">
              Resolve no ServiceNow (estado Resolvido, código Solved) com este texto como nota de encerramento e work note.
              Só quando o caso estiver resolvido.
            </p>
            <textarea
              value={closeNote}
              onChange={(e) => setCloseNote(e.target.value)}
              placeholder="Causa base: … / Descrição: …"
              className="mt-2 w-full border border-line bg-panel px-2 py-1.5 font-mono text-xs"
              rows={3}
            />
            <div className="mt-2 flex items-center gap-3">
              <button {...holdClose.handlers} disabled={!closeNote.trim() || !!closing?.busy}
                className="relative overflow-hidden bg-invert px-4 py-2 text-left font-display text-sm font-extrabold uppercase tracking-wide text-invert-ink hover:opacity-90 disabled:opacity-50">
                {closing?.busy ? 'Encerrando…' : 'Encerrar (Resolvido)'}
                <span className="block font-mono text-[11.25px] font-normal normal-case tracking-[0.1em] opacity-75">mantenha pressionado</span>
                <span ref={holdClose.bar} className="absolute bottom-0 left-0 h-1 w-0 bg-bad" />
              </button>
              {closing?.erro && <span className="font-mono text-[12.5px] font-bold text-bad">{closing.erro}</span>}
              {closing?.sucesso && (
                <span className={`font-mono text-[12.5px] font-bold ${closing.simulado ? 'text-warn' : 'text-ok'}`}>{closing.mensagem}</span>
              )}
            </div>
          </div>
        )}

        {etapa === 'saida' && !isScom && !incident.acesso && (
          <div className="border-b-2 border-rule px-5 py-3">
            <RitmPanel key={incident.incident_number} incident={incident} autoOpen={!!incident.ritm_necessaria} />
          </div>
        )}
      </div>

      {/* Ação */}
      <div className="shrink-0 border-t-2 border-rule">
        {msg && (
          <div className={`border-b border-line px-5 py-1.5 font-mono text-[13.75px] font-bold ${msg.ok ? 'text-ok' : 'text-bad'}`} role="status">
            {msg.text}
          </div>
        )}
        <div className="grid grid-cols-[1fr_auto]">
          <button
            {...hold.handlers}
            disabled={busy || !canDispatch || approved}
            aria-label={approved ? statusLabel(incident.status) : 'Despachar: mantenha pressionado'}
            className={`relative h-[72px] overflow-hidden px-5 text-left font-display text-2xl font-extrabold uppercase tracking-wide transition-opacity ${
              busy || !canDispatch || approved
                ? 'cursor-not-allowed bg-[repeating-linear-gradient(135deg,var(--c-line)_0_8px,var(--c-panel)_8px_16px)] text-mute'
                : 'bg-invert text-invert-ink hover:opacity-90'
            }`}
          >
            {incident.status === 'aprovado' ? 'Já despachado' : incident.status === 'tratado_fora' ? 'Tratado fora do agente'
              : incident.status === 'encerrado' ? 'Encerrado' : busy ? 'Enviando…' : !canDispatch ? 'Bloqueado' : editing ? 'Despachar edição' : 'Despachar'}
            {canDispatch && !approved && !busy && (
              <span className="block font-mono text-[12.5px] font-normal normal-case tracking-[0.1em] opacity-75">
                Mantenha pressionado para confirmar
              </span>
            )}
            <span ref={hold.bar} className="absolute bottom-0 left-0 h-1.5 w-0 bg-bad" />
          </button>
          <button
            onClick={() => setEditing((v) => !v)}
            disabled={approved}
            className={`border-l-2 border-rule px-6 font-display text-lg font-bold uppercase hover:bg-panel2 disabled:cursor-not-allowed disabled:opacity-40 ${
              !canDispatch && !editing ? 'bg-warn/25 text-ink' : 'text-ink'
            }`}
          >
            {editing ? 'Cancelar' : 'Editar'}
          </button>
        </div>
      </div>
    </section>
  );
}
