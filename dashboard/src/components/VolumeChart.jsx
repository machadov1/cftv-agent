import { Bar, BarChart, CartesianGrid, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useThemeColors } from '../lib/theme';

// Entraram x encerrados por mês (o mês atual está em andamento)
export default function VolumeChart({ data, error, height = 200 }) {
  const c = useThemeColors();
  if (error) return <div className="p-4 text-xs font-bold text-bad">{error}</div>;
  if (!data) return <div className="p-4 font-mono text-[12.5px] text-mute">Lendo a volumetria no ServiceNow…</div>;
  const AXIS = { fill: c.mute, fontSize: 11 };
  const ultimo = data.meses[data.meses.length - 1]?.mes;
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <BarChart data={data.meses} margin={{ left: -18, right: 8, top: 16 }} barGap={2}>
          <CartesianGrid vertical={false} stroke={c.line} />
          <XAxis dataKey="mes" tick={AXIS} stroke={c.line} tickFormatter={(m) => (m === ultimo ? `${m}*` : m)} />
          <YAxis allowDecimals={false} tick={AXIS} stroke={c.line} />
          <Tooltip contentStyle={{ background: c.panel, border: `2px solid ${c.rule}`, borderRadius: 0, fontSize: 12, color: c.ink }}
            cursor={{ fill: c.line, opacity: 0.3 }} />
          <Legend wrapperStyle={{ fontSize: 11 }} iconType="square" />
          <Bar dataKey="entraram" fill={c.warn}>
            <LabelList dataKey="entraram" position="top" style={{ fill: c.mute, fontSize: 11 }} />
          </Bar>
          <Bar dataKey="encerrados" fill={c.ok}>
            <LabelList dataKey="encerrados" position="top" style={{ fill: c.ink, fontSize: 11, fontWeight: 700 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
