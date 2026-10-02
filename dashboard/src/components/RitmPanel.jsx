import { useEffect, useState } from 'react';
import { getRitmDraft, createRitm, teamsDraft, controleRow } from '../api';
import HoldButton from './HoldButton';
import { Button, inputClass } from './ui';

const LABEL = 'text-[12.5px] font-semibold uppercase tracking-[0.12em] text-mute';

// Mesmo modelo de backend/textos.ritm_descricao (manual: pendências externas); os textos por pendência vêm do rascunho.
const SLA = 'Considerando a proximidade do encerramento do SLA do incidente, o acompanhamento seguirá vinculado à requisição.';
const ponto = (t) => { const s = (t || '').trim(); return /[.!?)]$/.test(s) ? s : `${s}.`; };
const modelo = (d, pend) => d.modelos?.[pend] ?? { recurso: 'atuação de outra equipe para tratativa da falha',
  aguardando: 'Aguardando atuação da equipe responsável.' };
const render = (d, pend, encam) =>
  `Causa raiz: ${ponto(d.causa)}\n\nAnálise: Reparo depende de ${modelo(d, pend).recurso}.${d.sla_proximo ? ` ${SLA}` : ''}\n\n` +
  `Encaminhamento: ${ponto(encam || modelo(d, pend).aguardando)} Acompanhamento seguirá vinculado à requisição.\n\n` +
  'Encerramento: Incidente encerrado com pendência vinculada à requisição.';

