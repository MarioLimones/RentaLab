import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigationType, useSearchParams } from 'react-router-dom';
import { api, type DisponibilidadPublica, type EquipoPublico } from '../api/cliente';
import { EstadoVacio, Campo, Aviso } from '../componentes/interfaz';
import { formatearFecha } from '../utilidades/fechas';
import { SelectorFechasCatalogo } from './SelectorFechasCatalogo';
import { ReservasCatalogo } from './ReservasCatalogo';
import { completarIntervaloFechas, erroresIntervaloFechas, hoyEnMadrid } from './intervaloFechas';
import { rutaProductoCatalogo, destinoDesplazamientoCatalogo, recordarPosicionCatalogo } from './navegacionCatalogo';
import { ImagenProducto } from './ImagenProducto';
import { BotonGuardarProducto } from './BotonGuardarProducto';
import './catalogo.css';

interface ResultadoCatalogo {
  key: string;
  equipo: EquipoPublico[];
  disponibilidad: Record<number, DisponibilidadPublica>;
  cargando: boolean;
  error: string | null;
  intervalo: { start_date: string; end_date: string };
  soloDisponibles: boolean;
}

function filtrosCatalogo(busqueda: URLSearchParams) {
  return {
    q: busqueda.get('q') ?? '', category: busqueda.get('category') ?? '',
    start_date: busqueda.get('start_date') ?? '', end_date: busqueda.get('end_date') ?? '',
    available: busqueda.get('available') === '1' ? '1' : '',
  };
}

