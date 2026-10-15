import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api, ErrorApi, type ReservaCliente, type IntervaloFechas, type DisponibilidadPublica, type EquipoPublico } from '../api/cliente';
import { useAutenticacion } from '../autenticacion/contexto';
import { Aviso, EtiquetaEstado } from '../componentes/interfaz';
import { formatearFecha } from '../utilidades/fechas';
import { completarIntervaloFechas, erroresIntervaloFechas, busquedaIntervalo, hoyEnMadrid } from './intervaloFechas';
import { ImagenProducto } from './ImagenProducto';
import { BotonGuardarProducto } from './BotonGuardarProducto';
import { CalendarioDisponibilidad } from './CalendarioDisponibilidad';
import { useCalendarioDisponibilidad } from './useCalendarioDisponibilidad';
import { regresoCatalogoProducto } from './navegacionCatalogo';
import { nuevoIntentoReserva, leerIntentoReserva, ambitoReserva, guardarIntentoReserva, type IntentoReserva } from './intentoReserva';
import './catalogo.css';

interface EstadoDisponibilidad {
  key: string;
  datos: DisponibilidadPublica | null;
  cargando: boolean;
  error: string | null;
}

function Producto({ idEquipo }: { idEquipo: number }) {
  const [busqueda, establecerBusqueda] = useSearchParams();
  const ubicacion = useLocation();
  const navegar = useNavigate();
  const { sesion, comprobando } = useAutenticacion();
  const [equipo, establecerEquipo] = useState<EquipoPublico | null>(null);
  const [errorCarga, establecerErrorCarga] = useState<string | null>(null);
  const [reintentoEquipos, establecerReintentoEquipos] = useState(0);
  const [disponibilidad, establecerDisponibilidad] = useState<EstadoDisponibilidad>({ key: '', datos: null, cargando: false, error: null });
  const [errores, establecerErrores] = useState<Record<string, string>>({});
  const [errorEnvio, establecerErrorEnvio] = useState<string | null>(null);
  const [pendiente, establecerPendiente] = useState(false);
  const [creado, establecerCreado] = useState<ReservaCliente | null>(null);
  const encabezadoConfirmacion = useRef<HTMLHeadingElement>(null);
  const envioEnCurso = useRef(false);
  const [reintentoDisponibilidad, establecerReintentoDisponibilidad] = useState(0);
  const intervalo = { start_date: busqueda.get('start_date') ?? '', end_date: busqueda.get('end_date') ?? '' };
  const idCliente = sesion?.role === 'customer' ? sesion.user?.id ?? null : null;
  const ambitoOperacion = ambitoReserva(idCliente, { equipment_id: idEquipo, ...intervalo });
  const [operacion, establecerOperacion] = useState<{ ambito: string | null; intento: IntentoReserva | null }>(() => ({ ambito: ambitoOperacion, intento: leerIntentoReserva(ambitoOperacion) }));
  if (operacion.ambito !== ambitoOperacion) {
    establecerOperacion({ ambito: ambitoOperacion, intento: leerIntentoReserva(ambitoOperacion) });
    establecerCreado(null);
    establecerErrorEnvio(null);
  }
  const intento = operacion.ambito === ambitoOperacion ? operacion.intento : null;
  const incierto = intento?.phase === 'uncertain';
  const intentoCompletado = intento?.phase === 'complete' ? intento : null;
  const mensajeIncertidumbre = 'No hemos podido comprobar si se confirmó. Consulta Mis reservas o vuelve a confirmar de forma segura.';
  const regresoCatalogo = regresoCatalogoProducto(ubicacion.state, busqueda.get('catalogue'), `/catalogo${busquedaIntervalo(intervalo)}`);
  const intervaloValido = completarIntervaloFechas(intervalo);
  const claveIntervalo = `${idEquipo}:${intervalo.start_date}:${intervalo.end_date}`;
  const disponibilidadActual = disponibilidad.key === claveIntervalo ? disponibilidad : null;
  const calendario = useCalendarioDisponibilidad(idEquipo, intervalo.start_date, reintentoDisponibilidad, true);
  const erroresIntervalo = erroresIntervaloFechas(intervalo);
  if (intervalo.start_date && intervalo.start_date < hoyEnMadrid()) erroresIntervalo.start_date = 'Elige hoy o una fecha posterior para reservar.';
  const erroresVisibles = { ...erroresIntervalo, ...errores };
  if (intervalo.start_date && !intervalo.end_date && !erroresIntervalo.start_date && !errores.end_date) delete erroresVisibles.end_date;
  const intervaloCalendarioNoDisponible = calendario.datos?.unavailable_end_dates?.includes(intervalo.end_date) === true;
  const disponibilidadComprobada = intervaloValido && disponibilidadActual?.datos?.available === true && !calendario.cargando
    && calendario.datos?.can_book === true && !intervaloCalendarioNoDisponible && Object.keys(erroresVisibles).length === 0;
  const cargandoDisponibilidad = intervaloValido && (!disponibilidadActual || disponibilidadActual.cargando || calendario.cargando);

  useEffect(() => { if (creado) encabezadoConfirmacion.current?.focus(); }, [creado]);

  useEffect(() => {
    const controlador = new AbortController();
    let actual = true;
    void api.obtenerEquipoPublico(idEquipo, controlador.signal).then((resultado) => {
      if (actual) { establecerEquipo(resultado); establecerErrorCarga(null); }
    }, (fallo: unknown) => {
      if (actual) establecerErrorCarga(fallo instanceof ErrorApi && fallo.estado === 404 ? 'Este equipo no está disponible en el catálogo.' : fallo instanceof Error ? fallo.message : 'No se pudo cargar el equipo.');
    });
    return () => { actual = false; controlador.abort(); };
  }, [idEquipo, reintentoEquipos]);

  useEffect(() => {
    if (!equipo || !intervaloValido) return;
    const controlador = new AbortController();
    let actual = true;
    const fechas = { start_date: intervalo.start_date, end_date: intervalo.end_date };
    void Promise.resolve().then(async () => {
      if (!actual) return;
      establecerDisponibilidad({ key: claveIntervalo, datos: null, cargando: true, error: null });
      const resultado = await api.obtenerDisponibilidadPublica(idEquipo, fechas, controlador.signal);
      if (actual) establecerDisponibilidad({ key: claveIntervalo, datos: resultado, cargando: false, error: null });
    }).catch((fallo: unknown) => {
      if (actual) establecerDisponibilidad({ key: claveIntervalo, datos: null, cargando: false, error: fallo instanceof Error ? fallo.message : 'No se pudo consultar la disponibilidad.' });
    });
    return () => { actual = false; controlador.abort(); };
  }, [equipo, idEquipo, intervalo.start_date, intervalo.end_date, claveIntervalo, intervaloValido, reintentoDisponibilidad]);

  function cambiarFechas(valor: IntervaloFechas) {
    establecerOperacion({ ambito: null, intento: null });
    establecerErrores({});
    establecerErrorEnvio(null);
    establecerCreado(null);
    establecerBusqueda((anterior) => {
      const siguiente = new URLSearchParams(anterior);
      for (const nombre of ['start_date', 'end_date'] as const) {
        if (valor[nombre]) siguiente.set(nombre, valor[nombre]); else siguiente.delete(nombre);
      }
      return siguiente;
    }, { replace: true, state: ubicacion.state });
  }

  function prepararOtraReserva() {
    if (!ambitoOperacion) return;
    const siguiente = nuevoIntentoReserva(ambitoOperacion);
    guardarIntentoReserva(siguiente);
    establecerOperacion({ ambito: ambitoOperacion, intento: siguiente });
    establecerCreado(null);
    establecerErrores({});
    establecerErrorEnvio(null);
    establecerReintentoDisponibilidad((valor) => valor + 1);
  }

  async function reservar() {
    if (envioEnCurso.current) return;
    const validacion = incierto ? {} : erroresIntervaloFechas(intervalo, true);
    if (!incierto && completarIntervaloFechas(intervalo) && intervalo.start_date < hoyEnMadrid()) validacion.start_date = 'Elige hoy o una fecha posterior para reservar.';
    establecerErrores(validacion);
    establecerErrorEnvio(null);
    if (Object.keys(validacion).length > 0 || (!disponibilidadComprobada && !incierto) || comprobando) return;
    if (!sesion) {
      const consultaDestino = new URLSearchParams(busquedaIntervalo(intervalo));
      if (ubicacion.state || busqueda.has('catalogue')) consultaDestino.set('catalogue', regresoCatalogo.path);
      const destino = `/equipos/${idEquipo}${consultaDestino.size ? `?${consultaDestino}` : ''}`;
      void navegar(`/acceso?next=${encodeURIComponent(destino)}`);
      return;
    }
    if (sesion.role !== 'customer' || !ambitoOperacion) return;
    const intentoActivo = intento ?? nuevoIntentoReserva(ambitoOperacion);
    const enviando: IntentoReserva = { ...intentoActivo, phase: 'uncertain' };
    guardarIntentoReserva(enviando);
    establecerOperacion({ ambito: ambitoOperacion, intento: enviando });
    envioEnCurso.current = true;
    establecerPendiente(true);
    try {
      const reserva = await api.crearMiReserva({ equipment_id: idEquipo, start_date: intervalo.start_date, end_date: intervalo.end_date }, enviando.key);
      const completado: IntentoReserva = { ...enviando, phase: 'complete', reservationIds: [reserva.id] };
      guardarIntentoReserva(completado);
      establecerOperacion({ ambito: ambitoOperacion, intento: completado });
      establecerCreado(reserva);
      establecerReintentoDisponibilidad((valor) => valor + 1);
    } catch (fallo) {
      const resultadoDesconocido = !(fallo instanceof ErrorApi) || fallo.estado === 0 || fallo.estado === 401 || fallo.estado >= 500 || (fallo.estado >= 200 && fallo.estado < 300);
      if (!resultadoDesconocido) {
        const preparado: IntentoReserva = { ...enviando, phase: 'ready' };
        guardarIntentoReserva(preparado);
        establecerOperacion({ ambito: ambitoOperacion, intento: preparado });
      }
      if (fallo instanceof ErrorApi && fallo.estado === 409) {
        establecerDisponibilidad({ key: claveIntervalo, datos: null, cargando: false, error: null });
        establecerErrorEnvio('La disponibilidad ha cambiado y estas fechas ya no se pueden confirmar. Selecciona otro periodo o consulta otro equipo.');
        establecerReintentoDisponibilidad((valor) => valor + 1);
      } else if (fallo instanceof ErrorApi && fallo.estado === 503) {
        establecerErrorEnvio(`El sistema está ocupado temporalmente. ${mensajeIncertidumbre}`);
      } else if (fallo instanceof ErrorApi && fallo.estado === 401) {
        establecerErrorEnvio('Tu sesión ha caducado. Accede de nuevo para confirmar; tus fechas se conservan.');
      } else if (fallo instanceof ErrorApi && fallo.estado === 403) {
        establecerErrorEnvio('Tu cuenta no tiene permiso para crear esta reserva.');
      } else if (fallo instanceof ErrorApi && fallo.estado === 404) {
        establecerErrorEnvio('Este equipo ya no está disponible en el catálogo. Vuelve al catálogo para elegir otro.');
        establecerDisponibilidad({ key: claveIntervalo, datos: null, cargando: false, error: null });
      } else {
        establecerErrores(fallo instanceof ErrorApi ? fallo.campos : {});
        establecerErrorEnvio(resultadoDesconocido ? mensajeIncertidumbre : fallo instanceof Error ? fallo.message : 'No se pudo confirmar la reserva.');
      }
    } finally { envioEnCurso.current = false; establecerPendiente(false); }
  }

  const rutaCatalogo = regresoCatalogo.path;
  if (errorCarga && !incierto && !intentoCompletado) return <><Link className="back-link" to={rutaCatalogo} state={{ catalogueRestore: regresoCatalogo }}>Volver al catálogo</Link><h1>Equipo no disponible</h1><Aviso tono="error">{errorCarga}</Aviso><button type="button" className="button button-secondary" onClick={() => establecerReintentoEquipos((valor) => valor + 1)}>Volver a cargar</button></>;
  if (errorCarga && (incierto || intentoCompletado)) return <>
    <Link className="back-link" to={rutaCatalogo} state={{ catalogueRestore: regresoCatalogo }}>Volver al catálogo</Link><h1>Tu reserva</h1>
    {intentoCompletado ? <><Aviso>Ya registraste una reserva con estas fechas.</Aviso><Link className="button" to={`/mis-reservas/${intentoCompletado.reservationIds[0]}`}>Ver mi reserva</Link></> : <><Aviso tono="warning">{mensajeIncertidumbre}</Aviso><Link className="button button-secondary" to="/mis-reservas">Consultar Mis reservas</Link><button type="button" className="button" disabled={pendiente} onClick={() => { void reservar(); }}>{pendiente ? 'Confirmando reserva…' : 'Volver a confirmar de forma segura'}</button>{errorEnvio && <Aviso tono="error">{errorEnvio}</Aviso>}</>}
  </>;
  if (!equipo) return <p role="status" className="catalogue-loading">Cargando equipo…</p>;

  return <>
    <Link className="back-link" to={rutaCatalogo} state={{ catalogueRestore: regresoCatalogo }}>Volver al catálogo</Link>
    <div className="product-layout">
      <div className="product-overview">
        <header className="product-heading"><p className="catalogue-category">{equipo.category}</p><h1>{equipo.name}</h1><BotonGuardarProducto id={equipo.id} nombre={equipo.name} /></header>
        <ImagenProducto equipo={equipo} className="product-image" inmediato />
        <section className="product-description" aria-labelledby="product-description-title"><h2 id="product-description-title">Sobre este equipo</h2><p>{equipo.public_description || 'Consulta sus características y elige las fechas de tu proyecto.'}</p></section>
        <section className="product-specifications" aria-labelledby="product-specifications-title"><h2 id="product-specifications-title">Características técnicas</h2>{Object.keys(equipo.technical_specs).length ? <dl>{Object.entries(equipo.technical_specs).map(([etiqueta, valor]) => <div key={etiqueta}><dt>{etiqueta}</dt><dd>{valor}</dd></div>)}</dl> : <p className="text-muted">Este equipo aún no tiene características publicadas.</p>}</section>
      </div>
      <aside className="product-booking" aria-labelledby="product-booking-title">
        <h2 id="product-booking-title">Reserva tus fechas</h2>
        <p className="product-booking-intro">Consulta los días disponibles y elige tu recogida y devolución en el calendario.</p>
        <CalendarioDisponibilidad calendario={calendario} {...(!creado && !intentoCompletado ? { intervalo, onChange: cambiarFechas, deshabilitado: pendiente, errores: erroresVisibles } : {})} />
        {creado ? <section className="product-confirmation" aria-label="Resultado de tu reserva"><Aviso tono={creado.status === 'confirmed' ? 'success' : 'info'}>{creado.status === 'confirmed' ? 'Tu reserva se ha confirmado.' : 'Esta reserva está cancelada. Puedes consultar su historial.'}</Aviso><h3 ref={encabezadoConfirmacion} tabIndex={-1}>Reserva #{creado.id}</h3><EtiquetaEstado clase={creado.status} /><p>{formatearFecha(creado.start_date)} al {formatearFecha(creado.end_date)}<br /><span className="text-muted">Día de devolución no incluido.</span></p><Link className="button" to={`/mis-reservas/${creado.id}`}>Ver mi reserva</Link><button type="button" className="button button-secondary" onClick={prepararOtraReserva}>Preparar otra reserva</button><Link className="product-secondary-link" to={rutaCatalogo} state={{ catalogueRestore: regresoCatalogo }}>Seguir explorando</Link></section> : intentoCompletado ? <section className="product-confirmation" aria-label="Reserva registrada"><Aviso>Ya registraste una reserva con estas fechas. Consulta su estado antes de preparar otra.</Aviso><Link className="button" to={`/mis-reservas/${intentoCompletado.reservationIds[0]}`}>Ver mi reserva</Link><button type="button" className="button button-secondary" onClick={prepararOtraReserva}>Preparar otra reserva</button></section> : <>
          {Object.keys(erroresVisibles).length > 0 && <Aviso tono="error" errores={erroresVisibles}>Revisa las fechas de la reserva.</Aviso>}
          {intervaloValido && <div className="product-availability" aria-live="polite">
            {cargandoDisponibilidad ? <p role="status">Comprobando tus fechas…</p> : disponibilidadActual?.error ? <><Aviso tono="error">{disponibilidadActual.error}</Aviso><button type="button" className="button button-secondary" onClick={() => establecerReintentoDisponibilidad((valor) => valor + 1)}>Reintentar disponibilidad</button></> : calendario.datos?.can_book === false ? <p className="catalogue-availability is-unavailable">El equipo no admite nuevas reservas en este momento. Consulta otro equipo.</p> : disponibilidadActual?.datos?.available === true && calendario.datos && !intervaloCalendarioNoDisponible ? <p className="catalogue-availability is-available">Disponible del {formatearFecha(intervalo.start_date)} al {formatearFecha(intervalo.end_date)}.</p> : disponibilidadActual?.datos?.available === false || intervaloCalendarioNoDisponible ? <p className="catalogue-availability is-unavailable">{calendario.datos?.can_book === true ? 'No hay disponibilidad para todo este periodo. Selecciona otras fechas o consulta otro equipo.' : 'No se puede reservar este periodo. Consulta otras fechas o vuelve al catálogo para elegir otro equipo.'}</p> : null}
          </div>}
          {errorEnvio && <Aviso tono="error">{errorEnvio}</Aviso>}
          {incierto && !pendiente && !errorEnvio && <Aviso tono="warning">{mensajeIncertidumbre}</Aviso>}
          {incierto && <Link className="product-secondary-link" to="/mis-reservas">Consultar Mis reservas</Link>}
          {sesion?.role === 'admin' ? <div className="product-admin-action"><p>Gestiona las reservas desde tu panel de administración.</p><Link className="button" to="/admin">Ir al panel</Link></div> : comprobando ? <p role="status">Comprobando tu cuenta…</p> : <>
            <button type="button" className="button product-reserve-button" disabled={(!disponibilidadComprobada && !incierto) || pendiente} onClick={() => { void reservar(); }}>{pendiente ? 'Confirmando reserva…' : incierto ? 'Volver a confirmar de forma segura' : sesion ? 'Confirmar reserva' : 'Acceder para reservar'}</button>
            <p className="product-confirmation-note">{sesion ? 'Al confirmar se comprobará de nuevo la disponibilidad.' : 'Conservaremos el equipo y tus fechas al acceder. Después podrás confirmar la reserva.'}</p>
          </>}
        </>}
      </aside>
    </div>
  </>;
}

export function PaginaProducto() {
  const { id } = useParams();
  const idEquipo = Number(id);
  if (!Number.isSafeInteger(idEquipo) || idEquipo <= 0) return <><h1>Equipo no encontrado</h1><Aviso tono="error">El equipo solicitado no existe.</Aviso><Link to="/catalogo">Volver al catálogo</Link></>;
  return <Producto key={idEquipo} idEquipo={idEquipo} />;
}