function NextSteps({ incident, done }) {
  const [teams, setTeams] = useState(null);
  const [ctl, setCtl] = useState(null);
  const [busy, setBusy] = useState(null);

  const run = async (kind, fn, set) => {
    setBusy(kind);
    try { set(await fn()); } catch (e) { set({ erro: e.message }); }
    setBusy(null);
  };
  const n = incident.incident_number;
  const draft = (abrir) => run('teams', () => teamsDraft(n, { ritm: done.ritm, pendencia: done.pendencia, abrir }), setTeams);

  return (
    <div className="space-y-3 border-2 border-rule bg-bg p-3">
      <div className="text-xs text-ok">
        {done.simulado ? 'RITM simulada' : 'RITM criada'}: <span className="font-mono">{done.ritm}</span>
        {done.req && <span className="font-mono text-mute"> · {done.req}</span>} · work note registrada
      </div>

      <div>
        <div className={LABEL}>Teams (rascunho, nunca enviado)</div>
        <div className="mt-1 flex gap-2">
          <Button onClick={() => draft(false)} disabled={busy === 'teams'}>Ver mensagem</Button>
          <Button onClick={() => draft(true)} disabled={busy === 'teams'}>Abrir no Teams</Button>
        </div>
        {teams?.erro && <p className="mt-1 text-xs text-bad">{teams.erro}</p>}
        {teams?.mensagem && (
          <>
            <p className="mt-1 text-[13.75px] text-mute">Para {teams.solicitante} · {teams.email}</p>
            <pre className="mt-1 whitespace-pre-wrap border border-line px-2 py-1.5 font-mono text-[13.75px] text-mute">{teams.mensagem}</pre>
            <p className="text-[13.75px] text-warn">{teams.aberto ? 'Chat aberto com a mensagem pré-preenchida. ' : ''}{teams.aviso}</p>
          </>
        )}
      </div>

      <div>
        <div className={LABEL}>Planilha de controle</div>
        <div className="mt-1">
          <Button onClick={() => run('ctl', () => controleRow(n, { ritm: done.ritm, req: done.req, subarea: done.subarea, pendencia: done.pendencia }), setCtl)}
            disabled={busy === 'ctl' || ctl?.linha}>
            {busy === 'ctl' ? 'Lançando…' : 'Lançar na planilha'}
          </Button>
        </div>
        {ctl?.erro && <p className="mt-1 text-xs text-bad">{ctl.erro}</p>}
        {ctl?.linha && (
          <div className="mt-1 text-[13.75px] text-mute">
            <div className={ctl.gravado ? 'text-ok' : 'text-warn'}>
              {ctl.gravado ? `Gravado na linha ${ctl.linha}.` : `Simulado (dry-run): iria para a linha ${ctl.linha}, nada foi gravado.`}
            </div>
            <div className="mt-1 font-mono">
              {['A', 'B', 'C', 'D', 'G', 'H', 'I', 'J', 'L'].map((k) => `${k}: ${ctl.valores[k]}`).join(' | ')}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function RitmPanel({ incident, autoOpen = false }) {
  const [done, setDone] = useState(null);
  const [d, setD] = useState(null);
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [force, setForce] = useState(false);

  const open = async () => {
    setBusy(true); setMsg(null);
    try {
      const draft = await getRitmDraft(incident.incident_number);
      setD(draft);
      setF({ localidade_form: draft.localidade_form, subarea: draft.subarea, pendencia: draft.pendencia,
        encaminhamento: draft.encaminhamento, descricao: draft.descricao });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  // RITM sugerida pela regra (ou pedida pela aba Câmeras): já abre o rascunho
  useEffect(() => { if (autoOpen) open(); }, [autoOpen, incident.incident_number]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const setPend = (e) => {
    const pendencia = e.target.value;
    setF((x) => {
      // encaminhamento ainda no padrão da pendência anterior acompanha a troca; editado à mão fica
      const encaminhamento = x.encaminhamento === modelo(d, x.pendencia).aguardando ? modelo(d, pendencia).aguardando : x.encaminhamento;
      return { ...x, pendencia, encaminhamento, descricao: render(d, pendencia, encaminhamento) };
    });
  };
  const setEncam = (e) => {
    const encaminhamento = e.target.value;
    setF((x) => ({ ...x, encaminhamento, descricao: render(d, x.pendencia, encaminhamento) }));
  };

  const submit = async () => {
    setBusy(true); setMsg(null);
    try {
      const { encaminhamento, ...body } = f;
      const r = await createRitm(incident.incident_number, { ...body, force });
      setDone({ ritm: r.ritm, req: r.req, simulado: r.simulado, pendencia: f.pendencia, subarea: f.subarea });
      setD(null); setF(null);
    } catch (e) { setMsg({ ok: false, text: e.message, dup: /duplicidade/i.test(e.message) }); }
    setBusy(false);
  };

  if (done) return <NextSteps incident={incident} done={done} />;

  if (!f) {
    return (
      <div className="flex items-center gap-2">
        <Button onClick={open} disabled={busy}>{busy ? 'Carregando…' : 'Preparar RITM'}</Button>
        {msg && <span className={`text-xs ${msg.ok ? 'text-ok' : 'text-bad'}`}>{msg.text}</span>}
      </div>
    );
  }

  const missing = !f.localidade_form || !f.subarea || !f.pendencia;
  return (
    <div className="space-y-2 border-2 border-rule bg-bg p-3">
      <div className="flex items-center justify-between">
        <div className={LABEL}>RITM de acompanhamento {d.dry_run && <span className="text-warn">· dry-run</span>}</div>
        <button className="text-[13.75px] text-mute hover:text-ink" onClick={() => { setF(null); setD(null); }}>fechar</button>
      </div>

      {d.ja_criada.length > 0 && <p className="text-xs text-warn">Já existe RITM para este incidente: {d.ja_criada.join(', ')}</p>}
      {d.duplicidade.map((w) => <p key={w} className="text-xs text-warn">⚠ {w}</p>)}
      {d.warnings.map((w) => <p key={w} className="text-[13.75px] text-mute">• {w}</p>)}

      <div className="grid grid-cols-2 gap-2">
        <label className="col-span-2"><div className={LABEL}>Localidade (formulário)</div>
          <select className={inputClass} value={f.localidade_form} onChange={set('localidade_form')}>
            <option value="">— escolha —</option>
            {(d.locais ?? []).map((l) => <option key={l}>{l}</option>)}
          </select></label>
        <label><div className={LABEL}>Subárea</div>
          <input className={inputClass} value={f.subarea} onChange={set('subarea')} /></label>
        <label><div className={LABEL}>Pendência</div>
          <select className={inputClass} value={f.pendencia} onChange={setPend}>
            <option value="">—</option>
            {d.pendencias.map((p) => <option key={p}>{p}</option>)}
          </select></label>
        <label className="col-span-2"><div className={LABEL}>Encaminhamento (só fatos registrados)</div>
          <input className={inputClass} value={f.encaminhamento} onChange={setEncam} /></label>
        <label className="col-span-2"><div className={LABEL}>Descrição</div>
          <textarea className={`${inputClass} h-40 font-mono text-[13.75px]`} value={f.descricao} onChange={set('descricao')} /></label>
      </div>

      <p className="text-[13.75px] text-mute">
        Confira câmeras e o que foi reestabelecido antes de criar: depois de enviada, a descrição da RITM não pode ser editada.
      </p>
      {msg && !msg.ok && msg.dup && (
        <label className="flex items-center gap-2 text-xs text-warn">
          <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} className="accent-[var(--c-accent)]" />
          Sei da sobreposição, criar mesmo assim
        </label>
      )}
      <div className="flex items-center gap-2">
        <HoldButton onDone={submit} disabled={busy || missing || d.ja_criada.length > 0} hint="segure para enviar">
          {busy ? 'Enviando…' : d.dry_run ? 'Criar RITM (simulado)' : 'Criar RITM'}
        </HoldButton>
        {msg && <span className={`text-xs ${msg.ok ? 'text-ok' : 'text-bad'}`}>{msg.text}</span>}
      </div>
    </div>
  );
}
