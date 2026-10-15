import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, ErrorApi, type ReservaCliente, type IntervaloFechas, type DisponibilidadPublica, type EquipoPublico } from '../api/cliente';
import { useAutenticacion } from '../autenticacion/contexto';
import { EstadoVacio, Aviso, CabeceraPagina } from '../componentes/interfaz';
import { formatearFecha } from '../utilidades/fechas';
import { CalendarioDisponibilidad } from './CalendarioDisponibilidad';
import { completarIntervaloFechas, erroresIntervaloFechas, busquedaIntervalo, hoyEnMadrid } from './intervaloFechas';
import { ImagenProducto } from './ImagenProducto';
import { useProductosGuardados } from './contextoProductosGuardados';
import { useCalendarioDisponibilidad } from './useCalendarioDisponibilidad';
import { useCalendarioDisponibilidadCompartido } from './useCalendarioDisponibilidadCompartido';
import { ambitoReservaConjunta, nuevoIntentoReserva, leerSeleccionReservasConjuntas, leerIntentoReserva, guardarIntentoReserva, type IntentoReserva } from './intentoReserva';
import './catalogo.css';
import './productos-guardados.css';

interface ResultadoProducto { equipo: EquipoPublico | null; error: string | null; }

function CalendarioProducto({ id, fechaSeleccionada, revision }: { id: number; fechaSeleccionada: string; revision: number }) {
  const calendario = useCalendarioDisponibilidad(id, fechaSeleccionada, revision);
  return <CalendarioDisponibilidad calendario={calendario} />;
}

