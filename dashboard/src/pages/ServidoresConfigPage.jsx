import { useEffect, useMemo, useState } from 'react';
import { deleteCredencial, getServidoresConfig, relerServidor, setCredencial, setDesabilitado } from '../api';
import LoadingSpinner from '../components/LoadingSpinner';
import { Badge, Button, inputClass, unitColor } from '../components/ui';

const LABEL = 'font-mono text-[12.5px] font-bold uppercase tracking-[0.14em] text-mute';
const ERRO = { credencial: 'senha recusada', timeout: 'porta não atende', lento: 'servidor lento', rede: 'conexão recusada',
  config: 'Digifort não configurado', resposta: 'resposta inesperada' };
const fold = (s) => (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();

function Estado({ s }) {
  if (s.disabled) return <Badge tone="mute">escondido</Badge>;
  if (s.ok === true) return <Badge tone="ok">ok · {s.cameras} câm.</Badge>;
  if (s.ok === false) return <Badge tone="bad" title={s.erro}>{ERRO[s.tipo_erro] ?? 'falha'}</Badge>;
  return <Badge tone="mute">não lido</Badge>;
}

function Linha({ s, padrao, onAtualizar }) {
  const [aberto, setAberto] = useState(false);
  const [usuario, setUsuario] = useState(s.usuario_proprio || padrao || '');
  const [senha, setSenha] = useState('');
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);

  const rodar = async (qual, fn) => {
    setBusy(qual); setMsg(null);
    try {
      const r = await fn();
      if (r && 'ok' in r) setMsg(r.ok ? { ok: true, t: `respondeu · ${r.cameras} câmeras` } : { ok: false, t: r.erro || 'falhou' });
      onAtualizar(s.ip, r);
      return r;
    } catch (e) { setMsg({ ok: false, t: e.message }); return null; } finally { setBusy(null); }
  };
  const salvar = async () => {
    const r = await rodar('salvar', () => setCredencial(s.ip, usuario, senha));
    if (r?.ok) { setSenha(''); setAberto(false); }
  };

  return (
    <div className={`border-b border-line ${s.disabled ? 'opacity-60' : ''}`}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-4 py-2">
        <div className="min-w-[13rem] flex-1">
          <div className="font-mono text-[13.75px] font-bold">{s.nome}</div>
          <div className="font-mono text-[12.5px] text-mute">{s.ip} · {s.tipo}</div>
        </div>
        <Estado s={s} />
        <span className="w-44 font-mono text-[12.5px] text-mute" title="Credencial usada para ler este servidor">
          {s.usuario_proprio ? <span className="font-bold text-ink">própria · {s.usuario_proprio}</span> : 'padrão do .env'}
        </span>
        <div className="flex flex-wrap gap-1.5">
          <Button onClick={() => setAberto((v) => !v)} disabled={!!busy}>{aberto ? 'Fechar' : 'Senha'}</Button>
          <Button onClick={() => rodar('reler', () => relerServidor(s.ip))} disabled={!!busy || s.disabled}>
            {busy === 'reler' ? 'Lendo…' : 'Reler'}
          </Button>
          <Button onClick={() => rodar('mapa', () => setDesabilitado(s.ip, !s.disabled))} disabled={!!busy}
            title={s.disabled ? 'Voltar a mostrar e ler este servidor no mapa' : 'Esconder do mapa (não é mais lido no Digifort)'}>
            {s.disabled ? 'Mostrar no mapa' : 'Esconder do mapa'}
          </Button>
        </div>
      </div>
      {(s.ok === false && !s.disabled && s.erro) && !msg && (
        <div className="px-4 pb-2 font-mono text-[12.5px] text-bad">{s.erro}</div>
      )}
      {msg && <div className={`px-4 pb-2 font-mono text-[12.5px] font-bold ${msg.ok ? 'text-ok' : 'text-bad'}`}>{msg.t}</div>}
      {aberto && (
        <div className="flex flex-wrap items-end gap-2 border-t border-line bg-panel2 px-4 py-3">
          <label className="w-48">
            <span className={LABEL}>Usuário</span>
            <input className={`${inputClass} mt-1 font-mono`} value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="off" />
          </label>
          <label className="w-48">
            <span className={LABEL}>Senha</span>
            <input type="password" className={`${inputClass} mt-1 font-mono`} value={senha} onChange={(e) => setSenha(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && usuario.trim() && senha && salvar()} autoComplete="new-password" />
          </label>
          <Button tone="primary" onClick={salvar} disabled={!!busy || !usuario.trim() || !senha}>
            {busy === 'salvar' ? 'Testando…' : 'Salvar e testar'}
          </Button>
          {s.usuario_proprio && (
            <Button onClick={() => rodar('padrao', () => deleteCredencial(s.ip))} disabled={!!busy}>Voltar à padrão</Button>
          )}
          <span className="font-mono text-[12.5px] text-mute">Fica só nesta máquina (data/digifort_credenciais.json, fora do git).</span>
        </div>
      )}
    </div>
  );
}

// Servidores CFTV: senha própria por servidor, reler um só e esconder do mapa os que não interessam.
export default function ServidoresConfigPage() {
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState(null);
  const [filtro, setFiltro] = useState('falha');
  const [q, setQ] = useState('');

  useEffect(() => { getServidoresConfig().then(setDados).catch((e) => setErro(e.message)); }, []);

  const atualizar = (ip, r) => setDados((d) => ({ ...d, servidores: d.servidores.map((s) => {
    if (s.ip !== ip) return s;
    if (r && 'disabled' in r && !('ok' in r)) return { ...s, disabled: r.disabled };
    return { ...s, ok: r.ok, tipo_erro: r.tipo_erro, erro: r.erro, cameras: r.cameras,
      usuario_proprio: r.usuario_proprio !== undefined ? r.usuario_proprio : s.usuario_proprio };
  }) }));

  // a lista volta do servidor depois de trocar a senha (usuário próprio atualizado)
  const recarregar = () => getServidoresConfig().then(setDados).catch(() => {});

  const lista = dados?.servidores ?? [];
  const cont = {
    todos: lista.length,
    falha: lista.filter((s) => !s.disabled && s.ok === false).length,
    escondidos: lista.filter((s) => s.disabled).length,
  };
  const grupos = useMemo(() => {
    const f = fold(q);
    const vis = lista.filter((s) => (filtro === 'todos' || (filtro === 'falha' ? !s.disabled && s.ok === false : s.disabled))
      && (!f || fold(`${s.nome} ${s.ip} ${s.unidade}`).includes(f)));
    const g = {};
    vis.forEach((s) => { (g[s.unidade] ||= []).push(s); });
    return Object.entries(g);
  }, [lista, filtro, q]);

  if (erro) return <p className="p-4 font-bold text-bad">{erro}</p>;
  if (!dados) return <LoadingSpinner />;

  return (
    <div className="h-full overflow-auto">
      <div className="flex flex-wrap items-center gap-3 border-b-2 border-rule bg-panel px-4 py-3">
        <div className="mr-auto">
          <div className="font-display text-2xl font-extrabold uppercase leading-none">Servidores CFTV</div>
          <p className="mt-1 text-xs text-mute">
            Senha própria para quem recusa a padrão ({dados.usuario_padrao || 'sem usuário no .env'}), reler um servidor e esconder do
            mapa os que não precisam aparecer. O estado é o da última leitura do mapa.
          </p>
        </div>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="filtrar nome, IP ou unidade…" className={`${inputClass} w-60`} />
        <div className="flex">
          {[['falha', 'Com falha'], ['escondidos', 'Escondidos'], ['todos', 'Todos']].map(([id, rot]) => (
            <button key={id} onClick={() => setFiltro(id)}
              className={`border-2 border-rule px-3 py-1.5 font-display text-xs font-bold uppercase tracking-wide -ml-0.5 first:ml-0 ${filtro === id ? 'bg-invert text-invert-ink' : 'bg-panel text-ink hover:bg-panel2'}`}>
              {rot} · {cont[id]}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-4 p-4">
        {grupos.length === 0 && (
          <p className="font-mono text-[13.75px] text-mute">
            {filtro === 'falha' ? 'Nenhum servidor com falha na última leitura.' : filtro === 'escondidos' ? 'Nenhum servidor escondido.' : 'Nenhum servidor.'}
          </p>
        )}
        {grupos.map(([unidade, srv]) => (
          <section key={unidade} className="border-2 border-rule bg-panel">
            <header className="border-b-2 border-rule px-4 py-2 font-display text-lg font-extrabold uppercase leading-none"
              style={{ borderLeft: `8px solid ${unitColor(unidade)}` }}>
              {unidade}
            </header>
            {srv.map((s) => (
              <Linha key={s.ip} s={s} padrao={dados.usuario_padrao}
                onAtualizar={(ip, r) => { atualizar(ip, r); if (r && 'ok' in r) recarregar(); }} />
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}
