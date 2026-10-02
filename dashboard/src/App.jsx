import { useState } from 'react';
import Header from './components/Header';
import Secoes from './components/Secoes';
import IncidentsPage from './pages/IncidentsPage';
import BacklogPage from './pages/BacklogPage';
import TasksPage from './pages/TasksPage';
import AgentPage from './pages/AgentPage';
import CameraPage from './pages/CameraPage';
import SettingsPage from './pages/SettingsPage';
import MetricsPage from './pages/MetricsPage';
import './index.css';

const BACKLOG = [
  { id: 'backlog', label: 'Backlog', Page: BacklogPage },
  { id: 'tasks', label: 'Tasks', Page: TasksPage },
];

function BacklogTasks({ target }) {
  return <Secoes secoes={BACKLOG} target={target} label="Backlog e Tasks" />;
}

// Abas da régua; o resto abre por células do cabeçalho (IA, gráfico de métricas, engrenagem).
const TABS = [
  { id: 'incidents', label: 'Operação', Page: IncidentsPage },
  { id: 'cameras', label: 'Câmeras e servidores', Page: CameraPage },
  { id: 'backlog', label: 'Backlog', Page: BacklogTasks },
];
const EXTRAS = [
  { id: 'agent', label: 'Agente de IA', Page: AgentPage },
  { id: 'metrics', label: 'Métricas', Page: MetricsPage },
  { id: 'settings', label: 'Configurações', Page: SettingsPage },
];

export default function App() {
  const [current, setCurrent] = useState('incidents');
  // alvo na página de destino: incidente (Métricas -> Câmeras) ou seção ('regras', 'tasks')
  const [target, setTarget] = useState(null);
  const go = (tab, alvo = null) => { setTarget(alvo); setCurrent(tab); };
  const { Page, label } = [...TABS, ...EXTRAS].find((t) => t.id === current);

  return (
    <div className="flex h-full flex-col">
      <Header tabs={TABS} current={current} onSelect={(t) => go(t)} />
      <main className="min-h-0 flex-1" aria-label={label}>
        <Page go={go} target={target} />
      </main>
    </div>
  );
}
