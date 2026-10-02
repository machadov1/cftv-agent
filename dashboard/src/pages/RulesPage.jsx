import { useEffect, useMemo, useState } from 'react';
import { getRules, createRule, updateRule, deleteRule, getSugestoes, aceitarSugestao } from '../api';
import RuleForm from '../components/RuleForm';
import LoadingSpinner from '../components/LoadingSpinner';
import { Badge, Button, Panel, inputClass } from '../components/ui';

export default function RulesPage() {
  const [rules, setRules] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [adding, setAdding] = useState(false);
  const [q, setQ] = useState('');
  const [error, setError] = useState(null);
  const [sug, setSug] = useState([]);
  const [aviso, setAviso] = useState(null);

  const load = () => {
    getRules().then(setRules).catch((e) => setError(e.message));
    getSugestoes().then(setSug).catch(() => setSug([]));
  };
  useEffect(() => { load(); }, []);

  const aceitar = async (x) => {
    setError(null);
    try {
      const r = await aceitarSugestao(x.prefixo, x.localidade);
      setAviso(`Regra #${r.regra.id} criada.${r.reaplicados.length ? ` ${r.reaplicados.length} incidente(s) sem destino reavaliado(s): ${r.reaplicados.join(', ')}` : ''}`);
      await load();
    } catch (e) { setError(e.message); }
  };

  const handleCreate = async (rule) => { await createRule(rule); setAdding(false); await load(); };
  const handleUpdate = async (id, rule) => { await updateRule(id, rule); setEditingId(null); await load(); };
  const handleDelete = async (r) => {
    if (!confirm(`Remover a regra #${r.id} "${r.pattern}"?`)) return;
    try { await deleteRule(r.id); await load(); } catch (e) { setError(e.message); }
  };

  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (rules ?? []).filter((r) => !t || JSON.stringify(r).toLowerCase().includes(t));
  }, [rules, q]);

  return (
    <div className="h-full space-y-3 overflow-auto p-3">
      {(sug.length > 0 || aviso) && (
        <Panel title={`Sugestões aprendidas · ${sug.length}`} bodyClass="p-0">
          {aviso && <div className="border-b border-line px-3 py-2 font-mono text-[13.75px] font-bold text-ok">{aviso}</div>}
          {sug.map((x) => (
            <div key={x.prefixo} className="flex flex-wrap items-center gap-3 border-b border-line px-3 py-2 text-xs last:border-b-0">
              <div className="min-w-0 flex-1">
                <div>
                  Câmeras <span className="font-mono font-bold text-accent">{x.prefixo}-…</span> são de{' '}
                  <span className="font-bold">{x.localidade}</span>
                  <span className="text-mute"> · {x.incidentes} incidente(s), {x.pureza}% consistente</span>
                </div>
                <div className="font-mono text-[12.5px] text-mute">
                  {x.regra.pattern} → {x.grupo_display ?? 'sem grupo'} · ex.: {x.exemplos.join(', ')}
                  {x.resolveria_agora > 0 && <span className="font-bold text-warn"> · resolve {x.resolveria_agora} sem destino agora</span>}
                </div>
              </div>
              <Button tone="primary" disabled={!x.pode_criar} onClick={() => aceitar(x)}>Criar regra</Button>
            </div>
          ))}
        </Panel>
      )}
      <Panel
        title={`Regras determinísticas · ${rules?.length ?? 0}`}
        right={
          <div className="flex items-center gap-2">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="filtrar…" className={`${inputClass} w-44`} />
            <Button tone="primary" onClick={() => setAdding((v) => !v)}>{adding ? 'Fechar' : 'Nova regra'}</Button>
          </div>
        }
      >
        {adding && (
          <div className="border-b border-line bg-panel2 p-3">
            <RuleForm onSubmit={handleCreate} onCancel={() => setAdding(false)} />
          </div>
        )}
        {error && <div className="px-3 py-2 text-xs text-bad">{error}</div>}
        {!rules && !error && <LoadingSpinner />}
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-line text-left text-[12.5px] uppercase tracking-[0.1em] text-mute">
              <th className="w-10 py-2 pl-3">#</th>
              <th className="pr-3">Pattern</th>
              <th className="pr-3">Localidade</th>
              <th className="pr-3">Grupo</th>
              <th className="pr-3">RITM</th>
              <th className="pr-3">Categoria / Pendência</th>
              <th className="w-28 pr-3 text-right">Ações</th>
            </tr>
          </thead>
          <tbody className="zebra">
            {shown.map((r) =>
              editingId === r.id ? (
                <tr key={r.id} className="border-b border-line/60 bg-panel2">
                  <td colSpan={7} className="p-3">
                    <RuleForm initial={r} onSubmit={(rule) => handleUpdate(r.id, rule)} onCancel={() => setEditingId(null)} />
                  </td>
                </tr>
              ) : (
                <tr key={r.id} className="border-b border-line/60 align-top hover:bg-panel2">
                  <td className="py-2 pl-3 font-mono text-mute">{r.id}</td>
                  <td className="max-w-[340px] break-all pr-3 font-mono text-accent">{r.pattern}</td>
                  <td className="pr-3">{r.localidade ?? <span className="text-mute">— (só atributos)</span>}</td>
                  <td className="pr-3">
                    {r.grupo ? <span className="font-mono text-ok">{r.grupo_display}</span>
                      : r.localidade ? <Badge tone="warn">sem grupo</Badge> : <span className="text-mute">—</span>}
                  </td>
                  <td className="pr-3">{r.ritm_necessaria ? <span className="text-warn">SIM</span> : <span className="text-mute">não</span>}</td>
                  <td className="pr-3 text-mute">{[r.categoria, r.pendencia].filter(Boolean).join(' · ') || '—'}</td>
                  <td className="pr-3 text-right">
                    <button className="mr-3 text-accent hover:underline" onClick={() => setEditingId(r.id)}>editar</button>
                    <button className="text-bad hover:underline" onClick={() => handleDelete(r)}>remover</button>
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>
      </Panel>
      <p className="px-1 text-[13.75px] text-mute">
        A primeira regra com localidade que casar define o destino. Regras sem localidade só somam RITM, categoria e pendência.
      </p>
    </div>
  );
}
