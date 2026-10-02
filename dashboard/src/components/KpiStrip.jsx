import useMetrics from '../hooks/useMetrics';
import { Kpi } from './ui';

export default function KpiStrip() {
  const { metrics: m, error } = useMetrics(10000);
  const v = (x, fallback = '—') => (m ? x : fallback);

  return (
    <div className="flex shrink-0 flex-wrap border-b-2 border-rule bg-panel">
      <Kpi label="Aguardando você" value={v(m?.pendentes)} tone={m?.pendentes > 0 ? 'bad' : 'ink'} hint="pendentes de aprovação" />
      <Kpi label="Processados" value={v(m?.total_processados)} hint="total analisado" />
      <Kpi label="Automação" value={v(m?.automacao_percentual)} unit="%" tone="accent" hint="sem chamar LLM" />
      <Kpi label="Precisão" value={v(m?.precisao_percentual)} unit="%" tone="ok" hint="aprovado sem edição" />
      <Kpi label="Tempo médio" value={v(m?.tempo_medio_segundos)} unit="s" hint="por análise" />
      <Kpi label="LLM hoje" value={v(m?.chamadas_claude_hoje)} tone="mock" hint="chamadas" />
      {error && <span className="self-center px-3 text-xs text-bad">métricas: {error}</span>}
    </div>
  );
}
