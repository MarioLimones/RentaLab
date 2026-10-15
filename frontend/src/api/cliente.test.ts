import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ErrorApi, api, URL_EJEMPLO_IMPORTACION, limpiarTokenCsrf } from './cliente';

const equipo = {
  id: 1,
  code: 'CAM-001',
  name: 'Cámara de estudio',
  category: 'Vídeo',
  description: 'Equipo ficticio',
  active: true,
};
const entradaEquipo = {
  code: equipo.code,
  name: equipo.name,
  category: equipo.category,
  description: equipo.description,
  active: equipo.active,
};
const reserva = {
  id: 3,
  equipment_id: 1,
  customer_name: 'Cliente ficticio',
  customer_email: 'cliente@example.test',
  start_date: '2026-11-10',
  end_date: '2026-11-12',
  status: 'confirmed',
  external_reference: null,
};
const entradaReserva = {
  equipment_id: reserva.equipment_id,
  customer_name: reserva.customer_name,
  customer_email: reserva.customer_email,
  start_date: reserva.start_date,
  end_date: reserva.end_date,
};
const disponibilidad = {
  equipment_id: 1,
  start_date: '2026-11-10',
  end_date: '2026-11-12',
  available: true,
  reason: null,
  conflicting_reservation_ids: [],
};
const incidencia = {
  id: 4,
  equipment_id: 1,
  title: 'Conector pendiente de revisar',
  description: 'Incidencia ficticia de demostración.',
  priority: 'medium',
  blocking: false,
  status: 'open',
  resolution: '',
  confirmed_reservation_ids: [],
  warning: null,
};
const filaImportadaAceptada = {
  line: 2,
  external_reference: 'PEDIDO-FICTICIO-001',
  status: 'accepted',
  reservation: { ...reserva, external_reference: 'PEDIDO-FICTICIO-001' },
  message: 'Reserva creada.',
};
const informeImportacion = {
  totals: { total: 3, accepted: 1, already_imported: 1, rejected: 1 },
  rows: [
    filaImportadaAceptada,
    {
      line: 3,
      external_reference: 'PEDIDO-FICTICIO-002',
      status: 'already_imported',
      reservation: { ...reserva, id: 4, status: 'cancelled', external_reference: 'PEDIDO-FICTICIO-002' },
      message: 'La referencia ya se importó; se conserva su cancelación.',
    },
    {
      line: 4,
      external_reference: null,
      status: 'rejected',
      reservation: null,
      message: 'El equipo indicado no existe.',
    },
  ],
};
const peticionSimulada = vi.fn<typeof fetch>();

beforeEach(() => {
  limpiarTokenCsrf();
  peticionSimulada.mockReset();
  // Conserva las comprobaciones originales del contrato de negocio; la autenticación se prueba aparte.
  vi.stubGlobal('fetch', (ruta: RequestInfo | URL, opciones?: RequestInit) => ruta === '/api/auth/csrf'
    ? Promise.resolve(Response.json({ csrf_token: 'test-csrf' })) : peticionSimulada(ruta, opciones));
});

