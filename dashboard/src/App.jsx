import { useState } from 'react';
import Header from './components/Header';
import KpiStrip from './components/KpiStrip';
import IncidentsPage from './pages/IncidentsPage';
import BacklogPage from './pages/BacklogPage';
import TasksPage from './pages/TasksPage';
import AgentPage from './pages/AgentPage';
import CameraPage from './pages/CameraPage';
import SettingsPage from './pages/SettingsPage';
import RulesPage from './pages/RulesPage';
import HistoryPage from './pages/HistoryPage';
import MetricsPage from './pages/MetricsPage';
import './index.css';

const TABS = [
  { id: 'incidents', label: 'Operação', Page: IncidentsPage },
  { id: 'agent', label: 'Agente', Page: AgentPage },
  { id: 'backlog', label: 'Painel', Page: BacklogPage },
  { id: 'tasks', label: 'Tasks', Page: TasksPage },
  { id: 'cameras', label: 'Câmeras', Page: CameraPage },
  { id: 'rules', label: 'Regras', Page: RulesPage },
  { id: 'history', label: 'Histórico', Page: HistoryPage },
  { id: 'metrics', label: 'Métricas', Page: MetricsPage },
];
const SETTINGS = { id: 'settings', label: 'Configurações', Page: SettingsPage };

export default function App() {
  const [current, setCurrent] = useState('incidents');
  const [target, setTarget] = useState(null); // incidente a abrir na aba de destino (ex.: Métricas -> Câmeras)
  const go = (tab, inc = null) => { setTarget(inc); setCurrent(tab); };
  const { Page, label } = [...TABS, SETTINGS].find((t) => t.id === current);

  return (
    <div className="flex h-full flex-col">
      <Header tabs={TABS} current={current} onSelect={(t) => go(t)} />
      <KpiStrip />
      <main className="min-h-0 flex-1" aria-label={label}>
        <Page go={go} target={target} />
      </main>
    </div>
  );
}
