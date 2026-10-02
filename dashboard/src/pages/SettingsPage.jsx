import { useEffect, useState } from 'react';
import { getHealth, getLlmConfig, saveLlmConfig, testLlm, getLlmModels, getServidoresStatus } from '../api';
import LoadingSpinner from '../components/LoadingSpinner';
import { Badge, Button, inputClass } from '../components/ui';

const LABEL = 'font-mono text-[12.5px] font-bold uppercase tracking-[0.14em] text-mute';

function Check({ name, r }) {
  if (!r) return <div className="border border-line px-3 py-2"><div className={LABEL}>{name}</div><div className="text-mute">—</div></div>;
  const ok = r.ok && r.passou !== false;
  return (
    <div className={`border-2 px-3 py-2 ${ok ? 'border-ok' : 'border-bad'}`}>
      <div className="flex items-center justify-between">
        <span className={LABEL}>{name}</span>
        <span className="font-mono text-[13.75px] font-bold">{(r.ms / 1000).toFixed(1)}s</span>
      </div>
      <div className={`font-display text-lg font-extrabold uppercase ${ok ? 'text-ok' : 'text-bad'}`}>{ok ? 'passou' : r.ok ? 'respondeu errado' : 'falhou'}</div>
      <div className="truncate font-mono text-[12.5px] text-mute" title={r.erro || r.resposta || r.chamada}>
        {r.erro || `${r.modelo ?? ''} · ${r.resposta ?? r.chamada ?? ''}`}
      </div>
    </div>
  );
}

function Section({ title, children, aside }) {
  return (
    <section className="border-2 border-rule bg-panel">
      <header className="flex flex-wrap items-center gap-3 border-b-2 border-rule px-4 py-2.5">
        <div className="mr-auto font-display text-xl font-extrabold uppercase leading-none">{title}</div>
        {aside}
      </header>
      {children}
    </section>
  );
}

