import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, URL_EJEMPLO_IMPORTACION } from '../api/cliente';
import type { InformeImportacion } from '../tipos/api';
import { Campo, Aviso, CabeceraPagina, EtiquetaEstado } from '../componentes/interfaz';
import { useRetroalimentacionFormulario } from '../hooks/useRetroalimentacionFormulario';

export default function PaginaImportaciones() {
  const [archivo, establecerArchivo] = useState<File | null>(null);
  const [informe, establecerInforme] = useState<InformeImportacion | null>(null);
  const retroalimentacionFormulario = useRetroalimentacionFormulario();
  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    retroalimentacionFormulario.limpiar();
    if (!archivo) { retroalimentacionFormulario.establecerValidacion({ file: 'Selecciona un archivo CSV.' }); return; }
    if (archivo.size > 1_048_576) { retroalimentacionFormulario.establecerValidacion({ file: 'El archivo supera el límite de 1 MiB.' }); return; }
    retroalimentacionFormulario.establecerPendiente(true);
    establecerInforme(null);
    try { establecerInforme(await api.importarReservas(archivo)); }
    catch (error) { retroalimentacionFormulario.establecerFallo(error); }
    finally { retroalimentacionFormulario.establecerPendiente(false); }
  }
  return <>
    <CabeceraPagina titulo="Importaciones" descripcion="Carga pedidos y revisa el resultado de cada solicitud de reserva." accion={<a className="button button-secondary" href={URL_EJEMPLO_IMPORTACION} download>Descargar CSV de ejemplo</a>} />
    <div className="split-grid import-layout">
      <section className="panel"><div className="panel-header"><h2>Importar pedidos</h2></div>
        <p>Una fila reserva una unidad de equipo. Las filas correctas se guardan aunque otras se rechacen.</p>
        <form onSubmit={(evento) => { void enviar(evento); }} noValidate className="stack">
          {retroalimentacionFormulario.mensaje && <Aviso tono="error" errores={retroalimentacionFormulario.errores}>{retroalimentacionFormulario.mensaje}</Aviso>}
          <Campo nombre="file" etiqueta="Archivo CSV" error={retroalimentacionFormulario.errores.file} ayuda="UTF-8, con o sin BOM. Máximo 1 MiB y 500 filas de datos.">
            <input type="file" accept=".csv,text/csv" onChange={(evento) => { establecerArchivo(evento.target.files?.[0] ?? null); establecerInforme(null); retroalimentacionFormulario.limpiar(); }} disabled={retroalimentacionFormulario.pendiente} />
          </Campo>
          <div className="form-actions"><button className="button" disabled={retroalimentacionFormulario.pendiente}>{retroalimentacionFormulario.pendiente ? 'Importando…' : 'Importar pedidos'}</button></div>
        </form>
      </section>
      <aside className="panel instructions"><h2>Preparar el archivo</h2><p>Usa comas como separador y conserva esta cabecera exacta:</p>
        <code className="csv-header">external_reference,customer_name,customer_email,equipment_code,starts_on,ends_on</code>
        <ul><li>Fechas con formato <strong>YYYY-MM-DD</strong>. El día de fin queda libre.</li><li>Usa el código de una unidad del catálogo.</li><li>La referencia externa identifica el pedido: repetir los mismos datos no crea otra reserva, incluso si está cancelada.</li><li>Una referencia con datos distintos se rechaza sin sobrescribir. Puedes corregir y reenviar el archivo.</li></ul>
      </aside>
    </div>
    {informe && <section className="panel import-report">
      <div className="panel-header"><h2>Resultado de la importación</h2></div>
      <Aviso tono="success">{informe.totals.total} filas procesadas: {informe.totals.accepted} aceptadas, {informe.totals.already_imported} ya importadas y {informe.totals.rejected} rechazadas.</Aviso>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabla desplazable horizontalmente"><table aria-label="Resultado de la importación"><thead><tr><th scope="col">Línea</th><th scope="col">Referencia</th><th scope="col">Resultado</th><th scope="col">Reserva</th><th scope="col">Explicación</th></tr></thead><tbody>
        {informe.rows.map((fila) => <tr key={fila.line}><td>{fila.line}</td><td>{fila.external_reference ?? 'Sin referencia'}</td><td><EtiquetaEstado clase={fila.status} /></td><td>{fila.reservation ? <><Link to={`/admin/reservas/${fila.reservation.id}`}>Reserva #{fila.reservation.id}</Link><div><EtiquetaEstado clase={fila.reservation.status} /></div></> : '—'}</td><td>{fila.message}</td></tr>)}
      </tbody></table></div>
      {informe.rows.length === 0 && <p className="text-muted">El archivo sólo contenía la cabecera. No se han creado reservas.</p>}
    </section>}
  </>;
}