export function PaginaCatalogo() {
  const [busqueda, establecerBusqueda] = useSearchParams();
  const ubicacion = useLocation();
  const tipoNavegacion = useNavigationType();
  const ubicacionRestaurada = useRef<string | null>(null);
  const [todosEquipos, establecerTodosEquipos] = useState<EquipoPublico[]>([]);
  const [resultado, establecerResultado] = useState<ResultadoCatalogo>({ key: '', equipo: [], disponibilidad: {}, cargando: true, error: null, intervalo: { start_date: '', end_date: '' }, soloDisponibles: false });
  const [errores, establecerErrores] = useState<Record<string, string>>({});
  const [reintento, establecerReintento] = useState(0);
  const [hoy, establecerHoy] = useState(hoyEnMadrid);
  const claveBusqueda = busqueda.toString();
  const [formulario, establecerFormulario] = useState(() => ({ fuente: claveBusqueda, valores: filtrosCatalogo(busqueda), destinoActual: null as string | null }));
  const [componiendo, establecerComponiendo] = useState(false);
  const regionResultados = useRef<HTMLElement>(null);
  // La búsqueda en directo conserva los demás borradores; la navegación del navegador restaura los filtros aplicados.
  if (formulario.fuente !== claveBusqueda) {
    const busquedaActual = formulario.destinoActual === claveBusqueda;
    establecerFormulario({ fuente: claveBusqueda, valores: busquedaActual ? formulario.valores : filtrosCatalogo(busqueda), destinoActual: null });
    if (!busquedaActual) establecerErrores({});
  }
  const borrador = formulario.valores;
  const intervaloBorrador = { start_date: borrador.start_date, end_date: borrador.end_date };
  const intervaloBorradorValido = completarIntervaloFechas(intervaloBorrador);
  const consulta = busqueda.get('q') ?? '';
  const categoria = busqueda.get('category') ?? '';
  const intervalo = { start_date: busqueda.get('start_date') ?? '', end_date: busqueda.get('end_date') ?? '' };
  const intervaloValido = completarIntervaloFechas(intervalo);
  const soloDisponibles = busqueda.get('available') === '1';
  const key = JSON.stringify([consulta, categoria, intervalo.start_date, intervalo.end_date, soloDisponibles, reintento, hoy]);

  useEffect(() => {
    const actualizarDia = () => establecerHoy(hoyEnMadrid());
    const temporizador = window.setInterval(actualizarDia, 60_000);
    window.addEventListener('focus', actualizarDia);
    return () => { window.clearInterval(temporizador); window.removeEventListener('focus', actualizarDia); };
  }, []);

  useEffect(() => {
    if (componiendo || borrador.q === consulta) return;
    const temporizador = window.setTimeout(() => {
      const siguiente = new URLSearchParams(busqueda);
      if (borrador.q) siguiente.set('q', borrador.q); else siguiente.delete('q');
      establecerFormulario((anterior) => ({ ...anterior, destinoActual: siguiente.toString() }));
      establecerBusqueda(siguiente, { replace: true });
    }, 150);
    return () => window.clearTimeout(temporizador);
  }, [borrador.q, consulta, componiendo, busqueda, establecerBusqueda]);

  useEffect(() => {
    const controlador = new AbortController();
    let actual = true;
    void api.listarEquiposPublicos({}, controlador.signal).then((equipo) => { if (actual) establecerTodosEquipos(equipo); }, () => { /* La petición filtrada posterior ofrece un error del que se puede recuperar. */ });
    return () => { actual = false; controlador.abort(); };
  }, [reintento]);

  useEffect(() => {
    const controlador = new AbortController();
    let actual = true;
    const fechas = { start_date: intervalo.start_date, end_date: intervalo.end_date };
    const manana = new Date(`${hoy}T12:00:00Z`);
    manana.setUTCDate(manana.getUTCDate() + 1);
    const fechasDisponibilidad = intervaloValido ? fechas : { start_date: hoy, end_date: manana.toISOString().slice(0, 10) };
    void Promise.resolve().then(async () => {
      if (!actual) return;
      establecerResultado((anterior) => ({ ...anterior, cargando: true, error: null }));
      const equipo = await api.listarEquiposPublicos({ q: consulta, category: categoria }, controlador.signal);
      const disponibilidad: Record<number, DisponibilidadPublica> = {};
      await Promise.all(equipo.map(async (elementoLista) => { disponibilidad[elementoLista.id] = await api.obtenerDisponibilidadPublica(elementoLista.id, fechasDisponibilidad, controlador.signal); }));
      if (actual) establecerResultado({ key, equipo, disponibilidad, cargando: false, error: null, intervalo: fechas, soloDisponibles });
    }).catch((fallo: unknown) => {
      if (actual) establecerResultado({ key, equipo: [], disponibilidad: {}, cargando: false, error: fallo instanceof Error ? fallo.message : 'No se pudo cargar el catálogo.', intervalo: fechas, soloDisponibles });
    });
    return () => { actual = false; controlador.abort(); };
  }, [consulta, categoria, intervalo.start_date, intervalo.end_date, intervaloValido, soloDisponibles, key, hoy]);

  function conservarAlturaResultados() {
    const region = regionResultados.current;
    if (region) region.style.minHeight = `${region.getBoundingClientRect().height}px`;
  }

  function actualizacion(nombre: keyof typeof borrador, valor: string) {
    conservarAlturaResultados();
    establecerErrores({});
    establecerFormulario((anterior) => ({ ...anterior, valores: {
      ...anterior.valores, [nombre]: valor,
    } }));
  }

  function alternarDisponible(marcado: boolean) {
    conservarAlturaResultados();
    const siguiente = new URLSearchParams(busqueda);
    if (marcado) siguiente.set('available', '1'); else siguiente.delete('available');
    establecerFormulario((anterior) => ({ ...anterior, valores: { ...anterior.valores, available: marcado ? '1' : '' }, destinoActual: siguiente.toString() }));
    establecerBusqueda(siguiente);
  }

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (componiendo) return;
    conservarAlturaResultados();
    const validacion = erroresIntervaloFechas(intervaloBorrador);
    establecerErrores(validacion);
    if (Object.keys(validacion).length > 0) return;
    const siguiente = new URLSearchParams(busqueda);
    for (const [nombre, valor] of Object.entries(borrador)) {
      if (valor) siguiente.set(nombre, valor);
      else siguiente.delete(nombre);
    }
    if (siguiente.toString() === claveBusqueda) establecerReintento((valor) => valor + 1);
    else establecerBusqueda(siguiente);
  }

  function limpiarFiltros() {
    conservarAlturaResultados();
    establecerFormulario({ fuente: claveBusqueda, valores: filtrosCatalogo(new URLSearchParams()), destinoActual: null });
    establecerErrores({});
    if (!claveBusqueda) establecerReintento((valor) => valor + 1);
    else establecerBusqueda({});
  }

  const categorias = [...new Set([...todosEquipos.map((elementoLista) => elementoLista.category), ...(borrador.category ? [borrador.category] : [])])].sort((a, b) => a.localeCompare(b, 'es'));
  const resultadoActual = resultado.key === key;
  const cargando = !resultadoActual || resultado.cargando || borrador.q !== consulta;
  const cargaInicial = !resultado.key && cargando;
  const intervaloMostrado = resultado.key ? resultado.intervalo : intervalo;
  const equipo = resultado.soloDisponibles ? resultado.equipo.filter((elementoLista) => resultado.disponibilidad[elementoLista.id]?.available === true) : resultado.equipo;
  const rutaDelCatalogo = `/catalogo${claveBusqueda ? `?${claveBusqueda}` : ''}`;

  useEffect(() => {
    if (cargando || resultado.error || ubicacionRestaurada.current === ubicacion.key) return;
    const superior = destinoDesplazamientoCatalogo(rutaDelCatalogo, ubicacion.state, tipoNavegacion === 'POP');
    if (superior === null) return;
    const marco = window.requestAnimationFrame(() => {
      window.scrollTo({ top: superior, left: 0, behavior: 'instant' });
      ubicacionRestaurada.current = ubicacion.key;
    });
    return () => window.cancelAnimationFrame(marco);
  }, [cargando, resultado.error, rutaDelCatalogo, ubicacion.key, ubicacion.state, tipoNavegacion]);

  return <>
    <header className="catalogue-intro">
      <div><h1>El equipo para tu próxima idea.</h1><p>Cámaras, sonido e iluminación para tus proyectos. Elige tus fechas y encuentra el equipo que necesitas.</p></div>
      <div className="catalogue-intro-note"><strong>Alquiler por días</strong><span>Consulta las características y reserva desde tu cuenta.</span></div>
    </header>
    <form className="catalogue-filters" onSubmit={enviar} noValidate aria-label="Buscar en el catálogo">
      <div className="catalogue-search-row">
        <Campo nombre="catalogue-search" etiqueta="Buscar equipo"><input id="catalogue-search" type="search" name="q" placeholder="Cámara, micrófono…" maxLength={120} value={borrador.q} onChange={(evento) => actualizacion('q', evento.target.value)} onCompositionStart={() => establecerComponiendo(true)} onCompositionEnd={() => establecerComponiendo(false)} /></Campo>
        <Campo nombre="catalogue-category" etiqueta="Categoría"><select id="catalogue-category" name="category" value={borrador.category} onChange={(evento) => actualizacion('category', evento.target.value)}><option value="">Todas las categorías</option>{categorias.map((elementoLista) => <option key={elementoLista} value={elementoLista}>{elementoLista}</option>)}</select></Campo>
      </div>
      <div className="catalogue-dates-row">
        <SelectorFechasCatalogo valor={intervaloBorrador} onChange={(fechas) => {
          conservarAlturaResultados();
          establecerErrores({});
          establecerFormulario((anterior) => ({ ...anterior, valores: { ...anterior.valores, ...fechas } }));
        }} errores={errores} />
        <div className="catalogue-filter-actions">
          <label className="catalogue-checkbox"><input type="checkbox" checked={borrador.available === '1'} onChange={(evento) => alternarDisponible(evento.target.checked)} />Solo disponibles</label>
          <button type="submit" className="button">Consultar catálogo</button>
        </div>
      </div>
      <p className="catalogue-help">La búsqueda y el filtro Solo disponibles se actualizan automáticamente. Aplica categoría y fechas con Consultar catálogo.</p>
      {!intervaloBorradorValido && <p className="catalogue-help" id="catalogue-date-help">Sin fechas aplicadas, Solo disponibles muestra los equipos disponibles hoy.</p>}
      {Object.keys(errores).length > 0 && <Aviso tono="error" errores={errores}>Revisa las fechas para consultar disponibilidad.</Aviso>}
    </form>
    <section id="catalogue-results" ref={regionResultados} aria-labelledby="catalogue-results-title" aria-busy={cargando}>
      <div className="catalogue-results-header"><h2 id="catalogue-results-title">Explora el catálogo</h2><span className="catalogue-results-status" role="status">{cargando ? 'Actualizando…' : !resultado.error ? `${equipo.length} ${equipo.length === 1 ? 'equipo' : 'equipos'}` : ''}</span></div>
      {completarIntervaloFechas(intervaloMostrado) && <p className="catalogue-range">Disponibilidad del {formatearFecha(intervaloMostrado.start_date)} al {formatearFecha(intervaloMostrado.end_date)}. El día de devolución no se incluye.</p>}
      {cargaInicial ? <p className="catalogue-loading">Cargando equipos{intervaloValido ? ' y disponibilidad' : ''}…</p> : resultado.error ? <div className="notice notice-error" role="alert">{resultado.error} <button type="button" className="button button-secondary" onClick={() => establecerReintento((valor) => valor + 1)}>Volver a cargar</button></div> : equipo.length === 0 ? <EstadoVacio titulo="No encontramos equipos para esta búsqueda" descripcion="Prueba otra palabra, categoría o rango de fechas." accion={<button className="button button-secondary" type="button" onClick={limpiarFiltros}>Ver todo el catálogo</button>} /> : <ul className="catalogue-grid">{equipo.map((elementoLista) => {
        const disponibilidad = resultadoActual ? resultado.disponibilidad[elementoLista.id] : undefined;
        const paraHoy = !completarIntervaloFechas(intervaloMostrado);
        const etiquetaDisponibilidad = disponibilidad?.available === true
          ? paraHoy ? 'Disponible hoy' : 'Disponible para tus fechas'
          : disponibilidad?.available === false ? paraHoy ? 'No disponible hoy' : 'No disponible para tus fechas'
          : 'Consultando disponibilidad…';
        return <li key={elementoLista.id} className="catalogue-card">
          <Link className="catalogue-card-image-link" to={rutaProductoCatalogo(elementoLista.id, intervaloMostrado, rutaDelCatalogo)} state={{ catalogueReturn: rutaDelCatalogo }} onClick={() => recordarPosicionCatalogo(rutaDelCatalogo)} aria-label={`Ver ${elementoLista.name}`}><ImagenProducto equipo={elementoLista} /></Link>
          <div className="catalogue-card-body"><p className="catalogue-category">{elementoLista.category}</p><h3><Link to={rutaProductoCatalogo(elementoLista.id, intervaloMostrado, rutaDelCatalogo)} state={{ catalogueReturn: rutaDelCatalogo }} onClick={() => recordarPosicionCatalogo(rutaDelCatalogo)}>{elementoLista.name}</Link></h3>
            <p className={`catalogue-availability catalogue-card-availability${disponibilidad?.available === true ? ' is-available' : disponibilidad?.available === false ? ' is-unavailable' : ''}`}>
              {disponibilidad?.available != null && <svg aria-hidden="true" viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="10" cy="10" r="7.5" />{disponibilidad.available ? <path d="m6.5 10 2.3 2.3 4.7-4.6" /> : <path d="m7.5 7.5 5 5m0-5-5 5" />}</svg>}
              <span>{etiquetaDisponibilidad}</span>
            </p>
            <div className="catalogue-card-actions">
              <Link className="button button-secondary catalogue-card-action" to={rutaProductoCatalogo(elementoLista.id, intervaloMostrado, rutaDelCatalogo)} state={{ catalogueReturn: rutaDelCatalogo }} onClick={() => recordarPosicionCatalogo(rutaDelCatalogo)}>Ver equipo</Link>
              <ReservasCatalogo id={elementoLista.id} nombre={elementoLista.name} cantidad={elementoLista.active_reservations_count} hoy={hoy} />
            </div>
            <BotonGuardarProducto id={elementoLista.id} nombre={elementoLista.name} />
          </div>
        </li>;
      })}</ul>}
    </section>
  </>;
}
