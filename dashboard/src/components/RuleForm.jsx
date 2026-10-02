import { useState } from 'react';
import { Button, inputClass } from './ui';

const EMPTY = {
  pattern: '', localidade: '', grupo: '', grupo_display: '',
  ritm_necessaria: false, categoria: '', pendencia: '',
};

export default function RuleForm({ initial, onSubmit, onCancel }) {
  const [form, setForm] = useState({ ...EMPTY, ...initial });
  const [error, setError] = useState(null);
  const set = (k) => (e) =>
    setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    const payload = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === '' ? null : v]));
    try {
      await onSubmit(payload);
      if (!initial) setForm(EMPTY);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <form onSubmit={submit} className="grid grid-cols-1 gap-2 md:grid-cols-3">
      <input className={`${inputClass} font-mono md:col-span-3`} placeholder="Pattern (regex) — ex.: BM|Barra Mansa"
        value={form.pattern} onChange={set('pattern')} required spellCheck={false} />
      <input className={inputClass} placeholder="Localidade (vazio = só RITM/pendência)"
        value={form.localidade ?? ''} onChange={set('localidade')} />
      <input className={inputClass} placeholder="Grupo display — AMS-TI-CFTV-DBB"
        value={form.grupo_display ?? ''} onChange={set('grupo_display')} />
      <input className={`${inputClass} font-mono`} placeholder="Grupo (sys_id)"
        value={form.grupo ?? ''} onChange={set('grupo')} spellCheck={false} />
      <input className={inputClass} placeholder="Categoria"
        value={form.categoria ?? ''} onChange={set('categoria')} />
      <input className={inputClass} placeholder="Pendência"
        value={form.pendencia ?? ''} onChange={set('pendencia')} />
      <label className="flex items-center gap-2 text-xs text-ink">
        <input type="checkbox" checked={!!form.ritm_necessaria} onChange={set('ritm_necessaria')} className="accent-[var(--c-accent)]" />
        RITM necessária
      </label>
      <div className="flex items-center gap-2 md:col-span-3">
        <Button tone="primary" type="submit">{initial ? 'Salvar' : 'Adicionar regra'}</Button>
        {onCancel && <Button type="button" onClick={onCancel}>Cancelar</Button>}
        {error && <span className="text-xs text-bad">{error}</span>}
      </div>
    </form>
  );
}
