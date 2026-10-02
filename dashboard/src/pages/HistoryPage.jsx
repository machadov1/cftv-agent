import { useEffect, useState } from 'react';
import { getHistory } from '../api';
import LoadingSpinner from '../components/LoadingSpinner';
import { Badge, Panel, inputClass, parseUtc } from '../components/ui';

const ACOES = ['', 'analise', 'aprovado', 'editado', 'ritm', 'ping', 'scom_ping'];
const ACAO_TONE = { analise: 'accent', aprovado: 'ok', editado: 'warn', ritm: 'accent', ping: 'mute', scom_ping: 'mute' };

export default function HistoryPage() {
  const [rows, setRows] = useState(null);
  const [acao, setAcao] = useState('');
  const [inc, setInc] = useState('');
  const [error, setError] = useState(null);

  useEffect(() => {
    setError(null);
    const load = () =>
      getHistory({ acao, incident_number: inc.trim(), limit: 200 }).then(setRows).catch((e) => setError(e.message));
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [acao, inc]);

  return (
    <div className="h-full overflow-auto p-3">
      <Panel
        title={`Registro de ações · ${rows?.length ?? 0}`}
        right={
          <div className="flex items-center gap-2">
            <input value={inc} onChange={(e) => setInc(e.target.value.toUpperCase())}
              placeholder="INC…" className={`${inputClass} w-36 font-mono`} />
            <select value={acao} onChange={(e) => setAcao(e.target.value)} className={`${inputClass} w-36`}>
              {ACOES.map((a) => <option key={a} value={a}>{a || 'todas as ações'}</option>)}
            </select>
          </div>
        }
      >
        {error && <div className="px-3 py-2 text-xs text-bad">{error}</div>}
        {!rows && !error && <LoadingSpinner />}
        {rows && (
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="border-b border-line text-left text-[12.5px] uppercase tracking-[0.1em] text-mute">
                <th className="py-2 pl-3">Horário</th><th className="pr-3">Incidente</th><th className="pr-3">Ação</th>
                <th className="pr-3">Origem</th><th className="pr-3 text-right">Tempo</th><th className="pr-3">Detalhe</th>
              </tr>
            </thead>
            <tbody className="zebra">
              {rows.map((h) => (
                <tr key={h.id} className="border-b border-line/60 hover:bg-panel2">
                  <td className="whitespace-nowrap py-2 pl-3 font-mono tabular-nums text-mute">
                    {parseUtc(h.created_at)?.toLocaleString('pt-BR')}
                  </td>
                  <td className="pr-3 font-mono text-accent">{h.incident_number}</td>
                  <td className="pr-3"><Badge tone={ACAO_TONE[h.acao] ?? 'mute'}>{h.acao}</Badge></td>
                  <td className="pr-3 text-mute">{h.chamou_claude ? 'LLM' : 'regras'}</td>
                  <td className="whitespace-nowrap pr-3 text-right font-mono tabular-nums text-mute">{Math.round(h.tempo_ms)} ms</td>
                  <td className="max-w-[420px] truncate pr-3 font-mono text-[13.75px] text-mute" title={h.resultado}>{h.resultado}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={6} className="p-6 text-center text-mute">Sem registros.</td></tr>
              )}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