function Router({ p, onChange }) {
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState(false);
  const [models, setModels] = useState(null);
  const [mErr, setMErr] = useState(null);

  const run = async () => {
    setBusy(true);
    try { setTest(await testLlm(p.id)); } catch (e) { setTest({ erro: e.message }); }
    setBusy(false);
  };
  const loadModels = async () => {
    setMErr(null);
    try { setModels(await getLlmModels(p.id)); } catch (e) { setMErr(e.message); }
  };
  const set = (k) => (e) => onChange({ ...p, [k]: e.target.value });

  return (
    <Section
      title="IA · 9router"
      aside={(
        <>
          <span className="font-mono text-[13.75px] text-mute">{p.base_url}</span>
          <Badge tone={p.key_present ? 'ok' : 'bad'}>chave {p.key_present ? `ok ${p.key_hint}` : `ausente (${p.api_key_env})`}</Badge>
          {p.status && (
            <Badge tone={p.status.ok ? 'ok' : 'bad'} title={p.status.erro}>
              {p.status.ok ? `última chamada ok · ${(p.status.ms / 1000).toFixed(1)}s` : 'última chamada falhou'}
            </Badge>
          )}
        </>
      )}
    >
      <p className="px-4 pt-3 text-xs text-mute">
        Toda IA do agente passa pelo 9router. Quais modelos existem e como caem entre si é gerido lá; aqui só o caminho até ele.
        A chave fica no arquivo <span className="font-mono">.env</span> e nunca aparece na tela.
      </p>
      <div className="grid gap-3 p-4 md:grid-cols-2">
        <label>
          <span className={LABEL}>Modelo (texto e ferramentas)</span>
          <input list="m-router" className={`${inputClass} mt-1 font-mono`} value={p.model ?? ''} onChange={set('model')} spellCheck={false} />
        </label>
        <label>
          <span className={LABEL}>Modelo para prints (visão)</span>
          <input list="mv-router" className={`${inputClass} mt-1 font-mono`} value={p.vision_model ?? ''} onChange={set('vision_model')} spellCheck={false} />
        </label>
        <label>
          <span className={LABEL}>Endereço (base URL)</span>
          <input className={`${inputClass} mt-1 font-mono`} value={p.base_url ?? ''} onChange={set('base_url')} spellCheck={false} />
        </label>
        <label>
          <span className={LABEL}>Tempo limite (s)</span>
          <input type="number" min={5} max={300} className={`${inputClass} mt-1 font-mono`} value={p.timeout ?? 60}
            onChange={(e) => onChange({ ...p, timeout: Number(e.target.value) })} />
        </label>
        <datalist id="m-router">{models?.map((m) => <option key={m.id} value={m.id}>{m.tools ? 'ferramentas' : ''}</option>)}</datalist>
        <datalist id="mv-router">{models?.filter((m) => m.vision).map((m) => <option key={m.id} value={m.id} />)}</datalist>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t-2 border-rule px-4 py-2.5">
        <Button tone="primary" onClick={run} disabled={busy}>{busy ? 'Testando (até 1 min)…' : 'Testar agora'}</Button>
        <Button onClick={loadModels}>{models ? `${models.length} modelos carregados` : 'Carregar modelos'}</Button>
        {mErr && <span className="text-xs font-bold text-bad">{mErr}</span>}
        <span className="font-mono text-[12.5px] text-mute">O teste usa a configuração salva.</span>
      </div>

      {test && (
        <div className="grid gap-2 border-t-2 border-rule p-4 md:grid-cols-3">
          {test.erro ? <div className="text-xs font-bold text-bad md:col-span-3">{test.erro}</div> : (
            <>
              <Check name="Texto" r={test.texto} />
              <Check name="Ferramentas (agente)" r={test.ferramentas} />
              <Check name="Visão (prints)" r={test.visao} />
            </>
          )}
        </div>
      )}
      {models && (
        <details className="border-t border-line px-4 py-2 text-xs">
          <summary className="cursor-pointer font-mono text-mute">ver modelos que o 9router oferece</summary>
          <table className="mt-2 w-full font-mono text-[13.75px]">
            <tbody>
              {models.map((m) => (
                <tr key={m.id} className="border-b border-line">
                  <td className="py-1 pr-3">{m.id}</td>
                  <td className="pr-3">{m.vision ? <span className="text-mock">visão</span> : ''}</td>
                  <td className="pr-3">{m.tools ? 'ferramentas' : ''}</td>
                  <td className="text-right text-mute">{m.contexto ? `${Math.round(m.contexto / 1000)}k` : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </Section>
  );
}

export default function SettingsPage() {
  const [cfg, setCfg] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState(null);
  const [health, setHealth] = useState(null);
  const [serv, setServ] = useState(null);

  useEffect(() => {
    getLlmConfig().then(setCfg).catch((e) => setMsg({ ok: false, t: e.message }));
    getHealth().then(setHealth).catch(() => setHealth(false));
    getServidoresStatus().then(setServ).catch(() => setServ(false));
  }, []);

  const update = (p) => { setCfg((c) => ({ providers: c.providers.map((x) => (x.id === p.id ? p : x)) })); setDirty(true); };
  const save = async () => {
    try {
      setCfg(await saveLlmConfig({ providers: cfg.providers }));
      setDirty(false);
      setMsg({ ok: true, t: 'Configuração salva.' });
    } catch (e) { setMsg({ ok: false, t: e.message }); }
  };

  if (!cfg) return msg ? <p className="p-4 text-bad">{msg.t}</p> : <LoadingSpinner />;
  const router = cfg.providers.find((p) => p.id === '9router') ?? cfg.providers[0];
  const real = health && !health.servicenow_dry_run;

  return (
    <div className="h-full overflow-auto">
      <div className="flex flex-wrap items-center gap-3 border-b-2 border-rule bg-panel px-4 py-3">
        <div className="mr-auto">
          <div className="font-display text-2xl font-extrabold uppercase leading-none">Configurações</div>
          <p className="mt-1 text-xs text-mute">Parâmetros do agente. Segredos ficam no <span className="font-mono">.env</span>.</p>
        </div>
        {msg && <span className={`text-xs font-bold ${msg.ok ? 'text-ok' : 'text-bad'}`}>{msg.t}</span>}
        <Button tone="primary" onClick={save} disabled={!dirty}>{dirty ? 'Salvar alterações' : 'Salvo'}</Button>
      </div>

      <div className="space-y-4 p-4">
        {router && <Router p={router} onChange={update} />}

        <Section title="Despacho">
          <div className="flex flex-wrap items-center gap-3 p-4 text-sm">
            {health === null ? <span className="text-mute">…</span> : health === false ? <Badge tone="bad">api offline</Badge> : (
              <Badge tone={real ? 'bad' : 'warn'}>{real ? 'escrita real no ServiceNow' : 'dry-run (não escreve)'}</Badge>
            )}
            <span className="font-mono text-[13.75px] text-mute">Definido por SERVICENOW_DRY_RUN no .env; exige reiniciar o backend.</span>
          </div>
        </Section>

        <Section title="Servidores">
          <div className="flex flex-wrap items-center gap-3 p-4 text-sm">
            {serv === null ? <span className="text-mute">…</span> : !serv ? <Badge tone="bad">indisponível</Badge> : serv.carregado ? (
              <Badge tone="ok">{serv.total} servidores na lista</Badge>
            ) : (
              <Badge tone="warn">lista não encontrada</Badge>
            )}
            <span className="font-mono text-[13.75px] text-mute">
              Arquivo <span>data/servidores.csv</span> (exportado de Gestão De Servidores). Senhas e chaves da planilha nunca são lidas.
            </span>
          </div>
        </Section>
      </div>
    </div>
  );
}
