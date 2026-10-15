import { useEffect, useState } from 'react';
import { api, type CalendarioDisponibilidadPublica } from '../api/cliente';
import { esFechaCalendario, hoyEnMadrid } from './intervaloFechas';

function desplazarMes(mes: string, desplazamiento: number) {
  const fecha = new Date(`${mes}-01T12:00:00Z`);
  fecha.setUTCMonth(fecha.getUTCMonth() + desplazamiento);
  return fecha.toISOString().slice(0, 7);
}

/** Un día está libre sólo si todos los modelos seleccionados pueden alquilarse durante todo el intervalo. */
export function useCalendarioDisponibilidadCompartido(idsEquipos: number[], fechaSeleccionada: string, revision: number) {
  const claveIds = idsEquipos.join(',');
  const mesSeleccionado = esFechaCalendario(fechaSeleccionada) ? fechaSeleccionada.slice(0, 7) : hoyEnMadrid().slice(0, 7);
  const ancla = mesSeleccionado > '9999-11' ? '9999-11' : mesSeleccionado;
  const [navegacion, establecerNavegacion] = useState<{ ancla: string; mes: string } | null>(null);
  const [reintento, establecerReintento] = useState(0);
  const mes = navegacion && (!fechaSeleccionada || navegacion.ancla === ancla) ? navegacion.mes : ancla;
  const inicioReserva = esFechaCalendario(fechaSeleccionada) ? fechaSeleccionada : '';
  const inicioPrefijo = inicioReserva && inicioReserva < `${mes}-01` ? inicioReserva : '';
  const ambito = `${claveIds}:${mes}:${revision}:${reintento}`;
  const key = `${ambito}:${inicioReserva}`;
  const [estadoInterno, establecerEstadoInterno] = useState({ key: '', ambito: '', datos: null as CalendarioDisponibilidadPublica | null, error: null as string | null, cargando: true, puedeAccederMes: false });
  const actual = estadoInterno.key === key ? estadoInterno : null;
  const datosMes = estadoInterno.ambito === ambito ? estadoInterno.datos : null;

  useEffect(() => {
    const controlador = new AbortController();
    let activo = true;
    const ids = claveIds ? claveIds.split(',').map(Number) : [];
    void Promise.resolve().then(async () => {
      if (!activo) return;
      establecerEstadoInterno((anterior) => ({ key, ambito, datos: anterior.ambito === ambito ? anterior.datos : null, error: null, cargando: true, puedeAccederMes: false }));
      if (!ids.length) {
        establecerEstadoInterno({ key, ambito, datos: null, error: null, cargando: false, puedeAccederMes: false });
        return;
      }
      const resultados = await Promise.all(ids.map(async (id) => {
        const [calendario, prefijo] = await Promise.all([
          api.obtenerCalendarioDisponibilidadPublica(id, { start_date: `${mes}-01`, end_date: `${desplazarMes(mes, 1)}-01`, ...(inicioReserva ? { booking_start: inicioReserva } : {}) }, controlador.signal),
          inicioPrefijo ? api.obtenerDisponibilidadPublica(id, { start_date: inicioPrefijo, end_date: `${mes}-01` }, controlador.signal) : null,
        ]);
        return { calendario, prefijo };
      }));
      if (activo) establecerEstadoInterno({ key, ambito, cargando: false, error: null,
        puedeAccederMes: resultados.every(({ prefijo }) => !prefijo || prefijo.available === true),
        datos: { equipment_id: ids[0]!, start_date: `${mes}-01`, end_date: `${desplazarMes(mes, 1)}-01`,
          can_book: resultados.every(({ calendario }) => calendario.can_book),
          occupied_ranges: resultados.flatMap(({ calendario }) => calendario.occupied_ranges),
          unavailable_end_dates: [...new Set(resultados.flatMap(({ calendario }) => calendario.unavailable_end_dates ?? []))],
        },
      });
    }).catch((fallo: unknown) => {
      if (activo) establecerEstadoInterno({ key, ambito, datos: null, cargando: false, puedeAccederMes: false, error: fallo instanceof Error ? fallo.message : 'No se pudo consultar el calendario conjunto.' });
    });
    return () => { activo = false; controlador.abort(); };
  }, [claveIds, mes, inicioReserva, inicioPrefijo, ambito, key]);

  return { mes, datos: actual?.datos ?? datosMes, error: actual?.error ?? null, cargando: !actual || actual.cargando, puedeAccederMes: actual?.puedeAccederMes ?? false,
    anterior: () => establecerNavegacion({ ancla, mes: desplazarMes(mes, -1) }),
    siguiente: () => establecerNavegacion({ ancla, mes: desplazarMes(mes, 1) }),
    irA: (destinoObjetivo: string) => { if (/^\d{4}-(0[1-9]|1[0-2])$/.test(destinoObjetivo)) establecerNavegacion({ ancla, mes: destinoObjetivo < '0001-01' ? '0001-01' : destinoObjetivo > '9999-11' ? '9999-11' : destinoObjetivo }); },
    reintento: () => establecerReintento((valor) => valor + 1),
  };
}
