import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api, type DateRange, type Equipment } from '../api/client';
import { Notice } from '../components/ui';
import { DateRangeFields } from '../portal/DateRangeFields';
import { dateRangeErrors } from '../portal/dateRange';
import { formatDate } from '../lib/dates';

export default function AvailabilitySummary({ equipment }: { equipment: Equipment[] }) {
  const [range, setRange] = useState<DateRange>({ start_date: '', end_date: '' });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [result, setResult] = useState<{ key: string; available: number; total: number } | null>(null);
  const sequence = useRef(0);
  const active = equipment.filter((unit) => unit.active);
  const key = JSON.stringify([range.start_date, range.end_date, active.map((unit) => unit.id)]);
  useEffect(() => () => { sequence.current += 1; }, []);

  function changeDate(name: keyof DateRange, value: string) {
    sequence.current += 1;
    setRange((previous) => ({ ...previous, [name]: value }));
    setResult(null);
    setPendingKey(null);
    setErrors({});
    setFailure(null);
  }

  async function consult(event: FormEvent) {
    event.preventDefault();
    if (pendingKey === key) return;
    const validation = dateRangeErrors(range, true);
    setErrors(validation);
    setFailure(null);
    if (Object.keys(validation).length) return;
    const version = ++sequence.current;
    setPendingKey(key);
    setResult(null);
    try {
      const results = await Promise.all(active.map((unit) => api.getEquipmentAvailability(unit.id, range)));
      if (sequence.current === version) setResult({ key, available: results.filter((item) => item.available).length, total: active.length });
    } catch (error) {
      if (sequence.current === version) setFailure(error instanceof Error ? error.message : 'No se pudo consultar la disponibilidad.');
    } finally {
      if (sequence.current === version) setPendingKey(null);
    }
  }

  return <section className="panel stack" aria-labelledby="admin-availability-title">
    <h2 id="admin-availability-title">Disponibilidad por fechas</h2>
    <p className="text-muted">Selecciona el intervalo para consultar las unidades activas. El día de devolución queda excluido.</p>
    <form className="stack" noValidate onSubmit={(event) => { void consult(event); }}>
      <DateRangeFields value={range} onChange={changeDate} errors={errors} />
      {Object.keys(errors).length > 0 && <Notice tone="error" errors={errors}>Revisa las fechas indicadas.</Notice>}
      <div><button className="button button-secondary" type="submit" disabled={pendingKey === key}>{pendingKey === key ? 'Consultando disponibilidad…' : 'Consultar disponibilidad'}</button></div>
    </form>
    {failure && <Notice tone="error">{failure} Vuelve a consultar para reintentar.</Notice>}
    {result?.key === key && <div role="status"><strong>{result.available} de {result.total} equipos activos disponibles</strong><p>Del {formatDate(range.start_date)} al {formatDate(range.end_date)} (fin excluido). Consulta orientativa; al confirmar se vuelve a comprobar.</p></div>}
  </section>;
}
