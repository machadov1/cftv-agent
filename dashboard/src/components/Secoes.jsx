import { useEffect, useState } from 'react';

// Sub-abas de uma página: [{id, label, Page}]. target (vindo de go(tab, alvo)) abre direto numa delas.
export default function Secoes({ secoes, target, label, ...props }) {
  const valido = (id) => secoes.some((s) => s.id === id);
  const [atual, setAtual] = useState(valido(target) ? target : secoes[0].id);
  useEffect(() => { if (valido(target)) setAtual(target); }, [target]); // eslint-disable-line react-hooks/exhaustive-deps
  const { Page } = secoes.find((s) => s.id === atual);
  return (
    <div className="flex h-full flex-col">
      <nav className="flex shrink-0 items-stretch border-b-2 border-rule bg-panel2" aria-label={label}>
        {secoes.map((s) => (
          <button key={s.id} onClick={() => setAtual(s.id)} aria-current={atual === s.id ? 'page' : undefined}
            className={`border-r-2 border-rule px-4 py-2 font-display text-sm font-bold uppercase tracking-wide ${
              atual === s.id ? 'bg-invert text-invert-ink' : 'text-ink hover:bg-panel'}`}>
            {s.label}
          </button>
        ))}
      </nav>
      <div className="min-h-0 flex-1"><Page {...props} /></div>
    </div>
  );
}
