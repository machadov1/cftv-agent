import { useEffect, useMemo, useState } from 'react';
import { getBacklog } from '../api';
import CameraPanel from '../components/CameraPanel';
import RitmPanel from '../components/RitmPanel';
import LoadingSpinner from '../components/LoadingSpinner';
import { Button, inputClass } from '../components/ui';

const EM_ANDAMENTO = /andamento/i;
const DE_CAMERA = /c[âa]mera/i;

export default function CameraPage({ target }) {
  const [number, setNumber] = useState('');
  const [active, setActive] = useState(target || '');
  useEffect(() => { if (target) setActive(target); }, [target]);
  const [rows, setRows] = useState(null);
  const [erro, setErro] = useState(null);
  const [q, setQ] = useState('');

  const load = (force = false) => {
    setErro(null);
    getBacklog(force).then((d) => setRows(d.incidentes ?? d.rows ?? d.items ?? [])).catch((e) => { setErro(e.message); setRows([]); });
  };
  useEffect(() => { load(); }, []);

  const lista = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (rows ?? [])
      .filter((r) => EM_ANDAMENTO.test(r.status || '') && DE_CAMERA.test(`${r.titulo} ${r.descricao}`))
      .filter((r) => !t || `${r.number} ${r.titulo} ${r.grupo}`.toLowerCase().includes(t));
  }, [rows, q]);

  const go = (n) => { const v = (n ?? number).trim().toUpperCase(); if (v) { setActive(v); setNumber(''); } };

  return (
    <div className="grid h-full min-h-0 grid-cols-1 xl:grid-cols-[minmax(380px,1fr)_minmax(520px,1.15fr)]">
      <div className="flex min-h-0 flex-col border-rule xl:border-r-2">
        <div className="shrink-0 space-y-2.5 border-b-2 border-rule p-3">
          <div className="flex gap-2">
            <input
              value={number}
              onChange={(e) => setNumber(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === 'Enter' && go()}
              placeholder="INC4006173"
              spellCheck={false}
              aria-label="Número do incidente"
              className={`${inputClass} font-mono text-sm tracking-wide`}
            />
            <Button tone="primary" onClick={() => go()} disabled={!number.trim()} className="shrink-0 px-5">Abrir</Button>
          </div>
          <div className="flex items-center gap-2">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="filtrar a lista…" className={`${inputClass} flex-1`} />
            <Button onClick={() => load(true)}>Atualizar</Button>
          </div>
          {erro && <div className="text-xs font-semibold text-bad">{erro}</div>}
        </div>
        <div className="border-b border-line bg-panel2 px-3 py-1.5 font-mono text-[12.5px] font-bold uppercase tracking-[0.14em] text-mute">
          Câmeras em andamento · {lista.length}
        </div>
        <div className="zebra min-h-0 flex-1 overflow-auto">
          {!rows ? <LoadingSpinner /> : lista.length === 0 ? (
            <div className="p-8 text-center text-mute">Nenhum incidente de câmera em andamento no painel.</div>
          ) : lista.map((r) => (
            <button
              key={r.number}
              onClick={() => setActive(r.number)}
              aria-pressed={active === r.number}
              className={`block w-full border-b border-line px-3.5 py-2.5 text-left ${active === r.number ? 'bg-invert text-invert-ink' : 'hover:!bg-bg'}`}
            >
              <div className="flex justify-between gap-2 font-mono text-xs font-bold">
                <span className={active === r.number ? '' : 'text-bad'}>{r.number}</span>
                <span className="font-normal opacity-70">{r.prazo_txt}</span>
              </div>
              <div className="truncate font-display text-lg font-bold leading-tight">{r.titulo}</div>
              <div className="truncate font-mono text-[12.5px] uppercase opacity-70">{r.grupo}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 overflow-auto border-t-2 border-rule p-5 xl:border-t-0">
        {active ? (
          <>
            <div className="mb-2 font-display text-3xl font-extrabold uppercase tracking-tight">{active}</div>
            <CameraPanel key={active} number={active} bare />
            {/* câmera segue fora e depende de outra equipe: RITM de acompanhamento */}
            <div className="mt-5 border-t-2 border-rule pt-4">
              <div className="mb-2 font-mono text-[12.5px] font-bold uppercase tracking-[0.14em] text-mute">
                Câmera segue fora? RITM de acompanhamento
              </div>
              <RitmPanel key={`ritm-${active}`} incident={{ incident_number: active }} />
            </div>
          </>
        ) : (
          <div className="flex h-full items-center justify-center p-8 text-center">
            <div>
              <div className="font-display text-3xl font-extrabold uppercase tracking-tight">Teste de câmera</div>
              <p className="mt-2 max-w-md text-mute">
                Escolha um incidente em andamento (ou digite o número). O agente acha a câmera no Digifort, confere se voltou,
                tira o print, anexa e prepara a work note de encerramento. O incidente continua aberto.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
