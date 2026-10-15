import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api, type IntervaloFechas, type Equipo } from '../api/cliente';
import { Aviso } from '../componentes/interfaz';
import { CamposIntervaloFechas } from '../portal/CamposIntervaloFechas';
import { erroresIntervaloFechas } from '../portal/intervaloFechas';
import { formatearFecha } from '../utilidades/fechas';

export default function ResumenDisponibilidad({ equipo }: { equipo: Equipo[] }) {
  const [intervalo, establecerIntervalo] = useState<IntervaloFechas>({ start_date: '', end_date: '' });
  const [errores, establecerErrores] = useState<Record<string, string>>({});
  const [fallo, establecerFallo] = useState<string | null>(null);
  const [clavePendiente, establecerClavePendiente] = useState<string | null>(null);
  const [resultado, establecerResultado] = useState<{ key: string; disponible: number; total: number } | null>(null);
  const secuencia = useRef(0);
  const activo = equipo.filter((unidad) => unidad.active);
  const key = JSON.stringify([intervalo.start_date, intervalo.end_date, activo.map((unidad) => unidad.id)]);
  useEffect(() => () => { secuencia.current += 1; }, []);

  function cambiarFecha(nombre: keyof IntervaloFechas, valor: string) {
    secuencia.current += 1;
    establecerIntervalo((anterior) => ({ ...anterior, [nombre]: valor }));
    establecerResultado(null);
    establecerClavePendiente(null);
    establecerErrores({});
    establecerFallo(null);
  }

  async function consultar(evento: FormEvent) {
    evento.preventDefault();
    if (clavePendiente === key) return;
    const validacion = erroresIntervaloFechas(intervalo, true);
    establecerErrores(validacion);
    establecerFallo(null);
    if (Object.keys(validacion).length) return;
    const version = ++secuencia.current;
    establecerClavePendiente(key);
    establecerResultado(null);
    try {
      const resultados = await Promise.all(activo.map((unidad) => api.obtenerDisponibilidadEquipo(unidad.id, intervalo)));
      if (secuencia.current === version) establecerResultado({ key, disponible: resultados.filter((elementoLista) => elementoLista.available).length, total: activo.length });
    } catch (error) {
      if (secuencia.current === version) establecerFallo(error instanceof Error ? error.message : 'No se pudo consultar la disponibilidad.');
    } finally {
      if (secuencia.current === version) establecerClavePendiente(null);
    }
  }

  return <section className="panel stack" aria-labelledby="admin-availability-title">
    <h2 id="admin-availability-title">Disponibilidad por fechas</h2>
    <p className="text-muted">Selecciona el intervalo para consultar las unidades activas. El día de devolución queda excluido.</p>
    <form className="stack" noValidate onSubmit={(evento) => { void consultar(evento); }}>
      <CamposIntervaloFechas valor={intervalo} onChange={cambiarFecha} errores={errores} />
      {Object.keys(errores).length > 0 && <Aviso tono="error" errores={errores}>Revisa las fechas indicadas.</Aviso>}
      <div><button className="button button-secondary" type="submit" disabled={clavePendiente === key}>{clavePendiente === key ? 'Consultando disponibilidad…' : 'Consultar disponibilidad'}</button></div>
    </form>
    {fallo && <Aviso tono="error">{fallo} Vuelve a consultar para reintentar.</Aviso>}
    {resultado?.key === key && <div role="status"><strong>{resultado.disponible} de {resultado.total} equipos activos disponibles</strong><p>Del {formatearFecha(intervalo.start_date)} al {formatearFecha(intervalo.end_date)} (fin excluido). Consulta orientativa; al confirmar se vuelve a comprobar.</p></div>}
  </section>;
}
