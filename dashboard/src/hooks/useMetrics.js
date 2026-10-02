import { useEffect, useState } from 'react';
import { getMetrics } from '../api';

export default function useMetrics(intervalMs = 15000) {
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      getMetrics()
        .then((m) => alive && (setMetrics(m), setError(null)))
        .catch((e) => alive && setError(e.message));
    load();
    const id = setInterval(load, intervalMs);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [intervalMs]);

  return { metrics, error };
}
