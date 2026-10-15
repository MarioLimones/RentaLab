import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { api, type IntervaloFechas } from '../api/cliente';
import { formatearFecha } from '../utilidades/fechas';

interface ResultadoReservas {
  key: string;
  contexto: string;
  reservas: IntervaloFechas[] | null;
  cargando: boolean;
  error: string | null;
}

export function ReservasCatalogo({ id, nombre, cantidad, hoy }: {
  id: number; nombre: string; cantidad: number; hoy: string;
}) {
  const idPanel = useId();
  const activador = useRef<HTMLButtonElement>(null);
  const [abierto, establecerAbierto] = useState(false);
  const [revision, establecerRevision] = useState(0);
  const [resultado, establecerResultado] = useState<ResultadoReservas>({ key: '', contexto: '', reservas: null, cargando: true, error: null });
  const contexto = `${id}:${cantidad}:${hoy}`;
  const key = `${contexto}:${revision}`;
  const actual = resultado.key === key;
  const cargando = !actual || resultado.cargando;
  const cantidadMostrada = resultado.contexto === contexto && resultado.reservas ? resultado.reservas.length : cantidad;

  useEffect(() => {
    if (!abierto) return;
    const controlador = new AbortController();
    let actual = true;
    void Promise.resolve().then(async () => {
      if (!actual) return;
      establecerResultado((anterior) => ({ key, contexto, reservas: anterior.contexto === contexto ? anterior.reservas : null, cargando: true, error: null }));
      const datos = await api.obtenerFechasReservaPublica(id, controlador.signal);
      if (actual) establecerResultado({ key, contexto, reservas: datos.reservations, cargando: false, error: null });
    }).catch((fallo: unknown) => {
      if (actual) establecerResultado((anterior) => ({ ...anterior, key, contexto, cargando: false, error: fallo instanceof Error ? fallo.message : 'No se pudieron cargar las fechas.' }));
    });
    return () => { actual = false; controlador.abort(); };
  }, [abierto, id, contexto, key]);

  function cerrarConEscape(evento: KeyboardEvent<HTMLElement>) {
    if (abierto && evento.key === 'Escape') {
      evento.preventDefault();
      establecerAbierto(false);
      activador.current?.focus();
    }
  }

  return <>
    <button ref={activador} type="button" className="catalogue-reservation-count" aria-expanded={abierto} aria-controls={abierto ? idPanel : undefined} aria-label={`${abierto ? 'Ocultar' : 'Ver'} fechas de ${cantidadMostrada} ${cantidadMostrada === 1 ? 'reserva' : 'reservas'} de ${nombre}`} onKeyDown={cerrarConEscape} onClick={() => {
      if (!abierto) establecerRevision((valor) => valor + 1);
      establecerAbierto(!abierto);
    }}>
      <strong>{cantidadMostrada} {cantidadMostrada === 1 ? 'reserva' : 'reservas'}</strong>
      <span>En curso y próximas</span>
    </button>
    {abierto && <section id={idPanel} className="catalogue-reservation-dates" aria-label={`Fechas de las reservas de ${nombre}`} aria-busy={cargando} onKeyDown={cerrarConEscape}>
      <h4>Fechas de las reservas</h4>
      {cargando ? <p role="status">Cargando fechas…</p> : resultado.error ? <>
        <p role="alert">{resultado.error}</p>
        <button type="button" className="button button-secondary" onClick={() => { establecerRevision((valor) => valor + 1); activador.current?.focus(); }}>Reintentar fechas</button>
      </> : !resultado.reservas?.length ? <p role="status">No hay reservas en curso ni próximas.</p> : <>
        <ol aria-label={`Fechas reservadas de ${nombre}`}>
          {resultado.reservas.map((reserva, indice) => <li key={`${reserva.start_date}:${reserva.end_date}:${indice}`}>
            <span>Recogida <time dateTime={reserva.start_date}>{formatearFecha(reserva.start_date)}</time></span>
            <span>Devolución <time dateTime={reserva.end_date}>{formatearFecha(reserva.end_date)}</time></span>
          </li>)}
        </ol>
        <p className="catalogue-reservation-note">El día de devolución no se incluye en el alquiler.</p>
      </>}
    </section>}
  </>;
}
