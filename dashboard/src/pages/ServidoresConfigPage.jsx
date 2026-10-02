import { useEffect, useState } from 'react';
import { getServidoresConfig, setCredencial, deleteCredencial, setDesabilitado } from '../api';
import { Button, inputClass } from '../components/ui';

export default function ServidoresConfigPage() {
  const [servidores, setServidores] = useState([]);
  const [lendo, setLendo] = useState(true);
  const [erro, setErro] = useState(null);
  const [editandoIp, setEditandoIp] = useState(null);
  const [usuario, setUsuario] = useState('');
  const [senha, setSenha] = useState('');
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    carregarConfig();
  }, []);

  const carregarConfig = async () => {
    setLendo(true);
    setErro(null);
    try {
      const data = await getServidoresConfig();
      setServidores(data.servidores);
    } catch (e) {
      setErro(e.message);
    } finally {
      setLendo(false);
    }
  };

  const handleSalvarCredencial = async (ip) => {
    if (!usuario.trim() || !senha.trim()) {
      setErro('Usuário e senha são obrigatórios');
      return;
    }
    setSalvando(true);
    try {
      await setCredencial(ip, usuario, senha);
      setEditandoIp(null);
      setUsuario('');
      setSenha('');
      await carregarConfig();
    } catch (e) {
      setErro(e.message);
    } finally {
      setSalvando(false);
    }
  };

  const handleRemoverCredencial = async (ip) => {
    if (!confirm('Remover credencial customizada?')) return;
    setSalvando(true);
    try {
      await deleteCredencial(ip);
      setEditandoIp(null);
      setUsuario('');
      setSenha('');
      await carregarConfig();
    } catch (e) {
      setErro(e.message);
    } finally {
      setSalvando(false);
    }
  };

  const handleToggleDesabilitado = async (ip, disabled) => {
    setSalvando(true);
    try {
      await setDesabilitado(ip, !disabled);
      await carregarConfig();
    } catch (e) {
      setErro(e.message);
    } finally {
      setSalvando(false);
    }
  };

  if (lendo) return <div className="p-6 font-mono text-mute">carregando…</div>;

  return (
    <div className="flex flex-col gap-6 p-6 max-w-4xl">
      <div>
        <h2 className="text-lg font-bold mb-2">Gerenciamento de Servidores CFTV</h2>
        <p className="text-sm text-mute">Configure credenciais customizadas e desabilite servidores no mapa de topologia.</p>
      </div>

      {erro && <div className="bg-bad/10 border-2 border-bad text-bad p-3 font-mono text-sm">{erro}</div>}

      {servidores.length === 0 ? (
        <p className="text-mute">Nenhum servidor CFTV encontrado.</p>
      ) : (
        <div className="border-2 border-rule bg-panel overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b-2 border-rule bg-panel2">
                <th className="text-left px-4 py-2 font-bold">IP</th>
                <th className="text-left px-4 py-2 font-bold">Servidor</th>
                <th className="text-left px-4 py-2 font-bold">Unidade</th>
                <th className="text-center px-4 py-2 font-bold">Credencial</th>
                <th className="text-center px-4 py-2 font-bold">Desabilitado</th>
                <th className="text-center px-4 py-2 font-bold">Ações</th>
              </tr>
            </thead>
            <tbody>
              {servidores.map((srv, idx) => (
                <tr key={srv.ip} className={idx % 2 === 0 ? '' : 'bg-panel2'} >
                  <td className="px-4 py-3 font-mono text-[12.5px]">{srv.ip}</td>
                  <td className="px-4 py-3 font-mono text-[12.5px]">{srv.nome}</td>
                  <td className="px-4 py-3 text-[12.5px]">{srv.unidade}</td>
                  <td className="px-4 py-3 text-center">
                    {srv.credencial_customizada ? (
                      <span className="inline-block px-2 py-1 bg-ok/20 text-ok font-bold text-[11.25px]">customizada</span>
                    ) : (
                      <span className="text-mute text-[11.25px]">padrão</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <input type="checkbox" checked={srv.disabled} onChange={() => handleToggleDesabilitado(srv.ip, srv.disabled)}
                      className="h-4 w-4 cursor-pointer" disabled={salvando} />
                  </td>
                  <td className="px-4 py-3 text-center">
                    {editandoIp === srv.ip ? (
                      <div className="flex flex-col gap-2">
                        <input value={usuario} onChange={(e) => setUsuario(e.target.value)} placeholder="usuário"
                          className={inputClass} disabled={salvando} />
                        <input type="password" value={senha} onChange={(e) => setSenha(e.target.value)} placeholder="senha"
                          className={inputClass} disabled={salvando} />
                        <div className="flex gap-1">
                          <button onClick={() => handleSalvarCredencial(srv.ip)} disabled={salvando} className="text-xs font-bold px-2 py-1 bg-ok text-ink hover:bg-ok/85">
                            {salvando ? 'salvando…' : 'salvar'}
                          </button>
                          <button onClick={() => setEditandoIp(null)} disabled={salvando} className="text-xs font-bold px-2 py-1 bg-mute text-ink hover:bg-mute/85">
                            cancelar
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex gap-1 justify-center">
                        <button onClick={() => { setEditandoIp(srv.ip); setUsuario(''); setSenha(''); }}
                          className="text-xs font-bold px-2 py-1 bg-panel2 border border-rule hover:bg-rule/20">
                          {srv.credencial_customizada ? 'editar' : 'adicionar'}
                        </button>
                        {srv.credencial_customizada && (
                          <button onClick={() => handleRemoverCredencial(srv.ip)} disabled={salvando}
                            className="text-xs font-bold px-2 py-1 bg-bad/20 text-bad hover:bg-bad/30">
                            remover
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="text-xs text-mute font-mono leading-relaxed">
        <p className="font-bold mb-1">Legenda:</p>
        <ul className="list-disc list-inside space-y-1">
          <li><strong>Credencial customizada:</strong> senha específica para este servidor (sobrescreve a padrão do .env)</li>
          <li><strong>Desabilitado:</strong> servidor não aparecerá no mapa de topologia</li>
          <li>Deixe em branco para voltar a usar a credencial padrão do .env</li>
        </ul>
      </div>
    </div>
  );
}
