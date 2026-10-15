import type {
  Equipo, EntradaEquipo, CambiosEquipo, Reserva, EntradaReserva, FiltrosReservas, IntervaloFechas, Disponibilidad, Incidencia, EntradaIncidencia, FiltrosIncidencias, CambioEstadoIncidencia, ActualizacionIncidencia, InformeImportacion, ResultadoFilaImportacion, TotalesImportacion, SesionAutenticacion, EntradaAcceso, EntradaRegistro, Usuario,
  EquipoPublico, FiltrosEquiposPublicos, DisponibilidadPublica, CalendarioDisponibilidadPublica, FechasReservaPublica, ReservaCliente, EntradaReservaCliente, IncidenciaCliente, EntradaIncidenciaCliente, ProductosGuardados, EntradaReservasConjuntasCliente,
} from '../tipos/api';
export type * from '../tipos/api';

export class ErrorApi extends Error {
  constructor(mensaje: string, public readonly estado: number, public readonly campos: Record<string, string> = {}) {
    super(mensaje);
    this.name = 'ApiError';
  }
}

const BASE_API = '/api';
export const URL_EJEMPLO_IMPORTACION = `${BASE_API}/imports/example`;
const RESPUESTA_INVALIDA = 'El servidor devolvió una respuesta no válida.';
let tokenCsrf: string | null = null;
let solicitudCsrf: Promise<string> | null = null;
let versionCsrf = 0;
let versionSesion = 0;
const oyentesSinAutorizacion = new Set<() => void>();

// Los tokens sólo viven en memoria. Una sesión renovada o caducada necesita un token nuevo.
export function limpiarTokenCsrf() {
  tokenCsrf = null;
  solicitudCsrf = null;
  versionCsrf += 1;
}

function invalidarSesion() {
  versionSesion += 1;
  limpiarTokenCsrf();
}

export function suscribirSinAutorizacion(oyente: () => void): () => void {
  oyentesSinAutorizacion.add(oyente);
  return () => { oyentesSinAutorizacion.delete(oyente); };
}

function esRegistro(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor);
}

function esEquipo(valor: unknown): valor is Equipo {
  return esRegistro(valor)
    && typeof valor.id === 'number' && Number.isInteger(valor.id) && valor.id > 0
    && typeof valor.code === 'string'
    && typeof valor.name === 'string'
    && typeof valor.category === 'string'
    && typeof valor.description === 'string'
    && (valor.public_description === undefined || typeof valor.public_description === 'string')
    && (valor.technical_specs === undefined || esMapaTextos(valor.technical_specs))
    && (valor.image_url === undefined || valor.image_url === null || esImagenPublica(valor.image_url))
    && typeof valor.active === 'boolean';
}

function esMapaTextos(valor: unknown): valor is Record<string, string> {
  return esRegistro(valor) && Object.entries(valor).every(([key, elementoLista]) => key.trim().length > 0 && typeof elementoLista === 'string');
}

function esListaEquipos(valor: unknown): valor is Equipo[] {
  return Array.isArray(valor) && valor.every(esEquipo);
}

function esEnteroPositivo(valor: unknown): valor is number {
  return typeof valor === 'number' && Number.isInteger(valor) && valor > 0;
}

function esFechaIso(valor: unknown): valor is string {
  return typeof valor === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(valor);
}

function tieneClavesExactas(valor: Record<string, unknown>, claves: readonly string[]): boolean {
  return Object.keys(valor).length === claves.length && claves.every((key) => Object.hasOwn(valor, key));
}