export default function PaginaProductosGuardados() {
  const guardado = useProductosGuardados();
  const { sesion } = useAutenticacion();
  const idCliente = sesion?.role === 'customer' ? sesion.user?.id ?? null : null;
  const [busqueda, establecerBusqueda] = useSearchParams();
  const [excluidos, establecerExcluidos] = useState<number[]>([]);
  const [idsRecuperacion, establecerIdsRecuperacion] = useState<number[] | null>(null);
  const [cuentaSeleccion, establecerCuentaSeleccion] = useState(idCliente);
  const [seleccionRestaurada, establecerSeleccionRestaurada] = useState(false);
  const [revision, establecerRevision] = useState(0);
  const [productos, establecerProductos] = useState({ key: '', elementos: {} as Record<number, ResultadoProducto>, cargando: true });
  const [disponibilidad, establecerDisponibilidad] = useState({ key: '', elementos: {} as Record<number, DisponibilidadPublica>, fallos: {} as Record<number, string>, error: null as string | null, cargando: false });
  const [errores, establecerErrores] = useState<Record<string, string>>({});
  const [errorEnvio, establecerErrorEnvio] = useState<string | null>(null);
  const [errorAccion, establecerErrorAccion] = useState<string | null>(null);
  const [pendiente, establecerPendiente] = useState(false);
  const [expandido, establecerExpandido] = useState<number[]>([]);
  const [creado, establecerCreado] = useState<{ reservas: ReservaCliente[]; idsEquipos: number[]; nombres: string[] } | null>(null);
  const envio = useRef(false);
  const vigente = useRef(false);
  const confirmacion = useRef<HTMLHeadingElement>(null);
  const [hoy, establecerHoy] = useState(hoyEnMadrid);
  const intervalo = { start_date: busqueda.get('start_date') ?? '', end_date: busqueda.get('end_date') ?? '' };
  if (cuentaSeleccion !== idCliente) {
    establecerCuentaSeleccion(idCliente);
    establecerSeleccionRestaurada(false);
    establecerExcluidos([]);
    establecerIdsRecuperacion(null);
  } else if (!seleccionRestaurada && idCliente !== null && !guardado.cargando && !guardado.error) {
    const seleccionAnterior = leerSeleccionReservasConjuntas(idCliente, intervalo, guardado.ids);
    if (seleccionAnterior) {
      establecerExcluidos(guardado.ids.filter((id) => !seleccionAnterior.includes(id)));
      if (seleccionAnterior.some((id) => !guardado.ids.includes(id))) establecerIdsRecuperacion(seleccionAnterior);
    }
    establecerSeleccionRestaurada(true);
  }
  const intervaloValido = completarIntervaloFechas(intervalo) && intervalo.start_date >= hoy;
  const claveIds = guardado.ids.join(',');
  const claveProductos = `${claveIds}:${revision}`;
  const productosPreparados = productos.key === claveProductos && !productos.cargando;
  const seleccionado = idsRecuperacion ?? guardado.ids.filter((id) => !excluidos.includes(id));
  const ambitoOperacion = ambitoReservaConjunta(idCliente, seleccionado, intervalo);
  const [operacion, establecerOperacion] = useState<{ ambito: string | null; intento: IntentoReserva | null }>(() => ({ ambito: ambitoOperacion, intento: leerIntentoReserva(ambitoOperacion) }));
  if (operacion.ambito !== ambitoOperacion) {
    establecerOperacion({ ambito: ambitoOperacion, intento: leerIntentoReserva(ambitoOperacion) });
    establecerCreado(null);
    establecerErrorEnvio(null);
  }
  const intento = operacion.ambito === ambitoOperacion ? operacion.intento : null;
  const incierto = intento?.phase === 'uncertain';
  const intentoCompletado = intento?.phase === 'complete' ? intento : null;
  const mensajeIncertidumbre = 'No hemos podido comprobar si se confirmó la reserva conjunta. Consulta Mis reservas o vuelve a confirmar de forma segura.';
  const seleccionConocida = productosPreparados ? seleccionado.filter((id) => !!productos.elementos[id]?.equipo) : [];
  const calendario = useCalendarioDisponibilidadCompartido(seleccionConocida, intervalo.start_date, revision);
  const claveDisponibilidad = `${claveProductos}:${intervalo.start_date}:${intervalo.end_date}:${hoy}`;
  const disponibilidadActual = disponibilidad.key === claveDisponibilidad ? disponibilidad : null;
  const errorDisponibilidadSeleccionada = seleccionado.some((id) => !!disponibilidadActual?.fallos[id]);
  const erroresFechas = erroresIntervaloFechas(intervalo);
  if (intervalo.start_date && intervalo.start_date < hoy) erroresFechas.start_date = 'Elige hoy o una fecha posterior para reservar.';
  if (intervalo.start_date && !intervalo.end_date && !errores.end_date) delete erroresFechas.end_date;
  const erroresVisibles = { ...erroresFechas, ...errores };
  const todosDisponibles = intervaloValido && seleccionado.length > 0 && seleccionado.length <= 50 && productosPreparados
    && seleccionado.every((id) => !!productos.elementos[id]?.equipo && disponibilidadActual?.elementos[id]?.available === true)
    && !disponibilidadActual?.cargando && !disponibilidadActual?.error && !errorDisponibilidadSeleccionada && !calendario.cargando && !calendario.error
    && calendario.datos?.can_book === true && !calendario.datos.unavailable_end_dates?.includes(intervalo.end_date)
    && !guardado.cargando && !guardado.error && !guardado.pendiente && Object.keys(erroresVisibles).length === 0;

  useEffect(() => { vigente.current = true; return () => { vigente.current = false; }; }, []);
  useEffect(() => { if (creado && productosPreparados) confirmacion.current?.focus(); }, [creado, productosPreparados]);
  useEffect(() => {
    const actualizar = () => establecerHoy(hoyEnMadrid());
    const temporizador = window.setInterval(actualizar, 60_000);
    window.addEventListener('focus', actualizar);
    return () => { window.clearInterval(temporizador); window.removeEventListener('focus', actualizar); };
  }, []);

  useEffect(() => {
    if (guardado.cargando || guardado.error) return;
    const controlador = new AbortController();
    let activo = true;
    const ids = claveIds ? claveIds.split(',').map(Number) : [];
    void Promise.resolve().then(async () => {
      if (!activo) return;
      establecerProductos((anterior) => ({ ...anterior, cargando: true }));
      const entradas = await Promise.all(ids.map(async (id): Promise<[number, ResultadoProducto]> => {
        try { return [id, { equipo: await api.obtenerEquipoPublico(id, controlador.signal), error: null }]; }
        catch (fallo) {
          if (fallo instanceof ErrorApi && fallo.estado === 404) return [id, { equipo: null, error: null }];
          if (controlador.signal.aborted) throw fallo;
          return [id, { equipo: null, error: fallo instanceof Error ? fallo.message : 'No se pudo cargar este equipo.' }];
        }
      }));
      if (activo) establecerProductos({ key: claveProductos, elementos: Object.fromEntries(entradas), cargando: false });
    }).catch(() => { /* Una navegación cancelada no puede actualizar la lista siguiente. */ });
    return () => { activo = false; controlador.abort(); };
  }, [guardado.cargando, guardado.error, claveIds, claveProductos]);

  useEffect(() => {
    if (!productosPreparados || !intervaloValido) return;
    const controlador = new AbortController();
    let activo = true;
    void Promise.resolve().then(async () => {
      if (!activo) return;
      establecerDisponibilidad({ key: claveDisponibilidad, elementos: {}, fallos: {}, cargando: true, error: null });
      const entradas = await Promise.all(Object.entries(productos.elementos).filter(([, resultado]) => resultado.equipo).map(async ([id]) => {
        try { return { id: Number(id), datos: await api.obtenerDisponibilidadPublica(Number(id), { start_date: intervalo.start_date, end_date: intervalo.end_date }, controlador.signal), error: null }; }
        catch (fallo) { return { id: Number(id), datos: null, error: fallo instanceof Error ? fallo.message : 'No se pudo comprobar la disponibilidad.' }; }
      }));
      if (activo) establecerDisponibilidad({ key: claveDisponibilidad,
        elementos: Object.fromEntries(entradas.flatMap((entradaListado) => entradaListado.datos ? [[entradaListado.id, entradaListado.datos]] : [])),
        fallos: Object.fromEntries(entradas.flatMap((entradaListado) => entradaListado.error ? [[entradaListado.id, entradaListado.error]] : [])), cargando: false, error: null });
    }).catch((fallo: unknown) => {
      if (activo) establecerDisponibilidad({ key: claveDisponibilidad, elementos: {}, fallos: {}, cargando: false, error: fallo instanceof Error ? fallo.message : 'No se pudo comprobar la disponibilidad.' });
    });
    return () => { activo = false; controlador.abort(); };
  }, [productosPreparados, productos.elementos, intervaloValido, intervalo.start_date, intervalo.end_date, claveDisponibilidad]);

  function restablecerConfirmacion() { establecerCreado(null); establecerErrorEnvio(null); establecerErrores({}); }
  function restablecerOperacion() {
    establecerOperacion({ ambito: null, intento: null });
    restablecerConfirmacion();
  }
  function prepararOtraReserva() {
    const ambitoSiguiente = idsRecuperacion ? ambitoReservaConjunta(idCliente, guardado.ids, intervalo) : ambitoOperacion;
    if (!ambitoSiguiente) { establecerIdsRecuperacion(null); establecerExcluidos([]); restablecerConfirmacion(); return; }
    const siguiente = nuevoIntentoReserva(ambitoSiguiente);
    guardarIntentoReserva(siguiente);
    if (idsRecuperacion) { establecerIdsRecuperacion(null); establecerExcluidos([]); }
    establecerOperacion({ ambito: ambitoSiguiente, intento: siguiente });
    restablecerConfirmacion();
    establecerRevision((valor) => valor + 1);
  }
  function cambiarFechas(valor: IntervaloFechas) {
    if (envio.current) return;
    restablecerOperacion();
    establecerBusqueda(new URLSearchParams(busquedaIntervalo(valor).slice(1)), { replace: true });
  }
  function alternar(id: number) {
    if (envio.current) return;
    const siguientesExcluidos = excluidos.includes(id) ? excluidos.filter((elementoLista) => elementoLista !== id) : [...excluidos, id];
    restablecerOperacion();
    establecerExcluidos(siguientesExcluidos);
  }
  async function eliminar(id: number) {
    if (envio.current) return;
    establecerErrorAccion(null);
    try { await guardado.cambio(id, false); restablecerOperacion(); }
    catch (fallo) { if (vigente.current) establecerErrorAccion(fallo instanceof Error ? fallo.message : 'No se pudo quitar el equipo.'); }
  }
  async function reservar() {
    if (envio.current) return;
    const validacion = incierto ? {} : erroresIntervaloFechas(intervalo, true);
    if (!incierto && intervalo.start_date && intervalo.start_date < hoyEnMadrid()) validacion.start_date = 'Elige hoy o una fecha posterior para reservar.';
    establecerErrores(validacion);
    if (Object.keys(validacion).length || (!todosDisponibles && !incierto) || !ambitoOperacion) return;
    const enviando: IntentoReserva = { ...(intento ?? nuevoIntentoReserva(ambitoOperacion)), phase: 'uncertain' };
    guardarIntentoReserva(enviando);
    establecerOperacion({ ambito: ambitoOperacion, intento: enviando });
    envio.current = true; establecerPendiente(true); establecerErrorEnvio(null);
    try {
      const reservas = await api.crearMisReservasConjuntas({ equipment_ids: seleccionado, ...intervalo }, enviando.key);
      const completado: IntentoReserva = { ...enviando, phase: 'complete', reservationIds: reservas.map((reserva) => reserva.id) };
      guardarIntentoReserva(completado);
      if (vigente.current) {
        establecerOperacion({ ambito: ambitoOperacion, intento: completado });
        establecerCreado({ reservas, idsEquipos: seleccionado, nombres: seleccionado.map((id) => productos.elementos[id]?.equipo?.name ?? `Equipo #${id}`) });
        establecerRevision((valor) => valor + 1);
      }
    } catch (fallo) {
      const resultadoDesconocido = !(fallo instanceof ErrorApi) || fallo.estado === 0 || fallo.estado === 401 || fallo.estado >= 500 || (fallo.estado >= 200 && fallo.estado < 300);
      if (!resultadoDesconocido) {
        const preparado: IntentoReserva = { ...enviando, phase: 'ready' };
        guardarIntentoReserva(preparado);
        if (vigente.current) establecerOperacion({ ambito: ambitoOperacion, intento: preparado });
      }
      if (!vigente.current) return;
      if (fallo instanceof ErrorApi && fallo.estado === 409) {
        establecerErrorEnvio('La disponibilidad ha cambiado. No se ha reservado ningún equipo. Estamos comprobando las fechas de nuevo; cambia el periodo o la selección.');
        establecerRevision((valor) => valor + 1);
      } else if (fallo instanceof ErrorApi && fallo.estado === 404) {
        establecerErrorEnvio('Uno de los equipos ya no está disponible. No se ha reservado ningún equipo. Revisa tu lista.');
        guardado.recargar();
        establecerRevision((valor) => valor + 1);
      } else {
        establecerErrores(fallo instanceof ErrorApi ? fallo.campos : {});
        establecerErrorEnvio(fallo instanceof ErrorApi && fallo.estado === 401 ? 'Tu sesión ha caducado. Accede de nuevo para reservar; tu lista y tus fechas se conservan.' : resultadoDesconocido ? mensajeIncertidumbre : fallo instanceof Error ? fallo.message : 'No se pudo confirmar la reserva conjunta.');
      }
    } finally { envio.current = false; if (vigente.current) establecerPendiente(false); }
  }

  return <div className="saved-products-page">
    <CabeceraPagina titulo="Mi lista" descripcion="Guarda el equipo que necesitas, compara las fechas y reserva varios productos a la vez." accion={<Link className="button button-secondary" to={`/catalogo${busquedaIntervalo(intervalo)}`}>Añadir equipos</Link>} />
    {guardado.cargando ? <p role="status">Cargando tu lista…</p> : guardado.error ? <Aviso tono="error">{guardado.error} <button className="button button-secondary" type="button" onClick={guardado.recargar}>Volver a cargar mi lista</button></Aviso> : guardado.ids.length === 0 && !intento ? <EstadoVacio titulo="Tu próximo proyecto empieza aquí" descripcion="Guarda productos desde el catálogo para comparar su disponibilidad y reservarlos juntos." accion={<Link className="button" to="/catalogo">Explorar el catálogo</Link>} /> : <>
      {errorAccion && <Aviso tono="error">{errorAccion}</Aviso>}
      {idsRecuperacion && <Aviso tono="warning">Tu lista ha cambiado desde la reserva anterior. Consulta o recupera esa operación antes de preparar otra.</Aviso>}
      <div className="saved-products-layout">
        <section className="saved-products-selection" aria-labelledby="saved-selection-title" aria-busy={!productosPreparados}>
          <div className="saved-products-selection-heading"><h2 id="saved-selection-title">Tus equipos guardados</h2><p>{idsRecuperacion ? 'Revisando tu reserva anterior' : `${seleccionado.length} de ${guardado.ids.length} seleccionados`}</p></div>
          <div className="saved-products-selection-actions"><button type="button" disabled={pendiente || guardado.pendiente || !!idsRecuperacion || seleccionado.length === guardado.ids.length} onClick={() => { restablecerOperacion(); establecerExcluidos([]); }}>Seleccionar todos</button><button type="button" disabled={pendiente || guardado.pendiente || !!idsRecuperacion || seleccionado.length === 0} onClick={() => { restablecerOperacion(); establecerExcluidos([...guardado.ids]); }}>Deseleccionar todos</button><button type="button" disabled={pendiente || guardado.pendiente} onClick={() => { guardado.recargar(); }}>Actualizar mi lista</button></div>
          {!productosPreparados ? <p role="status">Cargando los equipos guardados…</p> : <ul className="saved-products-list">{guardado.ids.map((id) => {
            const resultado = productos.elementos[id];
            const elementoLista = resultado?.equipo;
            const disponible = disponibilidadActual?.elementos[id]?.available;
            const recienReservado = !!creado && creado.reservas[creado.idsEquipos.indexOf(id)]?.status === 'confirmed';
            const intervaloReservado = creado?.reservas[0];
            const nombre = elementoLista?.name ?? `Equipo #${id}`;
            return <li key={id} className="saved-product">
              <div className="saved-product-overview">
                <label className="saved-product-select"><input type="checkbox" checked={seleccionado.includes(id)} disabled={pendiente || guardado.pendiente || !!idsRecuperacion} onChange={() => alternar(id)} aria-label={`Seleccionar ${nombre}`} /><span className="sr-only">Seleccionar {nombre}</span></label>
                {elementoLista && <Link className="saved-product-image" to={`/equipos/${id}${busquedaIntervalo(intervalo)}`} tabIndex={-1} aria-hidden="true"><ImagenProducto equipo={elementoLista} /></Link>}
                <div className="saved-product-info">{elementoLista && <p className="catalogue-category">{elementoLista.category}</p>}<h3>{elementoLista ? <Link to={`/equipos/${id}${busquedaIntervalo(intervalo)}`}>{nombre}</Link> : nombre}</h3>
                  {!elementoLista ? <p className="catalogue-availability is-unavailable">{resultado?.error ?? 'Este equipo ya no está en el catálogo. Puedes quitarlo de tu lista.'}</p> : <p className={`catalogue-availability${recienReservado || disponible === true ? ' is-available' : disponible === false ? ' is-unavailable' : ''}`}>{recienReservado && intervaloReservado ? `Reservado del ${formatearFecha(intervaloReservado.start_date)} al ${formatearFecha(intervaloReservado.end_date)}` : !intervaloValido ? 'Elige fechas para comparar disponibilidad.' : !disponibilidadActual || disponibilidadActual.cargando ? 'Comprobando tus fechas…' : disponibilidadActual.error || disponibilidadActual.fallos[id] ? 'No se pudo comprobar la disponibilidad.' : disponible ? 'Disponible para todo el periodo' : 'No disponible para todo el periodo'}</p>}
                  <div className="saved-product-actions">{elementoLista && <button type="button" aria-expanded={expandido.includes(id)} aria-controls={`saved-calendar-${id}`} aria-label={`${expandido.includes(id) ? 'Ocultar' : 'Ver'} calendario de ${nombre}`} onClick={() => establecerExpandido((anterior) => anterior.includes(id) ? anterior.filter((valor) => valor !== id) : [...anterior, id])}>{expandido.includes(id) ? 'Ocultar calendario' : 'Ver calendario'}<span className="sr-only"> de {nombre}</span></button>}<button type="button" disabled={pendiente || guardado.pendiente || !!idsRecuperacion} onClick={() => { void eliminar(id); }} aria-label={`Quitar ${nombre} de mi lista`}>Quitar</button>{resultado?.error && <button type="button" disabled={pendiente} onClick={() => establecerRevision((valor) => valor + 1)}>Reintentar cargar equipo</button>}</div>
                </div>
              </div>
              {elementoLista && expandido.includes(id) && <div id={`saved-calendar-${id}`} className="saved-product-calendar" role="region" aria-label={`Calendario de ${nombre}`}><CalendarioProducto id={id} fechaSeleccionada={intervalo.start_date} revision={revision} /></div>}
            </li>;
          })}</ul>}
        </section>
        <aside className="saved-products-booking" aria-labelledby="saved-booking-title">
          <h2 id="saved-booking-title">Unas fechas para todos</h2><p className="saved-products-booking-intro">El calendario combina la disponibilidad de los equipos seleccionados. Los días ocupados afectan al menos a uno.</p>
          {seleccionConocida.length > 0 ? <CalendarioDisponibilidad titulo="Disponibilidad conjunta" calendario={calendario} {...(!creado && !intentoCompletado ? { intervalo, onChange: cambiarFechas, deshabilitado: pendiente, errores: erroresVisibles } : {})} /> : <p className="text-muted">Selecciona al menos un equipo del catálogo para consultar el calendario conjunto.</p>}
          {Object.keys(erroresVisibles).length > 0 && <Aviso tono="error" errores={erroresVisibles}>Revisa las fechas del alquiler conjunto.</Aviso>}
          {seleccionado.length > 50 && <Aviso tono="warning">Puedes reservar un máximo de 50 equipos a la vez. Reduce la selección.</Aviso>}
          {!creado && !intentoCompletado && <div className="saved-products-summary" aria-live="polite">
            <strong>{seleccionado.length} {seleccionado.length === 1 ? 'equipo seleccionado' : 'equipos seleccionados'}</strong>
            {seleccionado.length === 0 ? <p>Selecciona los equipos que quieres reservar.</p> : seleccionConocida.length !== seleccionado.length && productosPreparados ? <p>Hay equipos sin ficha disponible. Quítalos de la selección para continuar.</p> : !intervaloValido ? <p>Elige la recogida y la devolución para comprobar si puedes alquilarlos juntos.</p> : !productosPreparados || !disponibilidadActual || disponibilidadActual.cargando || calendario.cargando ? <p role="status">Comprobando la disponibilidad conjunta…</p> : disponibilidadActual.error || errorDisponibilidadSeleccionada || calendario.error ? <><p>No se pudo comprobar todo el periodo.</p><button type="button" className="button button-secondary" disabled={pendiente} onClick={() => establecerRevision((valor) => valor + 1)}>Reintentar disponibilidad</button></> : todosDisponibles ? <p className="catalogue-availability is-available">Todos disponibles del {formatearFecha(intervalo.start_date)} al {formatearFecha(intervalo.end_date)}.</p> : <p className="catalogue-availability is-unavailable">No todos están disponibles para estas fechas. Cambia el periodo o desmarca los equipos que no necesitas.</p>}
          </div>}
          {errorEnvio && <Aviso tono="error">{errorEnvio} <Link to="/mis-reservas">Consultar Mis reservas</Link></Aviso>}
          {incierto && !pendiente && !errorEnvio && <Aviso tono="warning">{mensajeIncertidumbre} <Link to="/mis-reservas">Consultar Mis reservas</Link></Aviso>}
          {creado ? <section className="saved-products-confirmation" aria-label="Resultado de la reserva conjunta"><Aviso tono={creado.reservas.every((reserva) => reserva.status === 'confirmed') ? 'success' : 'info'}>{creado.reservas.every((reserva) => reserva.status === 'confirmed') ? 'Todos los equipos se han reservado.' : 'Esta operación ya estaba registrada. Consulta el estado actual de cada reserva.'}</Aviso><h3 ref={confirmacion} tabIndex={-1}>{creado.reservas.length} {creado.reservas.every((reserva) => reserva.status === 'confirmed') ? creado.reservas.length === 1 ? 'reserva confirmada' : 'reservas confirmadas' : creado.reservas.length === 1 ? 'reserva registrada' : 'reservas registradas'}</h3><p>Del {formatearFecha(creado.reservas[0]!.start_date)} al {formatearFecha(creado.reservas[0]!.end_date)}. Devolución no incluida.</p><ul>{creado.reservas.map((reserva, indice) => <li key={reserva.id}><Link to={`/mis-reservas/${reserva.id}`}>Reserva #{reserva.id} · {creado.nombres[indice]}</Link></li>)}</ul><Link className="button" to="/mis-reservas">Ver mis reservas</Link><button type="button" className="button button-secondary" onClick={prepararOtraReserva}>Preparar otra reserva</button><p className="product-confirmation-note">Tus equipos siguen guardados en Mi lista.</p></section> : intentoCompletado ? <section className="saved-products-confirmation" aria-label="Reserva conjunta registrada"><Aviso>Ya registraste una reserva conjunta con esta selección y estas fechas. Consulta su estado antes de preparar otra.</Aviso><ul>{intentoCompletado.reservationIds.map((id) => <li key={id}><Link to={`/mis-reservas/${id}`}>Ver reserva #{id}</Link></li>)}</ul><button type="button" className="button button-secondary" onClick={prepararOtraReserva}>Preparar otra reserva</button></section> : <><button type="button" className="button saved-products-confirm-button" disabled={(!todosDisponibles && !incierto) || pendiente} onClick={() => { void reservar(); }}>{pendiente ? 'Confirmando todos los equipos…' : incierto ? 'Volver a confirmar de forma segura' : `Reservar ${seleccionado.length || ''} ${seleccionado.length === 1 ? 'equipo' : 'equipos'} a la vez`}</button><p className="product-confirmation-note">Se confirman todos juntos. Si un equipo deja de estar disponible, no se reserva ninguno. El día de devolución no se incluye.</p></>}
        </aside>
      </div>
    </>}
  </div>;
}
