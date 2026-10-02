import { useEffect, useState } from 'react';
import { cameraAttach, cameraCheck, cameraClose, cameraClosingDraft, cameraClosingNote, getDestinos, snapshotUrl } from '../api';
import HoldButton from './HoldButton';
import Redator, { pendentes } from './Redator';
import { Button } from './ui';

const LABEL = 'font-mono text-[12.5px] font-bold uppercase tracking-[0.14em] text-mute';

const dur = (s) => (s == null ? null : s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)} min` : `${Math.floor(s / 3600)} h`);

// Teste de câmera de um incidente (da fila local ou já em andamento): testar -> anexar print -> work note de encerramento.
// Nunca muda o estado nem encerra o incidente.
export default function CameraPanel({ number, hint, bare = false }) {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [att, setAtt] = useState(null);
  const [err, setErr] = useState(null);
  const [stamp, setStamp] = useState(0);
  const [destinos, setDestinos] = useState([]);
  const [loc, setLoc] = useState('');
  const [precisaLoc, setPrecisaLoc] = useState(false);
  const [nota, setNota] = useState(null); // { texto, faltando }
  const [notaRes, setNotaRes] = useState(null);
  const [fim, setFim] = useState(null); // resultado do encerramento
  const [debug, setDebug] = useState([]);
  const [validacao, setValidacao] = useState('');

  useEffect(() => {
    setRes(null); setAtt(null); setErr(null); setNota(null); setNotaRes(null); setFim(null); setPrecisaLoc(false); setLoc('');
    setValidacao('');
  }, [number]);

  const check = async (escolha = null) => {
    setBusy(true); setErr(null); setAtt(null); setNota(null); setNotaRes(null); setDebug([]);
    try {
      const r = await cameraCheck(number, loc, escolha);
      setRes(r); setStamp(Date.now()); setPrecisaLoc(false); setDebug(r.debug || []);
    } catch (e) {
      setErr(e.message); setRes(null);
      if (/escolha a localidade/i.test(e.message)) {
        setPrecisaLoc(true);
        if (destinos.length === 0) getDestinos().then(setDestinos).catch(() => {});
      }
    }
    setBusy(false);
  };

  const attach = async () => {
    setBusy(true); setErr(null);
    try {
      const a = await cameraAttach(number);
      setAtt(a);
      if (a.resultado.some((r) => r.status !== 'falhou')) setNota(await cameraClosingDraft(number));
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  const registrar = async () => {
    setBusy(true); setErr(null);
    try { setNotaRes(await cameraClosingNote(number, nota.texto, validacao)); } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  const encerrar = async () => {
    setBusy(true); setErr(null);
    try { setFim(await cameraClose(number, nota.texto, validacao)); } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  const withShot = res?.cameras.filter((c) => c.snapshot) ?? [];

  return (
    <div className={bare ? '' : 'border-b-2 border-rule px-5 py-3'}>
      <div className="flex flex-wrap items-center gap-2">
        <div className={`${LABEL} mr-auto`}>
          Teste de câmera · Digifort
          {hint && <span className="ml-2 text-ink">{hint}</span>}
        </div>
        <Button onClick={() => check()} disabled={busy || !number || (precisaLoc && !loc)}>
          {busy && !res ? 'Consultando…' : precisaLoc ? 'Testar nesta unidade' : 'Testar câmera'}
        </Button>
      </div>

      {precisaLoc && (
        <select value={loc} onChange={(e) => setLoc(e.target.value)} aria-label="Unidade da câmera"
          className="mt-2 w-full border-2 border-rule bg-panel px-2 py-1.5 text-sm">
          <option value="">— em qual unidade procurar? —</option>
          {destinos.map((d) => <option key={d.localidade} value={d.localidade}>{d.localidade}</option>)}
        </select>
      )}
      {err && <p className="mt-2 text-xs font-semibold text-bad">{err}</p>}

      {debug.length > 0 && (
        <details className="mt-2 border border-line bg-panel2 p-2 text-[13.75px] font-mono">
          <summary className="cursor-pointer font-bold text-mute">📋 Debug ({debug.length})</summary>
          <div className="mt-1 max-h-48 overflow-auto space-y-0.5 text-[12.5px] leading-tight">
            {debug.map((line, i) => (
              <div key={i} className={line.includes('✗') ? 'text-bad' : line.includes('✓') ? 'text-ok' : 'text-mute'}>
                {line}
              </div>
            ))}
          </div>
        </details>
      )}

      {res?.incidente && (
        <div className="mt-2 font-mono text-[13.75px] text-mute">
          {res.incidente.incident_number} · {res.incidente.localidade ?? 'unidade não identificada'}
          {res.incidente.grupo && ` · ${res.incidente.grupo}`}
        </div>
      )}

      {res?.cameras.map((c) => (
        <div key={c.codigo} className="mt-2 border border-line p-2 text-xs">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-mono font-bold">{c.codigo}</span>
            {c.achada && <span className="font-mono text-[13.75px] text-mute">{c.achada.servidor} · {c.achada.nome}</span>}
          </div>
          {c.working === true && <div className="font-bold text-ok">Voltou: transmitindo{c.active_s != null ? ` há ${dur(c.active_s)}` : ''}</div>}
          {c.active === false && <div className="font-bold text-warn">Desativada no cadastro do Digifort</div>}
          {c.active !== false && c.working === false && <div className="font-bold text-bad">Sem sinal{c.inactive_s ? ` há ${dur(c.inactive_s)}` : ''}</div>}
          {c.erro && <div className={c.snapshot ? 'text-warn' : 'text-bad'}>{c.erro}</div>}
          {!c.achada && c.candidatas?.length > 0 && (
            <div className="mt-1.5">
              <div className={LABEL}>{c.texto_livre ? 'Câmeras que combinam com a descrição' : 'Nomes parecidos no Digifort'} · escolha a certa</div>
              <ul className="mt-1 border border-line">
                {c.candidatas.map((x) => (
                  <li key={`${x.ip}-${x.nome}`} className="flex items-center gap-2 border-b border-line px-2 py-1 last:border-b-0">
                    <span className={`h-2.5 w-2.5 shrink-0 ${x.active === false ? 'bg-mute' : x.working === false ? 'bg-bad' : x.working ? 'bg-ok' : 'border-2 border-mute'}`}
                      title={x.active === false ? 'desativada' : x.working === false ? 'sem sinal' : x.working ? 'transmitindo' : 'sem estado'} />
                    <span className="min-w-0 flex-1">
                      <span className="font-mono font-bold">{x.nome}</span>
                      {x.descricao && <span className="text-mute"> · {x.descricao}</span>}
                      <span className="block font-mono text-[12.5px] text-mute">{x.servidor}</span>
                    </span>
                    <span className={`font-mono text-[12.5px] font-bold ${x.pontos >= 90 ? 'text-ok' : x.pontos >= 70 ? 'text-warn' : 'text-mute'}`}
                      title="Semelhança com o que o incidente cita">{x.pontos}%</span>
                    <Button onClick={() => check({ consulta: c.codigo, ip: x.ip, nome: x.nome })} disabled={busy}>Testar esta</Button>
                  </li>
                ))}
              </ul>
              <p className="mt-1 font-mono text-[12.5px] text-mute">A escolha fica lembrada: da próxima vez este código vai direto nela.</p>
            </div>
          )}
          {c.erros_servidores?.length > 0 && !c.achada && (
            <details className="mt-1 font-mono text-[12.5px] text-mute">
              <summary className="cursor-pointer">{c.erros_servidores.length} de {c.tentados.length} servidor(es) com falha</summary>
              {c.erros_servidores.map((e) => <div key={e}>{e}</div>)}
            </details>
          )}
          {c.snapshot && (
            <img src={snapshotUrl(number, c.codigo, stamp)} alt={`Snapshot ${c.codigo}`} className="mt-2 max-h-72 border border-line" />
          )}
        </div>
      ))}

      {withShot.length > 0 && !att && (
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <HoldButton onDone={attach} disabled={busy}>
            Anexar {withShot.length > 1 ? `${withShot.length} prints` : 'print'} ao incidente
          </HoldButton>
          {res.dry_run && <span className="font-mono text-[13.75px] text-warn">dry-run: não grava no ServiceNow</span>}
        </div>
      )}
      {att?.resultado.map((r) => (
        <div key={r.arquivo} className={`mt-1 font-mono text-[13.75px] font-bold ${r.status === 'falhou' ? 'text-bad' : 'text-ok'}`}>
          {r.arquivo}: {r.status}{att.dry_run && r.status === 'anexado' ? ' (simulado)' : ''}
        </div>
      ))}

      {nota && (
        <div className="mt-3 border-t border-line pt-2">
          <div className={LABEL}>Texto de encerramento (editável)</div>
          {nota.faltando?.length > 0 && (
            <p className="mt-1 text-[13.75px] text-warn">
              Sem print: {nota.faltando.join(', ')}. O texto lista cada câmera e pede a RITM da pendência.
            </p>
          )}
          {!notaRes && fim?.status !== 'encerrado' && (
            <div className="mt-2">
              <Redator incidentNumber={number} texto={nota.texto} onTexto={(t) => setNota({ ...nota, texto: t })}
                validacao={validacao} onValidacao={setValidacao} />
            </div>
          )}
          <textarea
            value={nota.texto}
            onChange={(e) => setNota({ ...nota, texto: e.target.value })}
            rows={7}
            disabled={!!notaRes || fim?.status === 'encerrado'}
            className="mt-2 w-full border-2 border-rule bg-panel px-2 py-1.5 font-mono text-[13.75px] leading-snug"
          />
          {!fim ? (
            <div className="mt-1 flex flex-wrap items-start gap-3">
              {!notaRes && (
                <HoldButton onDone={registrar} disabled={busy || nota.texto.trim().length < 20 || pendentes(nota.texto).length > 0}
                  hint="só a nota · segue aberto">
                  Registrar work note
                </HoldButton>
              )}
              <HoldButton onDone={encerrar} disabled={busy || nota.texto.trim().length < 20 || pendentes(nota.texto).length > 0}
                hint="resolvido · mantenha pressionado" className="border-l-8 border-bad">
                Encerrar incidente
              </HoldButton>
            </div>
          ) : (
            <div className={`mt-1 font-mono text-[13.75px] font-bold ${fim.status === 'encerrado' && !fim.dry_run ? 'text-ok' : 'text-warn'}`}>
              {fim.status === 'já encerrado' ? 'Já estava encerrado no ServiceNow: nada foi enviado.'
                : fim.dry_run ? 'Encerramento simulado (dry-run): nada foi enviado.' : 'Incidente encerrado no ServiceNow (Resolvido · Solved).'}
            </div>
          )}
          {notaRes && !fim && (
            <div className="mt-1 font-mono text-[13.75px] font-bold text-ok">
              Work note {notaRes.status}{notaRes.dry_run && notaRes.status === 'registrada' ? ' (simulada: dry-run)' : ''}. Encerre quando quiser.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