describe("cliente de la API", () => {
  it("comprueba el estado del servicio en el mismo origen", async () => {
    peticionSimulada.mockResolvedValue(Response.json({ status: 'ok' }));
    await expect(api.saludServicio()).resolves.toEqual({ status: 'ok' });
    expect(peticionSimulada).toHaveBeenCalledWith('/health', expect.objectContaining({ headers: expect.any(Headers) }));
  });

  it("utiliza /api para el contrato completo de equipos", async () => {
    peticionSimulada.mockResolvedValueOnce(Response.json([equipo]));
    await expect(api.listarEquipos()).resolves.toEqual([equipo]);
    expect(peticionSimulada).toHaveBeenLastCalledWith('/api/equipment', expect.any(Object));

    peticionSimulada.mockResolvedValueOnce(Response.json(equipo));
    await expect(api.obtenerEquipo(1)).resolves.toEqual(equipo);
    expect(peticionSimulada).toHaveBeenLastCalledWith('/api/equipment/1', expect.any(Object));

    peticionSimulada.mockResolvedValueOnce(Response.json(equipo, { status: 201 }));
    await expect(api.crearEquipo(entradaEquipo)).resolves.toEqual(equipo);
    expect(peticionSimulada).toHaveBeenLastCalledWith('/api/equipment', expect.objectContaining({ method: 'POST', body: JSON.stringify(entradaEquipo) }));

    peticionSimulada.mockResolvedValueOnce(Response.json(equipo));
    await expect(api.actualizarEquipo(1, entradaEquipo)).resolves.toEqual(equipo);
    expect(peticionSimulada).toHaveBeenLastCalledWith('/api/equipment/1', expect.objectContaining({ method: 'PUT' }));

    peticionSimulada.mockResolvedValueOnce(Response.json({ ...equipo, active: false }));
    await expect(api.modificarEquipo(1, { active: false })).resolves.toMatchObject({ active: false });
    expect(peticionSimulada).toHaveBeenLastCalledWith('/api/equipment/1', expect.objectContaining({ method: 'PATCH', body: '{"active":false}' }));
  });

  it.each([
    ['saludServicio', { status: 'broken' }],
    ['listarEquipos', [{ ...equipo, active: 'yes' }]],
  ] as const)("rechaza respuestas de %s no válidas sin confiar únicamente en TypeScript", async (metodo, cuerpo) => {
    peticionSimulada.mockResolvedValue(Response.json(cuerpo));
    await expect(api[metodo]()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it("rechaza JSON mal formado", async () => {
    peticionSimulada.mockResolvedValue(new Response('<html>Error</html>'));
    await expect(api.saludServicio()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it("conserva el estado HTTP y el detalle del servidor", async () => {
    peticionSimulada.mockResolvedValue(Response.json({ detail: 'El código ya existe.' }, { status: 409 }));
    const solicitud = api.crearEquipo(entradaEquipo);
    await expect(solicitud).rejects.toMatchObject({ name: 'ApiError', estado: 409, message: 'El código ya existe.' });
    await expect(solicitud).rejects.toBeInstanceOf(ErrorApi);
  });

  it("presenta de forma legible los detalles de validación de FastAPI", async () => {
    peticionSimulada.mockResolvedValue(Response.json({ detail: [{ loc: ['body', 'name'], msg: 'Field required', type: 'missing' }] }, { status: 422 }));
    await expect(api.crearEquipo(entradaEquipo)).rejects.toThrow('Field required');
  });

  it("gestiona un error HTTP cuyo cuerpo no es JSON", async () => {
    peticionSimulada.mockResolvedValue(new Response('Unavailable', { status: 503 }));
    await expect(api.saludServicio()).rejects.toMatchObject({ estado: 503, message: 'No se pudo completar la petición (503).' });
  });

  it("explica un fallo de red", async () => {
    peticionSimulada.mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(api.saludServicio()).rejects.toThrow('No se pudo conectar con el servidor. Comprueba que el backend está en marcha.');
  });

  it("conserva la cancelación de solicitudes", async () => {
    const cancelada = new DOMException('Aborted', 'AbortError');
    peticionSimulada.mockRejectedValue(cancelada);
    await expect(api.saludServicio(new AbortController().signal)).rejects.toBe(cancelada);
  });

});

describe("cliente de la API de reservas", () => {
  it("lista reservas sin filtros opcionales", async () => {
    peticionSimulada.mockResolvedValue(Response.json([reserva]));
    await expect(api.listarReservas()).resolves.toEqual([reserva]);
    expect(peticionSimulada).toHaveBeenCalledWith('/api/reservations', expect.any(Object));
  });

  it("serializa los filtros admitidos con URLSearchParams", async () => {
    peticionSimulada.mockResolvedValue(Response.json([]));
    await expect(api.listarReservas({
      equipment_id: 1,
      status: 'cancelled',
      start_date: '2026-11-10',
      end_date: '2026-11-12',
    })).resolves.toEqual([]);
    expect(peticionSimulada).toHaveBeenCalledWith(
      '/api/reservations?equipment_id=1&status=cancelled&start_date=2026-11-10&end_date=2026-11-12',
      expect.any(Object),
    );
  });

  it("omite filtros sin especificar y deja a Python validar un intervalo incompleto", async () => {
    peticionSimulada.mockResolvedValue(Response.json({ detail: 'Indica ambas fechas.' }, { status: 422 }));
    await expect(api.listarReservas({ start_date: '2026-11-10' }))
      .rejects.toMatchObject({ estado: 422, message: 'Indica ambas fechas.' });
    expect(peticionSimulada).toHaveBeenCalledWith('/api/reservations?start_date=2026-11-10', expect.any(Object));
  });

  it("consulta una reserva y conserva su referencia externa opcional", async () => {
    const importado = { ...reserva, external_reference: 'FICTICIO-001' };
    peticionSimulada.mockResolvedValue(Response.json(importado));
    await expect(api.obtenerReserva(3)).resolves.toEqual(importado);
    expect(peticionSimulada).toHaveBeenCalledWith('/api/reservations/3', expect.any(Object));
  });

  it("crea una reserva con cuerpo JSON y acepta la ausencia de referencia", async () => {
    peticionSimulada.mockResolvedValue(Response.json(reserva, { status: 201 }));
    await expect(api.crearReserva(entradaReserva)).resolves.toEqual(reserva);
    expect(peticionSimulada).toHaveBeenCalledWith('/api/reservations', expect.objectContaining({
      method: 'POST', body: JSON.stringify(entradaReserva),
    }));
    const opciones = peticionSimulada.mock.calls[0]?.[1];
    expect(new Headers(opciones?.headers).get('Content-Type')).toBe('application/json');
  });

  it("envía una referencia externa nula explícita sin transformar los datos del cliente", async () => {
    peticionSimulada.mockResolvedValue(Response.json(reserva, { status: 201 }));
    const entrada = { ...entradaReserva, external_reference: null };
    await api.crearReserva(entrada);
    expect(peticionSimulada).toHaveBeenCalledWith('/api/reservations', expect.objectContaining({ body: JSON.stringify(entrada) }));
  });

  it("cancela sin enviar cuerpo y acepta la reserva cancelada que se conserva", async () => {
    const cancelado = { ...reserva, status: 'cancelled' };
    peticionSimulada.mockResolvedValue(Response.json(cancelado));
    await expect(api.cancelarReserva(3)).resolves.toEqual(cancelado);
    expect(peticionSimulada).toHaveBeenCalledWith('/api/reservations/3/cancel', expect.objectContaining({ method: 'POST' }));
    const opciones = peticionSimulada.mock.calls[0]?.[1];
    expect(opciones?.body).toBeUndefined();
    expect(new Headers(opciones?.headers).has('Content-Type')).toBe(false);
  });

  it("consulta la disponibilidad del equipo con parámetros de intervalo ISO", async () => {
    peticionSimulada.mockResolvedValue(Response.json(disponibilidad));
    await expect(api.obtenerDisponibilidadEquipo(1, { start_date: '2026-11-10', end_date: '2026-11-12' }))
      .resolves.toEqual(disponibilidad);
    expect(peticionSimulada).toHaveBeenCalledWith(
      '/api/equipment/1/availability?start_date=2026-11-10&end_date=2026-11-12', expect.any(Object),
    );
  });

  it.each(['equipment_inactive', 'reservation_overlap'])(
    "conserva el motivo de disponibilidad del servidor %s", async (motivo) => {
      const bloqueado = { ...disponibilidad, available: false, reason: motivo, conflicting_reservation_ids: [3] };
      peticionSimulada.mockResolvedValue(Response.json(bloqueado));
      await expect(api.obtenerDisponibilidadEquipo(1, { start_date: '2026-11-10', end_date: '2026-11-12' }))
        .resolves.toEqual(bloqueado);
    },
  );

  it("conserva los conflictos operativos sin decidir los solapamientos en TypeScript", async () => {
    peticionSimulada.mockResolvedValue(Response.json({ detail: 'El equipo tiene una reserva incompatible.' }, { status: 409 }));
    await expect(api.crearReserva(entradaReserva))
      .rejects.toMatchObject({ estado: 409, message: 'El equipo tiene una reserva incompatible.' });
  });

  it.each([
    { ...reserva, id: 0 },
    { ...reserva, equipment_id: 1.5 },
    { ...reserva, customer_name: null },
    { ...reserva, customer_email: 42 },
    { ...reserva, start_date: '10/11/2026' },
    { ...reserva, end_date: null },
    { ...reserva, status: 'pending' },
    { ...reserva, external_reference: 1 },
  ])("rechaza una respuesta de reserva no válida: %j", async (cuerpo) => {
    peticionSimulada.mockResolvedValue(Response.json(cuerpo));
    await expect(api.obtenerReserva(3)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it("rechaza una lista de reservas que contiene registros no válidos", async () => {
    peticionSimulada.mockResolvedValue(Response.json([reserva, { ...reserva, status: 'pending' }]));
    await expect(api.listarReservas()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it.each([
    { ...disponibilidad, equipment_id: -1 },
    { ...disponibilidad, start_date: '2026-11-10T00:00:00' },
    { ...disponibilidad, end_date: 12 },
    { ...disponibilidad, available: 'yes' },
    { ...disponibilidad, reason: 'invented_reason' },
    { ...disponibilidad, conflicting_reservation_ids: '3' },
    { ...disponibilidad, conflicting_reservation_ids: [0] },
  ])("rechaza una respuesta de disponibilidad no válida: %j", async (cuerpo) => {
    peticionSimulada.mockResolvedValue(Response.json(cuerpo));
    await expect(api.obtenerDisponibilidadEquipo(1, { start_date: '2026-11-10', end_date: '2026-11-12' }))
      .rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });
});

describe("cliente de la API de incidencias", () => {
  it("lista incidencias sin filtros opcionales", async () => {
    peticionSimulada.mockResolvedValue(Response.json([incidencia]));
    await expect(api.listarIncidencias()).resolves.toEqual([incidencia]);
    expect(peticionSimulada).toHaveBeenCalledWith('/api/incidents', expect.any(Object));
  });

  it.each([true, false])("serializa los filtros de incidencias incluyendo blocking=%s", async (bloqueante) => {
    peticionSimulada.mockResolvedValue(Response.json([]));
    await expect(api.listarIncidencias({ equipment_id: 1, status: 'in_progress', priority: 'high', blocking: bloqueante }))
      .resolves.toEqual([]);
    expect(peticionSimulada).toHaveBeenCalledWith(
      `/api/incidents?equipment_id=1&status=in_progress&priority=high&blocking=${String(bloqueante)}`,
      expect.any(Object),
    );
  });

  it("omite los filtros de incidencias sin especificar", async () => {
    peticionSimulada.mockResolvedValue(Response.json([incidencia]));
    await api.listarIncidencias({ blocking: false });
    expect(peticionSimulada).toHaveBeenCalledWith('/api/incidents?blocking=false', expect.any(Object));
  });

  it("consulta una incidencia y conserva el aviso de reservas del servidor", async () => {
    const advertido = { ...incidencia, blocking: true, confirmed_reservation_ids: [3], warning: 'Revisa la reserva confirmada 3.' };
    peticionSimulada.mockResolvedValue(Response.json(advertido));
    await expect(api.obtenerIncidencia(4)).resolves.toEqual(advertido);
    expect(peticionSimulada).toHaveBeenCalledWith('/api/incidents/4', expect.any(Object));
  });

  it("crea una incidencia dejando a Python los valores opcionales predeterminados", async () => {
    const entrada = { equipment_id: 1, title: incidencia.title };
    peticionSimulada.mockResolvedValue(Response.json(incidencia, { status: 201 }));
    await expect(api.crearIncidencia(entrada)).resolves.toEqual(incidencia);
    expect(peticionSimulada).toHaveBeenCalledWith('/api/incidents', expect.objectContaining({
      method: 'POST', body: JSON.stringify(entrada),
    }));
    expect(new Headers(peticionSimulada.mock.calls[0]?.[1]?.headers).get('Content-Type')).toBe('application/json');
  });

  it("envía todos los campos de incidencia indicados expresamente sin transformarlos", async () => {
    const entrada = { equipment_id: 1, title: incidencia.title, description: 'Detalle ficticio.', priority: 'low' as const, blocking: false };
    peticionSimulada.mockResolvedValue(Response.json({ ...incidencia, ...entrada }, { status: 201 }));
    await expect(api.crearIncidencia(entrada)).resolves.toMatchObject(entrada);
    expect(peticionSimulada).toHaveBeenCalledWith('/api/incidents', expect.objectContaining({ body: JSON.stringify(entrada) }));
  });

  it.each(['open', 'in_progress', 'resolved'] as const)("envía el estado de destino %s para su validación en el servidor", async (estado) => {
    peticionSimulada.mockResolvedValue(Response.json({ ...incidencia, status: estado }));
    await expect(api.cambiarEstadoIncidencia(4, { status: estado })).resolves.toMatchObject({ status: estado });
    expect(peticionSimulada).toHaveBeenCalledWith('/api/incidents/4/status', expect.objectContaining({
      method: 'PATCH', body: JSON.stringify({ status: estado }),
    }));
  });

  it.each(['Conector reparado en la demostración.', null])("conserva el contenido de resolución %s proporcionado por quien llama", async (resolucion) => {
    peticionSimulada.mockResolvedValue(Response.json({ ...incidencia, status: 'resolved', resolution: resolucion ?? '' }));
    await api.cambiarEstadoIncidencia(4, { status: 'resolved', resolution: resolucion });
    expect(peticionSimulada).toHaveBeenCalledWith('/api/incidents/4/status', expect.objectContaining({
      method: 'PATCH', body: JSON.stringify({ status: 'resolved', resolution: resolucion }),
    }));
  });

  it("conserva un conflicto de transición devuelto por Python", async () => {
    peticionSimulada.mockResolvedValue(Response.json({ detail: 'La transición de estado no está permitida.' }, { status: 409 }));
    await expect(api.cambiarEstadoIncidencia(4, { status: 'open' }))
      .rejects.toMatchObject({ estado: 409, message: 'La transición de estado no está permitida.' });
  });

  it("acepta incidencias bloqueantes como motivo de disponibilidad del servidor", async () => {
    const bloqueado = { ...disponibilidad, available: false, reason: 'blocking_incident' };
    peticionSimulada.mockResolvedValue(Response.json(bloqueado));
    await expect(api.obtenerDisponibilidadEquipo(1, { start_date: '2026-11-10', end_date: '2026-11-12' }))
      .resolves.toEqual(bloqueado);
  });

  it.each([
    { ...incidencia, id: 0 },
    { ...incidencia, equipment_id: 1.5 },
    { ...incidencia, title: null },
    { ...incidencia, description: 42 },
    { ...incidencia, priority: 'urgent' },
    { ...incidencia, blocking: 'false' },
    { ...incidencia, status: 'cancelled' },
    { ...incidencia, resolution: null },
    { ...incidencia, confirmed_reservation_ids: '3' },
    { ...incidencia, confirmed_reservation_ids: [-1] },
    { ...incidencia, warning: false },
  ])("rechaza una respuesta de incidencia no válida: %j", async (cuerpo) => {
    peticionSimulada.mockResolvedValue(Response.json(cuerpo));
    await expect(api.obtenerIncidencia(4)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it("rechaza una lista que contiene una incidencia no válida", async () => {
    peticionSimulada.mockResolvedValue(Response.json([incidencia, { ...incidencia, status: 'invented' }]));
    await expect(api.listarIncidencias()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });
});

describe("cliente de la API de importación de reservas", () => {
  it("expone la URL relativa del ejemplo para un futuro enlace de descarga", () => {
    expect(URL_EJEMPLO_IMPORTACION).toBe('/api/imports/example');
    expect(peticionSimulada).not.toHaveBeenCalled();
  });

  it("sube exactamente un archivo como multipart sin fijar manualmente su separador", async () => {
    const archivo = new File(['contenido CSV ficticio'], 'pedidos.csv', { type: 'text/csv' });
    peticionSimulada.mockResolvedValue(Response.json(informeImportacion));
    await expect(api.importarReservas(archivo)).resolves.toEqual(informeImportacion);
    expect(peticionSimulada).toHaveBeenCalledWith('/api/imports', expect.objectContaining({ method: 'POST', body: expect.any(FormData) }));
    const opciones = peticionSimulada.mock.calls[0]?.[1];
    const cuerpo = opciones?.body as FormData;
    expect(Array.from(cuerpo.keys())).toEqual(['file']);
    expect(cuerpo.get('file')).toBe(archivo);
    expect(new Headers(opciones?.headers).get('Accept')).toBe('application/json');
    expect(new Headers(opciones?.headers).has('Content-Type')).toBe(false);
  });

  it("conserva el tipo de contenido JSON de las solicitudes existentes al añadir multipart", async () => {
    const archivo = new File(['datos ficticios'], 'pedidos.csv');
    peticionSimulada.mockResolvedValueOnce(Response.json(informeImportacion));
    await api.importarReservas(archivo);
    peticionSimulada.mockResolvedValueOnce(Response.json(reserva, { status: 201 }));
    await api.crearReserva(entradaReserva);
    const opciones = peticionSimulada.mock.calls[1]?.[1];
    expect(opciones?.body).toBe(JSON.stringify(entradaReserva));
    expect(new Headers(opciones?.headers).get('Content-Type')).toBe('application/json');
  });

  it("devuelve un informe mixto con filas rechazadas y una reserva cancelada anteriormente", async () => {
    peticionSimulada.mockResolvedValue(Response.json(informeImportacion, { status: 200 }));
    await expect(api.importarReservas(new File(['datos ficticios'], 'pedidos.csv')))
      .resolves.toEqual(informeImportacion);
  });

  it("acepta un informe sin filas importadas", async () => {
    const vacio = { totals: { total: 0, accepted: 0, already_imported: 0, rejected: 0 }, rows: [] };
    peticionSimulada.mockResolvedValue(Response.json(vacio));
    await expect(api.importarReservas(new File(['cabecera CSV ficticia'], 'pedidos.csv')))
      .resolves.toEqual(vacio);
  });

  it.each([
    [413, 'El archivo supera el tamaño permitido.'],
    [422, 'El archivo no contiene las columnas requeridas.'],
  ])("conserva los errores HTTP globales %s de Python", async (estado, mensaje) => {
    peticionSimulada.mockResolvedValue(Response.json({ detail: mensaje }, { status: estado }));
    await expect(api.importarReservas(new File(['datos ficticios'], 'pedidos.csv')))
      .rejects.toMatchObject({ name: 'ApiError', estado, message: mensaje });
  });

  it("mantiene legibles los detalles de validación de FastAPI para errores multipart", async () => {
    peticionSimulada.mockResolvedValue(Response.json({ detail: [{ loc: ['body', 'file'], msg: 'Field required', type: 'missing' }] }, { status: 422 }));
    await expect(api.importarReservas(new File(['datos ficticios'], 'pedidos.csv')))
      .rejects.toThrow('Field required');
  });

  it.each([
    null,
    { ...informeImportacion, totals: null },
    { ...informeImportacion, totals: { ...informeImportacion.totals, total: '3' } },
    { ...informeImportacion, totals: { ...informeImportacion.totals, accepted: -1 } },
    { ...informeImportacion, totals: { ...informeImportacion.totals, already_imported: 0.5 } },
    { ...informeImportacion, totals: { ...informeImportacion.totals, rejected: null } },
    { ...informeImportacion, rows: {} },
    { ...informeImportacion, rows: [{ ...filaImportadaAceptada, line: 0 }] },
    { ...informeImportacion, rows: [{ ...filaImportadaAceptada, external_reference: 1 }] },
    { ...informeImportacion, rows: [{ ...filaImportadaAceptada, status: 'pending' }] },
    { ...informeImportacion, rows: [{ ...filaImportadaAceptada, reservation: { ...reserva, status: 'pending' } }] },
    { ...informeImportacion, rows: [{ ...filaImportadaAceptada, reservation: null }] },
    { ...informeImportacion, rows: [{ ...filaImportadaAceptada, status: 'already_imported', reservation: null }] },
    { ...informeImportacion, rows: [{ ...filaImportadaAceptada, status: 'rejected' }] },
    { ...informeImportacion, rows: [{ ...filaImportadaAceptada, message: null }] },
  ])("rechaza un informe de importación no válido: %j", async (cuerpo) => {
    peticionSimulada.mockResolvedValue(Response.json(cuerpo));
    await expect(api.importarReservas(new File(['datos ficticios'], 'pedidos.csv')))
      .rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });
});
