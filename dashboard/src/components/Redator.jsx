import { useEffect, useState } from 'react';
import { getTextosComandos, redigirTexto } from '../api';
import { Button, inputClass } from './ui';

const LABEL = 'font-mono text-[12.5px] font-bold uppercase tracking-[0.14em] text-mute';
const MODELO = /\[(?!credencial\]|CPF\])[^\]\n]{2,60}\]/g;

// Colchetes de modelo ainda não preenchidos ([RITM], [descreva a ação executada]): o backend recusa o envio.
export const pendentes = (t) => [...new Set((t || '').match(MODELO) ?? [])];

const COMANDOS = [
  ['enche', 'Enche', 'Adiciona Análise e detalha a Resolução, sem inventar fato'],
  ['enxuto', 'Enxuto', 'Só Causa raiz, Resolução e Encerramento'],
  ['sem_req', 'Sem req', 'Tira a RITM e fecha com "Incidente encerrado."'],
  ['faz_um_pra_cada', 'Um pra cada', 'Um encerramento por câmera/item'],
  ['humanizada', 'Mensagem ao solicitante', 'Texto de Teams/WhatsApp no padrão do manual'],
];

let comandosCache = null;

// Redator do manual de textos: rascunho livre -> texto no padrão (IA via 9router). Só redige; o envio continua no
// botão de segurar de quem usa. Também guarda a Validação (Sobrenome, Nome) que vai na linha de Encerramento.
export default function Redator({ incidentNumber, texto, onTexto, validacao, onValidacao }) {
  const [rascunho, setRascunho] = useState('');
  const [busy, setBusy] = useState(null);
  const [res, setRes] = useState(null);
  const [mensagem, setMensagem] = useState(null);
  const [llm, setLlm] = useState(comandosCache?.llm ?? null);

  useEffect(() => {
    if (comandosCache) return;
    getTextosComandos().then((c) => { comandosCache = c; setLlm(c.llm); }).catch(() => setLlm(false));
  }, []);
  useEffect(() => { setRascunho(''); setRes(null); setMensagem(null); }, [incidentNumber]);

  const rodar = async (comando = null) => {
    setBusy(comando || 'redigir'); setRes(null);
    try {
      const r = await redigirTexto(incidentNumber, rascunho, comando, comando ? texto : null);
      if (r.pergunta) setRes({ pergunta: r.pergunta });
      else if (r.tipo === 'mensagem') { setMensagem(r.texto); setRes({ avisos: r.avisos }); }
      else { onTexto(r.texto); setRes({ avisos: r.avisos, modelo: r.modelo }); }
    } catch (e) { setRes({ erro: e.message }); }
    setBusy(null);
  };
  const semIa = llm === false ? 'IA desligada: confira o 9router em Configurações' : undefined;
  const falta = pendentes(texto);

  return (
    <div className="space-y-2">
      <label className="block">
        <span className={LABEL}>Rascunho · o que foi feito (a IA escreve no padrão do manual)</span>
        <textarea value={rascunho} onChange={(e) => setRascunho(e.target.value)} rows={2}
          placeholder="ex.: trocado patch cord no switch da portaria; validação Leila Canazart"
          className={`${inputClass} mt-1 font-mono`} />
      </label>
      <div className="flex flex-wrap items-center gap-1.5">
        <Button tone="primary" onClick={() => rodar()} disabled={!!busy || !rascunho.trim() || llm === false} title={semIa}>
          {busy === 'redigir' ? 'Redigindo…' : 'Redigir no padrão'}
        </Button>
        {COMANDOS.map(([id, rot, dica]) => (
          <Button key={id} onClick={() => rodar(id)} disabled={!!busy || llm === false || (!texto.trim() && !rascunho.trim())}
            title={semIa ?? dica}>{busy === id ? '…' : rot}</Button>
        ))}
      </div>
      {res?.pergunta && <p className="font-mono text-[12.5px] font-bold text-warn">A IA precisa saber: {res.pergunta}</p>}
      {res?.erro && <p className="font-mono text-[12.5px] font-bold text-bad">{res.erro}</p>}
      {res?.avisos?.length > 0 && (
        <ul className="font-mono text-[12.5px] text-warn">{res.avisos.map((a) => <li key={a}>· {a}</li>)}</ul>
      )}
      {mensagem && (
        <div className="border-2 border-line bg-panel2 p-2">
          <div className="flex items-center justify-between">
            <span className={LABEL}>Mensagem ao solicitante (não é enviada)</span>
            <Button onClick={() => navigator.clipboard?.writeText(mensagem)}>Copiar</Button>
          </div>
          <pre className="mt-1 whitespace-pre-wrap font-mono text-[12.5px]">{mensagem}</pre>
        </div>
      )}
      <label className="block max-w-sm">
        <span className={LABEL}>Validação (opcional)</span>
        <input value={validacao} onChange={(e) => onValidacao(e.target.value)} placeholder="Nome Sobrenome de quem validou"
          className={`${inputClass} mt-1`} />
        <span className="font-mono text-[11.25px] text-mute">vai como "Validação: Sobrenome, Nome." na linha de Encerramento</span>
      </label>
      {falta.length > 0 && (
        <p className="font-mono text-[12.5px] font-bold text-bad">Preencha {falta.join(', ')} no texto antes de enviar.</p>
      )}
    </div>
  );
}