function esFechaCalendario(valor: unknown): valor is string {
  if (!esFechaIso(valor)) return false;
  const ano = Number(valor.slice(0, 4));
  const mes = Number(valor.slice(5, 7));
  const dia = Number(valor.slice(8, 10));
  const anoBisiesto = ano % 4 === 0 && (ano % 100 !== 0 || ano % 400 === 0);
  const dias = [31, anoBisiesto ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return ano > 0 && mes >= 1 && mes <= 12 && dia > 0 && dia <= (dias[mes - 1] ?? 0);
}

function esIntervaloFechas(valor: Record<string, unknown>): boolean {
  return esFechaCalendario(valor.start_date) && esFechaCalendario(valor.end_date) && valor.end_date > valor.start_date;
}

function esImagenPublicaLocal(valor: unknown): valor is string {
  const prefijo = `${BASE_API}/public/images/`;
  return typeof valor === 'string' && valor.startsWith(prefijo)
    && valor.slice(prefijo.length).split('/').every((segmento) => /^[a-zA-Z0-9_-][a-zA-Z0-9_.-]*$/.test(segmento));
}

function esImagenPublica(valor: unknown): valor is string {
  if (esImagenPublicaLocal(valor)) return true;
  if (typeof valor !== 'string' || !/^https:\/\//i.test(valor) || valor.includes('\\')
    || Array.from(valor).some((caracter) => caracter.charCodeAt(0) <= 32 || caracter.charCodeAt(0) === 127)) return false;
  try {
    const url = new URL(valor);
    return url.protocol === 'https:' && url.hostname.length > 0 && !url.username && !url.password && !url.search && !url.hash;
  } catch {
    return false;
  }
}

function esEquipoPublico(valor: unknown): valor is EquipoPublico {
  return esRegistro(valor)
    && tieneClavesExactas(valor, ['id', 'name', 'category', 'public_description', 'technical_specs', 'image_url', 'image_fallback_url', 'active_reservations_count'])
    && esEnteroPositivo(valor.id)
    && typeof valor.name === 'string' && valor.name.trim().length > 0
    && typeof valor.category === 'string' && valor.category.trim().length > 0
    && typeof valor.public_description === 'string'
    && esRegistro(valor.technical_specs)
    && Object.entries(valor.technical_specs).every(([key, elementoLista]) => key.trim().length > 0 && typeof elementoLista === 'string')
    && (valor.image_url === null || esImagenPublica(valor.image_url))
    && esImagenPublicaLocal(valor.image_fallback_url)
    && typeof valor.active_reservations_count === 'number'
    && Number.isSafeInteger(valor.active_reservations_count) && valor.active_reservations_count >= 0;
}

function esListaEquiposPublicos(valor: unknown): valor is EquipoPublico[] {
  return Array.isArray(valor) && valor.every(esEquipoPublico);
}

function esDisponibilidadPublica(valor: unknown): valor is DisponibilidadPublica {
  return esRegistro(valor)
    && tieneClavesExactas(valor, ['equipment_id', 'start_date', 'end_date', 'available', 'status'])
    && esEnteroPositivo(valor.equipment_id)
    && ((valor.status === 'select_dates' && valor.start_date === null && valor.end_date === null && valor.available === null)
      || (esIntervaloFechas(valor) && ((valor.status === 'available' && valor.available === true)
        || (valor.status === 'unavailable' && valor.available === false))));
}

function esCalendarioDisponibilidadPublica(valor: unknown): valor is CalendarioDisponibilidadPublica {
  return esRegistro(valor)
    && tieneClavesExactas(valor, ['equipment_id', 'start_date', 'end_date', 'occupied_ranges', 'can_book', ...(Object.hasOwn(valor, 'unavailable_end_dates') ? ['unavailable_end_dates'] : [])])
    && esEnteroPositivo(valor.equipment_id) && esIntervaloFechas(valor)
    && typeof valor.can_book === 'boolean'
    && (valor.unavailable_end_dates === undefined || (Array.isArray(valor.unavailable_end_dates)
      && valor.unavailable_end_dates.every((fecha) => esFechaCalendario(fecha)
        && typeof valor.start_date === 'string' && typeof valor.end_date === 'string'
        && fecha >= valor.start_date && fecha < valor.end_date)))
    && Array.isArray(valor.occupied_ranges)
    && valor.occupied_ranges.every((intervalo) => esRegistro(intervalo)
      && tieneClavesExactas(intervalo, ['start_date', 'end_date']) && esIntervaloFechas(intervalo)
      && typeof intervalo.start_date === 'string' && typeof intervalo.end_date === 'string'
      && typeof valor.start_date === 'string' && typeof valor.end_date === 'string'
      && intervalo.start_date >= valor.start_date && intervalo.end_date <= valor.end_date);
}

function esFechasReservaPublica(valor: unknown): valor is FechasReservaPublica {
  return esRegistro(valor)
    && tieneClavesExactas(valor, ['equipment_id', 'reservations'])
    && esEnteroPositivo(valor.equipment_id)
    && Array.isArray(valor.reservations)
    && valor.reservations.every((intervalo) => esRegistro(intervalo)
      && tieneClavesExactas(intervalo, ['start_date', 'end_date']) && esIntervaloFechas(intervalo));
}

function esReservaCliente(valor: unknown): valor is ReservaCliente {
  return esRegistro(valor)
    && tieneClavesExactas(valor, ['id', 'equipment_id', 'start_date', 'end_date', 'status'])
    && esEnteroPositivo(valor.id) && esEnteroPositivo(valor.equipment_id)
    && esIntervaloFechas(valor)
    && (valor.status === 'confirmed' || valor.status === 'cancelled');
}

function esListaReservasCliente(valor: unknown): valor is ReservaCliente[] {
  return Array.isArray(valor) && valor.every(esReservaCliente);
}

function esProductosGuardados(valor: unknown): valor is ProductosGuardados {
  return esRegistro(valor) && tieneClavesExactas(valor, ['equipment_ids'])
    && Array.isArray(valor.equipment_ids) && valor.equipment_ids.every(esEnteroPositivo)
    && new Set(valor.equipment_ids).size === valor.equipment_ids.length;
}

function esIncidenciaCliente(valor: unknown): valor is IncidenciaCliente {
  return esRegistro(valor)
    && tieneClavesExactas(valor, ['id', 'reservation_id', 'title', 'description', 'status', 'public_response'])
    && esEnteroPositivo(valor.id) && esEnteroPositivo(valor.reservation_id)
    && typeof valor.title === 'string' && typeof valor.description === 'string'
    && (valor.status === 'open' || valor.status === 'in_progress' || valor.status === 'resolved')
    && typeof valor.public_response === 'string';
}

function esListaIncidenciasCliente(valor: unknown): valor is IncidenciaCliente[] {
  return Array.isArray(valor) && valor.every(esIncidenciaCliente);
}

function esReserva(valor: unknown): valor is Reserva {
  return esRegistro(valor)
    && esEnteroPositivo(valor.id)
    && esEnteroPositivo(valor.equipment_id)
    && typeof valor.customer_name === 'string'
    && typeof valor.customer_email === 'string'
    && esFechaIso(valor.start_date)
    && esFechaIso(valor.end_date)
    && (valor.status === 'confirmed' || valor.status === 'cancelled')
    && (valor.customer_user_id === undefined || valor.customer_user_id === null || esEnteroPositivo(valor.customer_user_id))
    && (valor.origin === undefined || valor.origin === 'portal' || valor.origin === 'admin' || valor.origin === 'csv' || valor.origin === 'legacy')
    && (typeof valor.external_reference === 'string' || valor.external_reference === null);
}

function esListaReservas(valor: unknown): valor is Reserva[] {
  return Array.isArray(valor) && valor.every(esReserva);
}

function esDisponibilidad(valor: unknown): valor is Disponibilidad {
  return esRegistro(valor)
    && esEnteroPositivo(valor.equipment_id)
    && esFechaIso(valor.start_date)
    && esFechaIso(valor.end_date)
    && typeof valor.available === 'boolean'
    && (valor.reason === null || valor.reason === 'equipment_inactive'
      || valor.reason === 'reservation_overlap' || valor.reason === 'blocking_incident')
    && Array.isArray(valor.conflicting_reservation_ids)
    && valor.conflicting_reservation_ids.every(esEnteroPositivo);
}

function esIncidencia(valor: unknown): valor is Incidencia {
  return esRegistro(valor)
    && esEnteroPositivo(valor.id)
    && esEnteroPositivo(valor.equipment_id)
    && typeof valor.title === 'string'
    && typeof valor.description === 'string'
    && (valor.priority === 'low' || valor.priority === 'medium' || valor.priority === 'high')
    && typeof valor.blocking === 'boolean'
    && (valor.status === 'open' || valor.status === 'in_progress' || valor.status === 'resolved')
    && typeof valor.resolution === 'string'
    && (valor.reservation_id === undefined || valor.reservation_id === null || esEnteroPositivo(valor.reservation_id))
    && (valor.author_user_id === undefined || valor.author_user_id === null || esEnteroPositivo(valor.author_user_id))
    && (valor.public_response === undefined || typeof valor.public_response === 'string')
    && (valor.internal_notes === undefined || typeof valor.internal_notes === 'string')
    && Array.isArray(valor.confirmed_reservation_ids)
    && valor.confirmed_reservation_ids.every(esEnteroPositivo)
    && (typeof valor.warning === 'string' || valor.warning === null);
}

function esListaIncidencias(valor: unknown): valor is Incidencia[] {
  return Array.isArray(valor) && valor.every(esIncidencia);
}

function esEnteroNoNegativo(valor: unknown): valor is number {
  return typeof valor === 'number' && Number.isInteger(valor) && valor >= 0;
}

function esTotalesImportacion(valor: unknown): valor is TotalesImportacion {
  return esRegistro(valor)
    && esEnteroNoNegativo(valor.total)
    && esEnteroNoNegativo(valor.accepted)
    && esEnteroNoNegativo(valor.already_imported)
    && esEnteroNoNegativo(valor.rejected);
}

function esResultadoFilaImportacion(valor: unknown): valor is ResultadoFilaImportacion {
  return esRegistro(valor)
    && esEnteroPositivo(valor.line)
    && (typeof valor.external_reference === 'string' || valor.external_reference === null)
    && typeof valor.message === 'string'
    && ((valor.status === 'rejected' && valor.reservation === null)
      || ((valor.status === 'accepted' || valor.status === 'already_imported') && esReserva(valor.reservation)));
}

function esInformeImportacion(valor: unknown): valor is InformeImportacion {
  return esRegistro(valor)
    && esTotalesImportacion(valor.totals)
    && Array.isArray(valor.rows)
    && valor.rows.every(esResultadoFilaImportacion);
}

function cadenaConsulta(parametros: Record<string, string | number | boolean | undefined>): string {
  const busqueda = new URLSearchParams();
  for (const [key, valor] of Object.entries(parametros)) {
    if (valor !== undefined) busqueda.set(key, String(valor));
  }
  return busqueda.size > 0 ? `?${busqueda.toString()}` : '';
}

function esSaludServicio(valor: unknown): valor is { status: 'ok' } {
  return esRegistro(valor) && valor.status === 'ok';
}

function esSesionAutenticacion(valor: unknown): valor is SesionAutenticacion {
  return esRegistro(valor) && valor.authenticated === true
    && typeof valor.username === 'string' && valor.username.length > 0
    && typeof valor.expires_at === 'string'
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$/.test(valor.expires_at)
    && (valor.role === 'customer' || valor.role === 'admin')
    && (valor.user === null ? valor.role === 'admin'
      : esUsuario(valor.user) && valor.user.active && valor.user.role === valor.role);
}

function esUsuario(valor: unknown): valor is Usuario {
  return esRegistro(valor) && esEnteroPositivo(valor.id)
    && typeof valor.name === 'string' && valor.name.length > 0
    && typeof valor.email === 'string' && valor.email.length > 0
    && (valor.role === 'customer' || valor.role === 'admin')
    && typeof valor.active === 'boolean';
}

function esClienteRegistrado(valor: unknown): valor is Usuario {
  return esUsuario(valor) && valor.role === 'customer' && valor.active;
}

function esCsrf(valor: unknown): valor is { csrf_token: string } {
  return esRegistro(valor) && typeof valor.csrf_token === 'string' && valor.csrf_token.length > 0;
}

function haCerradoSesion(valor: unknown): valor is { authenticated: false } {
  return esRegistro(valor) && valor.authenticated === false;
}

async function obtenerTokenCsrf(): Promise<string> {
  if (tokenCsrf) return tokenCsrf;
  // Las primeras escrituras simultáneas deben compartir una sola cookie de sesión anónima.
  if (!solicitudCsrf) {
    const version = versionCsrf;
    const pendiente = solicitud(`${BASE_API}/auth/csrf`, esCsrf, {}, false).then(({ csrf_token: token_csrf }) => {
      if (version !== versionCsrf) throw new ErrorApi('La protección de la sesión ha cambiado. Vuelve a intentarlo.', 403);
      tokenCsrf = token_csrf;
      return token_csrf;
    });
    solicitudCsrf = pendiente;
    void pendiente.finally(() => { if (solicitudCsrf === pendiente) solicitudCsrf = null; }).catch(() => {});
  }
  return solicitudCsrf;
}

function mensajeError(cuerpo: unknown, estado: number): string {
  if (esRegistro(cuerpo)) {
    if (typeof cuerpo.detail === 'string') return cuerpo.detail;
    if (Array.isArray(cuerpo.detail)) {
      const mensajes = cuerpo.detail.flatMap((elementoLista: unknown) =>
        esRegistro(elementoLista) && typeof elementoLista.msg === 'string' ? [elementoLista.msg] : [],
      );
      if (mensajes.length > 0) return mensajes.join(' ');
    }
  }
  return `No se pudo completar la petición (${estado}).`;
}

function erroresCampos(cuerpo: unknown): Record<string, string> {
  if (!esRegistro(cuerpo) || !Array.isArray(cuerpo.detail)) return {};
  const campos: Record<string, string> = {};
  for (const elementoLista of cuerpo.detail as unknown[]) {
    if (!esRegistro(elementoLista) || !Array.isArray(elementoLista.loc)) continue;
    const campo = elementoLista.loc.slice(1).find((parte: unknown) => typeof parte === 'string');
    if (typeof campo !== 'string') continue;
    const contexto = esRegistro(elementoLista.ctx) ? elementoLista.ctx : {};
    const mensaje = typeof elementoLista.msg === 'string' ? elementoLista.msg.replace(/^Value error, /, '') : '';
    campos[campo] = elementoLista.type === 'missing' ? 'Este campo es obligatorio.'
      : elementoLista.type === 'string_pattern_mismatch' ? 'Revisa el formato de este campo.'
        : elementoLista.type === 'string_too_long' ? typeof contexto.max_length === 'number'
          ? `Usa como máximo ${contexto.max_length} caracteres.` : 'El valor supera la longitud permitida.'
          : elementoLista.type === 'string_too_short' ? 'Escribe un valor con contenido.'
            : /^(El |La |Usa |Envía |Indica |Revisa )/.test(mensaje) ? mensaje
              : 'Revisa el valor de este campo.';
  }
  return campos;
}

async function solicitud<T>(
  ruta: string,
  validar: (valor: unknown) => valor is T,
  opciones: RequestInit = {},
  notificarSinAutorizacion = true,
): Promise<T> {
  const version = versionSesion;
  const cabeceras = new Headers(opciones.headers);
  cabeceras.set('Accept', 'application/json');
  if (opciones.body !== undefined && !(opciones.body instanceof FormData)) {
    cabeceras.set('Content-Type', 'application/json');
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(opciones.method ?? 'GET')) {
    cabeceras.set('X-CSRF-Token', await obtenerTokenCsrf());
  }
  asegurarSesionActual(ruta, version);

  let respuesta: Response;
  try {
    respuesta = await fetch(ruta, { ...opciones, headers: cabeceras, credentials: 'same-origin' });
  } catch (error) {
    if (esRegistro(error) && error.name === 'AbortError') throw error;
    throw new ErrorApi('No se pudo conectar con el servidor. Comprueba que el backend está en marcha.', 0);
  }

  asegurarSesionActual(ruta, version);

  // Comprueba el estado aunque la respuesta de una sesión caducada contenga JSON mal formado.
  if (respuesta.status === 401 && version === versionSesion && !esRutaPublica(ruta)) {
    invalidarSesion();
    if (notificarSinAutorizacion) for (const oyente of oyentesSinAutorizacion) oyente();
  } else if (respuesta.status === 403) {
    limpiarTokenCsrf();
  }

  let cuerpo: unknown;
  try {
    cuerpo = await respuesta.json();
  } catch {
    throw new ErrorApi(respuesta.ok ? RESPUESTA_INVALIDA : mensajeError(null, respuesta.status), respuesta.status);
  }

  if (!respuesta.ok) throw new ErrorApi(mensajeError(cuerpo, respuesta.status), respuesta.status, erroresCampos(cuerpo));
  asegurarSesionActual(ruta, version);
  if (!validar(cuerpo)) throw new ErrorApi(RESPUESTA_INVALIDA, respuesta.status);
  return cuerpo;
}

function asegurarSesionActual(ruta: string, version: number) {
  if (ruta.startsWith(`${BASE_API}/`) && !esRutaPublica(ruta) && version !== versionSesion) {
    throw new ErrorApi('La sesión ha cambiado. Vuelve a intentarlo.', 401);
  }
}

function esRutaPublica(ruta: string): boolean {
  return ruta.startsWith(`${BASE_API}/public/`);
}

export const api = {
  sesion: () => solicitud(`${BASE_API}/auth/session`, esSesionAutenticacion, {}, false),
  registrar: (datos: EntradaRegistro) => solicitud(`${BASE_API}/auth/register`, esClienteRegistrado, {
    method: 'POST', body: JSON.stringify(datos),
  }, false),
  iniciarSesion: async (datos: EntradaAcceso) => {
    const sesion = await solicitud(`${BASE_API}/auth/login`, esSesionAutenticacion, {
      method: 'POST', body: JSON.stringify(datos),
    }, false);
    invalidarSesion();
    return sesion;
  },
  cerrarSesionUsuario: async () => {
    const resultado = await solicitud(`${BASE_API}/auth/logout`, haCerradoSesion, { method: 'POST' });
    invalidarSesion();
    return resultado;
  },
  saludServicio: (senal?: AbortSignal) => solicitud('/health', esSaludServicio, { signal: senal ?? null }),
  listarEquiposPublicos: (filtros: FiltrosEquiposPublicos = {}, senal?: AbortSignal) => solicitud(
    `${BASE_API}/public/equipment${cadenaConsulta({ q: filtros.q, category: filtros.category })}`,
    esListaEquiposPublicos, { signal: senal ?? null }, false,
  ),
  obtenerEquipoPublico: (id: number, senal?: AbortSignal) => solicitud(
    `${BASE_API}/public/equipment/${id}`, esEquipoPublico, { signal: senal ?? null }, false,
  ),
  obtenerDisponibilidadPublica: (id: number, fechas?: IntervaloFechas, senal?: AbortSignal) => solicitud(
    `${BASE_API}/public/equipment/${id}/availability${cadenaConsulta({ start_date: fechas?.start_date, end_date: fechas?.end_date })}`,
    esDisponibilidadPublica, { signal: senal ?? null }, false,
  ),
  obtenerCalendarioDisponibilidadPublica: (id: number, fechas: IntervaloFechas & { booking_start?: string }, senal?: AbortSignal) => solicitud(
    `${BASE_API}/public/equipment/${id}/calendar${cadenaConsulta({ start_date: fechas.start_date, end_date: fechas.end_date, booking_start: fechas.booking_start })}`,
    esCalendarioDisponibilidadPublica, { signal: senal ?? null }, false,
  ),
  obtenerFechasReservaPublica: (id: number, senal?: AbortSignal) => solicitud(
    `${BASE_API}/public/equipment/${id}/reservations`, esFechasReservaPublica, { signal: senal ?? null }, false,
  ),
  listarMisReservas: (senal?: AbortSignal) => solicitud(
    `${BASE_API}/me/reservations`, esListaReservasCliente, { signal: senal ?? null },
  ),
  listarProductosGuardados: (senal?: AbortSignal) => solicitud(
    `${BASE_API}/me/saved-products`, esProductosGuardados, { signal: senal ?? null },
  ),
  guardarProducto: (id: number) => solicitud(`${BASE_API}/me/saved-products/${id}`, esProductosGuardados, { method: 'PUT' }),
  eliminarProductoGuardado: (id: number) => solicitud(`${BASE_API}/me/saved-products/${id}`, esProductosGuardados, { method: 'DELETE' }),
  crearMisReservasConjuntas: (datos: EntradaReservasConjuntasCliente, claveIdempotencia?: string) => solicitud(`${BASE_API}/me/reservations/batch`,
    (valor): valor is ReservaCliente[] => esListaReservasCliente(valor)
      && valor.length === datos.equipment_ids.length && new Set(valor.map((elementoLista) => elementoLista.id)).size === valor.length
      && valor.every((elementoLista) => (Boolean(claveIdempotencia) || elementoLista.status === 'confirmed') && elementoLista.start_date === datos.start_date && elementoLista.end_date === datos.end_date),
    { method: 'POST', ...(claveIdempotencia ? { headers: { 'Idempotency-Key': claveIdempotencia } } : {}), body: JSON.stringify({ equipment_ids: datos.equipment_ids, start_date: datos.start_date, end_date: datos.end_date }) },
  ),
  obtenerMiReserva: (id: number, senal?: AbortSignal) => solicitud(
    `${BASE_API}/me/reservations/${id}`, esReservaCliente, { signal: senal ?? null },
  ),
  crearMiReserva: (datos: EntradaReservaCliente, claveIdempotencia?: string) => solicitud(`${BASE_API}/me/reservations`, esReservaCliente, {
    method: 'POST', ...(claveIdempotencia ? { headers: { 'Idempotency-Key': claveIdempotencia } } : {}),
    body: JSON.stringify({ equipment_id: datos.equipment_id, start_date: datos.start_date, end_date: datos.end_date }),
  }),
  cancelarMiReserva: (id: number) => solicitud(`${BASE_API}/me/reservations/${id}/cancel`, esReservaCliente, {
    method: 'POST',
  }),
  listarMisIncidencias: (senal?: AbortSignal) => solicitud(
    `${BASE_API}/me/incidents`, esListaIncidenciasCliente, { signal: senal ?? null },
  ),
  obtenerMiIncidencia: (id: number, senal?: AbortSignal) => solicitud(
    `${BASE_API}/me/incidents/${id}`, esIncidenciaCliente, { signal: senal ?? null },
  ),
  crearMiIncidencia: (idReserva: number, datos: EntradaIncidenciaCliente) => solicitud(
    `${BASE_API}/me/reservations/${idReserva}/incidents`, esIncidenciaCliente, {
      method: 'POST', body: JSON.stringify({ title: datos.title, description: datos.description }),
    },
  ),
  listarEquipos: () => solicitud(`${BASE_API}/equipment`, esListaEquipos),
  obtenerEquipo: (id: number) => solicitud(`${BASE_API}/equipment/${id}`, esEquipo),
  crearEquipo: (datos: EntradaEquipo) => solicitud(`${BASE_API}/equipment`, esEquipo, {
    method: 'POST', body: JSON.stringify(datos),
  }),
  actualizarEquipo: (id: number, datos: EntradaEquipo) => solicitud(`${BASE_API}/equipment/${id}`, esEquipo, {
    method: 'PUT', body: JSON.stringify(datos),
  }),
  modificarEquipo: (id: number, datos: CambiosEquipo) => solicitud(`${BASE_API}/equipment/${id}`, esEquipo, {
    method: 'PATCH', body: JSON.stringify(datos),
  }),
  listarReservas: (filtros: FiltrosReservas = {}) => solicitud(
    `${BASE_API}/reservations${cadenaConsulta({ ...filtros })}`, esListaReservas,
  ),
  obtenerReserva: (id: number) => solicitud(`${BASE_API}/reservations/${id}`, esReserva),
  crearReserva: (datos: EntradaReserva) => solicitud(`${BASE_API}/reservations`, esReserva, {
    method: 'POST', body: JSON.stringify({
      equipment_id: datos.equipment_id, customer_name: datos.customer_name, customer_email: datos.customer_email,
      start_date: datos.start_date, end_date: datos.end_date, external_reference: datos.external_reference,
    }),
  }),
  cancelarReserva: (id: number) => solicitud(`${BASE_API}/reservations/${id}/cancel`, esReserva, {
    method: 'POST',
  }),
  obtenerDisponibilidadEquipo: (id: number, intervalo: IntervaloFechas) => solicitud(
    `${BASE_API}/equipment/${id}/availability${cadenaConsulta({ ...intervalo })}`, esDisponibilidad,
  ),
  listarIncidencias: (filtros: FiltrosIncidencias = {}) => solicitud(
    `${BASE_API}/incidents${cadenaConsulta({ ...filtros })}`, esListaIncidencias,
  ),
  obtenerIncidencia: (id: number) => solicitud(`${BASE_API}/incidents/${id}`, esIncidencia),
  crearIncidencia: (datos: EntradaIncidencia) => solicitud(`${BASE_API}/incidents`, esIncidencia, {
    method: 'POST', body: JSON.stringify(datos),
  }),
  modificarIncidencia: (id: number, datos: ActualizacionIncidencia) => solicitud(`${BASE_API}/incidents/${id}`, esIncidencia, {
    method: 'PATCH', body: JSON.stringify({
      priority: datos.priority, blocking: datos.blocking, public_response: datos.public_response, internal_notes: datos.internal_notes,
    }),
  }),
  cambiarEstadoIncidencia: (id: number, datos: CambioEstadoIncidencia) => solicitud(`${BASE_API}/incidents/${id}/status`, esIncidencia, {
    method: 'PATCH', body: JSON.stringify(datos),
  }),
  importarReservas: (archivo: File) => {
    const cuerpo = new FormData();
    cuerpo.append('file', archivo);
    return solicitud(`${BASE_API}/imports`, esInformeImportacion, { method: 'POST', body: cuerpo });
  },
};
