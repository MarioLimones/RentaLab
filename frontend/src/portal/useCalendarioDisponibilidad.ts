import { useEffect, useState } from 'react';
import { api, type CalendarioDisponibilidadPublica } from '../api/cliente';
import { esFechaCalendario, hoyEnMadrid } from './intervaloFechas';

interface EstadoCalendario {
  key: string;
  ambito: string;
  datos: CalendarioDisponibilidadPublica | null;
  error: string | null;
  cargando: boolean;
  puedeAccederMes: boolean;
}

function desplazarMes(mes: string, desplazamiento: number): string {
  const fecha = new Date(`${mes}-01T12:00:00Z`);
  fecha.setUTCMonth(fecha.getUTCMonth() + desplazamiento);
  return fecha.toISOString().slice(0, 7);
}

export function useCalendarioDisponibilidad(idEquipo: number, fechaSeleccionada: string, revision: number, comprobarDesdeInicio = false) {
  const mesSeleccionado = esFechaCalendario(fechaSeleccionada) ? fechaSeleccionada.slice(0, 7) : hoyEnMadrid().slice(0, 7);
  const ancla = mesSeleccionado > '9999-11' ? '9999-11' : mesSeleccionado < '0001-01' ? '0001-01' : mesSeleccionado;
  const [navegacion, establecerNavegacion] = useState<{ ancla: string; mes: string } | null>(null);
  const [reintento, establecerReintento] = useState(0);
  const [estadoInterno, establecerEstadoInterno] = useState<EstadoCalendario>({ key: '', ambito: '', datos: null, error: null, cargando: true, puedeAccederMes: false });
  const mes = navegacion && (!fechaSeleccionada || navegacion.ancla === ancla) ? navegacion.mes : ancla;
  // La ocupación se recorta por mes. Comprueba el intervalo anterior antes de ofrecer una devolución en un mes posterior.
  const inicioReserva = comprobarDesdeInicio && esFechaCalendario(fechaSeleccionada) ? fechaSeleccionada : '';
  const inicioPrefijo = comprobarDesdeInicio && esFechaCalendario(fechaSeleccionada) && fechaSeleccionada < `${mes}-01` ? fechaSeleccionada : '';
  const ambito = `${idEquipo}:${mes}:${revision}:${reintento}`;
  const key = `${ambito}:${inicioReserva}:${inicioPrefijo}`;
  const actual = estadoInterno.key === key ? estadoInterno : null;
  const datosMes = estadoInterno.ambito === ambito ? estadoInterno.datos : null;

  useEffect(() => {
    const controlador = new AbortController();
    let activo = true;
    void Promise.resolve().then(async () => {
      if (!activo) return;
      // Mantén la misma cuadrícula al comprobar devoluciones para una nueva recogida, conservando el foco del teclado.
      establecerEstadoInterno((anterior) => ({ key, ambito, datos: anterior.ambito === ambito ? anterior.datos : null, error: null, cargando: true, puedeAccederMes: false }));
      const [datos, prefijo] = await Promise.all([
        api.obtenerCalendarioDisponibilidadPublica(idEquipo, { start_date: `${mes}-01`, end_date: `${desplazarMes(mes, 1)}-01`, ...(inicioReserva ? { booking_start: inicioReserva } : {}) }, controlador.signal),
        inicioPrefijo ? api.obtenerDisponibilidadPublica(idEquipo, { start_date: inicioPrefijo, end_date: `${mes}-01` }, controlador.signal) : null,
      ]);
      if (activo) establecerEstadoInterno({ key, ambito, datos, error: null, cargando: false, puedeAccederMes: !prefijo || prefijo.available === true });
    }).catch((error: unknown) => {
      if (activo) establecerEstadoInterno({ key, ambito, datos: null, error: error instanceof Error ? error.message : 'No se pudo cargar el calendario.', cargando: false, puedeAccederMes: false });
    });
    return () => { activo = false; controlador.abort(); };
  }, [idEquipo, mes, inicioReserva, inicioPrefijo, ambito, key]);

  return {
    mes, datos: actual?.datos ?? datosMes, error: actual?.error ?? null, cargando: !actual || actual.cargando, puedeAccederMes: actual?.puedeAccederMes ?? false,
    anterior: () => establecerNavegacion({ ancla, mes: desplazarMes(mes, -1) }),
    siguiente: () => establecerNavegacion({ ancla, mes: desplazarMes(mes, 1) }),
    irA: (destinoObjetivo: string) => {
      if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(destinoObjetivo)) return;
      establecerNavegacion({ ancla, mes: destinoObjetivo < '0001-01' ? '0001-01' : destinoObjetivo > '9999-11' ? '9999-11' : destinoObjetivo });
    },
    reintento: () => establecerReintento((valor) => valor + 1),
  };
}
