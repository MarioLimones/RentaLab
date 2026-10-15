import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, IMPORT_EXAMPLE_URL } from '../api/client';
import type { ImportReport } from '../types/api';
import { Field, Notice, PageHeader, StatusBadge } from '../components/ui';
import { useFormFeedback } from '../hooks/useFormFeedback';

export default function ImportsPage() {
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const feedback = useFormFeedback();
  async function submit(event: FormEvent) {
    event.preventDefault();
    feedback.clear();
    if (!file) { feedback.setValidation({ file: 'Selecciona un archivo CSV.' }); return; }
    if (file.size > 1_048_576) { feedback.setValidation({ file: 'El archivo supera el límite de 1 MiB.' }); return; }
    feedback.setPending(true);
    setReport(null);
    try { setReport(await api.importReservations(file)); }
    catch (error) { feedback.setFailure(error); }
    finally { feedback.setPending(false); }
  }
  return <>
    <PageHeader title="Importaciones" description="Carga pedidos y revisa el resultado de cada solicitud de reserva." action={<a className="button button-secondary" href={IMPORT_EXAMPLE_URL} download>Descargar CSV de ejemplo</a>} />
    <div className="split-grid import-layout">
      <section className="panel"><div className="panel-header"><h2>Importar pedidos</h2></div>
        <p>Una fila reserva una unidad de equipo. Las filas correctas se guardan aunque otras se rechacen.</p>
        <form onSubmit={(event) => { void submit(event); }} noValidate className="stack">
          {feedback.message && <Notice tone="error" errors={feedback.errors}>{feedback.message}</Notice>}
          <Field name="file" label="Archivo CSV" error={feedback.errors.file} hint="UTF-8, con o sin BOM. Máximo 1 MiB y 500 filas de datos.">
            <input type="file" accept=".csv,text/csv" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setReport(null); feedback.clear(); }} disabled={feedback.pending} />
          </Field>
          <div className="form-actions"><button className="button" disabled={feedback.pending}>{feedback.pending ? 'Importando…' : 'Importar pedidos'}</button></div>
        </form>
      </section>
      <aside className="panel instructions"><h2>Preparar el archivo</h2><p>Usa comas como separador y conserva esta cabecera exacta:</p>
        <code className="csv-header">external_reference,customer_name,customer_email,equipment_code,starts_on,ends_on</code>
        <ul><li>Fechas con formato <strong>YYYY-MM-DD</strong>. El día de fin queda libre.</li><li>Usa el código de una unidad del catálogo.</li><li>La referencia externa identifica el pedido: repetir los mismos datos no crea otra reserva, incluso si está cancelada.</li><li>Una referencia con datos distintos se rechaza sin sobrescribir. Puedes corregir y reenviar el archivo.</li></ul>
      </aside>
    </div>
    {report && <section className="panel import-report">
      <div className="panel-header"><h2>Resultado de la importación</h2></div>
      <Notice tone="success">{report.totals.total} filas procesadas: {report.totals.accepted} aceptadas, {report.totals.already_imported} ya importadas y {report.totals.rejected} rechazadas.</Notice>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabla desplazable horizontalmente"><table aria-label="Resultado de la importación"><thead><tr><th scope="col">Línea</th><th scope="col">Referencia</th><th scope="col">Resultado</th><th scope="col">Reserva</th><th scope="col">Explicación</th></tr></thead><tbody>
        {report.rows.map((row) => <tr key={row.line}><td>{row.line}</td><td>{row.external_reference ?? 'Sin referencia'}</td><td><StatusBadge kind={row.status} /></td><td>{row.reservation ? <><Link to={`/admin/reservas/${row.reservation.id}`}>Reserva #{row.reservation.id}</Link><div><StatusBadge kind={row.reservation.status} /></div></> : '—'}</td><td>{row.message}</td></tr>)}
      </tbody></table></div>
      {report.rows.length === 0 && <p className="text-muted">El archivo sólo contenía la cabecera. No se han creado reservas.</p>}
    </section>}
  </>;
}
