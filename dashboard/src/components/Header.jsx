import { useEffect, useState } from 'react';
import { getHealth, getSession, sessionLogin } from '../api';
import { useTheme } from '../lib/theme';

// Régua única: toda célula tem a mesma altura, divisória e tipografia das abas.
const CELL = 'flex border-l-2 border-rule';
const TAB = 'flex items-center gap-2 px-3.5 font-display text-sm font-bold uppercase tracking-wide transition-colors';
const SUB = 'font-mono text-[11.25px] font-bold uppercase tracking-[0.14em]';

function Lamp({ on, warn }) {
  return <span className={`inline-block h-2.5 w-2.5 border-2 border-current ${on ? 'bg-current' : ''} ${warn ? 'pulse-dot' : ''}`} />;
}

function ServiceNowButton() {
  const [sn, setSn] = useState(undefined); // undefined = carregando, null = sem resposta da API

  useEffect(() => {
    const poll = () => getSession().then(setSn).catch(() => setSn(null));
    poll();
    const t = setInterval(poll, 3000);
    return () => clearInterval(t);
  }, []);

  if (sn?.mock) return null;
  const connected = !!sn?.connected;
  const busy = !!sn?.busy;
  const idle = !connected && !busy && sn;
  const detail = sn === undefined ? 'verificando…' : sn === null ? 'api sem resposta'
    : connected ? [sn.instance, sn.user].filter(Boolean).join(' · ') : busy ? 'aguardando login…' : 'sessão expirada';
  const title = sn?.message ?? (sn === null ? 'A API local não respondeu' : 'Sessão do ServiceNow');

  return (
    <button
      onClick={() => idle && sessionLogin().then(setSn).catch(() => setSn(null))}
      disabled={!idle}
      title={idle ? `${title} Clique para abrir o login (SSO/MFA).` : title}
      className="ml-8 flex items-stretch border-x-2 border-rule bg-sn text-left text-black hover:brightness-95 disabled:cursor-default disabled:hover:brightness-100"
    >
      <span className={`flex w-11 items-center justify-center bg-black text-sn ${busy ? 'pulse-dot' : ''}`} aria-hidden="true">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="square">
          {connected ? (
            <path d="M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0zM12 17v5" />
          ) : (
            <>
              <path d="M9 1v4M15 1v4M6 5h12v3a6 6 0 0 1-12 0zM12 14v1M12 19v4" />
              <path d="M3 21L21 3" />
            </>
          )}
        </svg>
      </span>
      <span className="flex flex-col justify-center px-3 py-1.5 leading-none">
        <span className="font-display text-sm font-bold uppercase tracking-wide">ServiceNow</span>
        <span className={`${SUB} mt-1 text-black/70`}>{detail}</span>
      </span>
      {idle && (
        <span className="flex items-center border-l-2 border-black px-3 font-display text-sm font-bold uppercase tracking-wide">
          Conectar
        </span>
      )}
    </button>
  );
}

function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className={`${CELL} flex-col justify-center px-3.5 text-right`}>
      <span className="font-display text-lg font-bold leading-none tabular-nums">{now.toLocaleTimeString('pt-BR')}</span>
      <span className={`${SUB} mt-0.5 text-mute`}>{now.toLocaleDateString('pt-BR', { weekday: 'short' }).replace('.', '')} {now.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}</span>
    </div>
  );
}

export default function Header({ tabs, current, onSelect }) {
  const [health, setHealth] = useState(null);
  const [theme, toggleTheme] = useTheme();

  useEffect(() => {
    const poll = () => getHealth().then(setHealth).catch(() => setHealth(false));
    poll();
    const h = setInterval(poll, 10000);
    return () => clearInterval(h);
  }, []);

  const apiOk = !!health;
  const real = apiOk && !health.servicenow_dry_run;
  const dark = theme === 'dark';
  const settings = current === 'settings';

  return (
    <header className="flex shrink-0 flex-wrap items-stretch border-b-2 border-rule bg-panel">
      <div className="flex flex-col justify-center bg-invert px-4 py-2 text-invert-ink">
        <span className="font-display text-xl font-extrabold uppercase leading-none tracking-tight">CFTV</span>
        <span className={`${SUB} mt-0.5 opacity-70`}>Despacho</span>
      </div>

      <nav className="flex items-stretch" aria-label="Seções">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => onSelect(t.id)}
            aria-current={current === t.id ? 'page' : undefined}
            className={`${TAB} border-l-2 border-rule ${current === t.id ? 'bg-invert text-invert-ink' : 'text-ink hover:bg-panel2'}`}
          >
            {t.label}
          </button>
        ))}
        <span className="border-l-2 border-rule" />
        <ServiceNowButton />
      </nav>

      <div className="ml-auto flex items-stretch">
        {health?.servicenow_mock && (
          <div className={`${CELL} items-center bg-mock px-3.5 ${SUB} text-white`} title="Incidentes fictícios; nada vai ao ServiceNow">mock</div>
        )}

        <div className={`${CELL} flex-col justify-center gap-1 px-3.5 ${SUB}`} aria-label="Estado dos serviços">
          <span className={`flex items-center gap-2 ${health === false ? 'text-bad' : apiOk ? 'text-ink' : 'text-mute'}`}>
            <Lamp on={apiOk} warn={health === false} />
            API {health === null ? '…' : apiOk ? 'ok' : 'fora'}
          </span>
          <span className={`flex items-center gap-2 ${health?.llm_enabled ? 'text-ink' : 'text-mute'}`} title="IA via 9router (só casos difíceis)">
            <Lamp on={!!health?.llm_enabled} />
            IA {health?.llm_enabled ? 'on' : 'off'}
          </span>
        </div>

        <Clock />

        <div className={CELL}>
          <button
            onClick={toggleTheme}
            title={dark ? 'Mudar para o modo claro' : 'Mudar para o modo escuro'}
            aria-label={dark ? 'Modo claro' : 'Modo escuro'}
            className={`${TAB} text-ink hover:bg-panel2`}
          >
            <span className="relative inline-block h-4 w-4 overflow-hidden border-2 border-current">
              <span className={`absolute inset-y-0 left-0 w-1/2 bg-current ${dark ? '' : 'translate-x-full'}`} />
            </span>
          </button>
        </div>

        <div className={CELL}>
          <button
            onClick={() => onSelect('settings')}
            title="Configurações"
            aria-label="Configurações"
            aria-current={settings ? 'page' : undefined}
            className={`${TAB} ${settings ? 'bg-invert text-invert-ink' : 'text-ink hover:bg-panel2'}`}
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" aria-hidden="true">
              <circle cx="12" cy="12" r="6" strokeWidth="2.6" />
              <circle cx="12" cy="12" r="2" strokeWidth="2.4" />
              <path strokeWidth="3.6" strokeLinecap="butt" d="M12 1.5v4.5M12 18v4.5M1.5 12H6M18 12h4.5M4.6 4.6l3.2 3.2M16.2 16.2l3.2 3.2M19.4 4.6l-3.2 3.2M7.8 16.2l-3.2 3.2" />
            </svg>
          </button>
        </div>

        {apiOk && (
          <div
            className={`${CELL} items-center gap-2 px-4 font-display text-sm font-bold uppercase tracking-wide ${real ? 'bg-bad text-white' : 'bg-warn text-black'}`}
            title={real ? 'Aprovar ESCREVE no ServiceNow' : 'Aprovar não escreve no ServiceNow'}
          >
            {real ? 'Escrita real' : 'Dry-run'}
          </div>
        )}
      </div>
    </header>
  );
}
