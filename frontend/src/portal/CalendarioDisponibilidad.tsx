import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import type { IntervaloFechas } from '../api/cliente';
import { formatearFecha } from '../utilidades/fechas';
import { completarIntervaloFechas, esFechaCalendario, hoyEnMadrid } from './intervaloFechas';
import type { useCalendarioDisponibilidad } from './useCalendarioDisponibilidad';
import './calendario-disponibilidad.css';

const diasSemana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

function IndicadorDesplegable({ siguiente = false }: { siguiente?: boolean }) {
  return <svg aria-hidden="true" viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={siguiente ? 'm8 5 5 5-5 5' : 'm12 5-5 5 5 5'} /></svg>;
}

export function CalendarioDisponibilidad({ calendario, intervalo, onChange: alCambiar, deshabilitado = false, errores = {}, titulo = 'Disponibilidad del equipo' }: {
  calendario: ReturnType<typeof useCalendarioDisponibilidad>;
  intervalo?: IntervaloFechas;
  onChange?: (intervalo: IntervaloFechas) => void;
  deshabilitado?: boolean;
  errores?: Record<string, string>;
  titulo?: string;
}) {
  const id = useId();
  const { mes, datos, cargando, error } = calendario;
  const hoy = hoyEnMadrid();
  const claveSeleccion = `${intervalo?.start_date ?? ''}:${intervalo?.end_date ?? ''}`;
  const [seleccion, establecerSeleccion] = useState<{ key: string; campo: 'start' | 'end' } | null>(null);
  const seleccionando = seleccion?.key === claveSeleccion ? seleccion.campo : intervalo?.start_date && !intervalo.end_date ? 'end' : 'start';
  const [fechaEnfocada, establecerFechaEnfocada] = useState('');
  const [vistaPrevia, establecerVistaPrevia] = useState<{ fecha: string; contexto: string; datos: typeof datos } | null>(null);
  const enfoquePendiente = useRef<string | null>(null);
  const tabla = useRef<HTMLTableElement>(null);
  const interactivo = !!intervalo && !!alCambiar;
  const intervaloValido = !!intervalo && completarIntervaloFechas(intervalo);
  const contextoVistaPrevia = `${mes}:${claveSeleccion}:${seleccionando}`;
  const finVistaPrevia = interactivo && !deshabilitado && !cargando && !error && seleccionando === 'end'
    && esFechaCalendario(intervalo.start_date) && intervalo.start_date >= hoy
    && datos?.can_book && calendario.puedeAccederMes && vistaPrevia?.contexto === contextoVistaPrevia && vistaPrevia.datos === datos
    && vistaPrevia.fecha > intervalo.start_date && !datos.unavailable_end_dates?.includes(vistaPrevia.fecha)
    && !datos.occupied_ranges.some((periodo) => periodo.start_date < vistaPrevia.fecha && periodo.end_date > intervalo.start_date)
    ? vistaPrevia.fecha : null;
  const primero = new Date(`${mes}-01T12:00:00Z`);
  const etiqueta = new Intl.DateTimeFormat('es-ES', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(primero);
  const desplazamiento = (primero.getUTCDay() + 6) % 7;
  const ultimo = new Date(primero);
  ultimo.setUTCMonth(ultimo.getUTCMonth() + 1, 0);
  const dias = ultimo.getUTCDate();
  const semanas = Array.from({ length: Math.ceil((desplazamiento + dias) / 7) }, (_, semana) => Array.from({ length: 7 }, (_, diaSemana) => {
    const dia = semana * 7 + diaSemana - desplazamiento + 1;
    return dia > 0 && dia <= dias ? dia : null;
  }));
  const fechaTabulacion = [fechaEnfocada, intervalo?.start_date, hoy].find((fecha) => fecha?.startsWith(`${mes}-`)) ?? `${mes}-01`;

  useEffect(() => {
    if (!cargando && datos && enfoquePendiente.current) {
      tabla.current?.querySelector<HTMLButtonElement>(`[data-date="${enfoquePendiente.current}"]`)?.focus();
      enfoquePendiente.current = null;
    }
    if (error) enfoquePendiente.current = null;
  }, [mes, cargando, datos, error]);

  function seleccionarFecha(fecha: string) {
    if (!intervalo || !alCambiar || deshabilitado) return;
    establecerVistaPrevia(null);
    const siguiente = seleccionando === 'end' && esFechaCalendario(intervalo.start_date) && fecha > intervalo.start_date
      ? { start_date: intervalo.start_date, end_date: fecha }
      : { start_date: fecha, end_date: '' };
    establecerSeleccion({ key: `${siguiente.start_date}:${siguiente.end_date}`, campo: siguiente.end_date ? 'start' : 'end' });
    establecerFechaEnfocada(fecha);
    alCambiar(siguiente);
  }

  function moverEnfoque(evento: KeyboardEvent<HTMLButtonElement>, fecha: string) {
    const destinoObjetivo = new Date(`${fecha}T12:00:00Z`);
    const diaSemana = (destinoObjetivo.getUTCDay() + 6) % 7;
    const desplazamientos: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -diaSemana, End: 6 - diaSemana };
    if (evento.key in desplazamientos) destinoObjetivo.setUTCDate(destinoObjetivo.getUTCDate() + desplazamientos[evento.key]!);
    else if (evento.key === 'PageUp' || evento.key === 'PageDown') {
      const dia = destinoObjetivo.getUTCDate();
      destinoObjetivo.setUTCDate(1);
      destinoObjetivo.setUTCMonth(destinoObjetivo.getUTCMonth() + (evento.key === 'PageUp' ? -1 : 1));
      const finMes = new Date(destinoObjetivo);
      finMes.setUTCMonth(finMes.getUTCMonth() + 1, 0);
      destinoObjetivo.setUTCDate(Math.min(dia, finMes.getUTCDate()));
    } else return;
    evento.preventDefault();
    if (destinoObjetivo.getUTCFullYear() < 1 || destinoObjetivo.getUTCFullYear() > 9999) return;
    const siguiente = destinoObjetivo.toISOString().slice(0, 10);
    if (siguiente > '9999-11-30') return;
    establecerFechaEnfocada(siguiente);
    fechaVistaPrevia(siguiente, true);
    if (siguiente.slice(0, 7) !== mes) {
      enfoquePendiente.current = siguiente;
      calendario.irA(siguiente.slice(0, 7));
    } else tabla.current?.querySelector<HTMLButtonElement>(`[data-date="${siguiente}"]`)?.focus();
  }

  function editarFecha(campo: 'start' | 'end') {
    establecerVistaPrevia(null);
    establecerSeleccion({ key: claveSeleccion, campo: campo === 'end' && !esFechaCalendario(intervalo?.start_date ?? '') ? 'start' : campo });
    const fecha = campo === 'start' ? intervalo?.start_date : intervalo?.end_date || intervalo?.start_date;
    if (fecha) calendario.irA(fecha.slice(0, 7));
  }

  function fechaVistaPrevia(fecha: string, permitido: boolean) {
    establecerVistaPrevia(permitido && !deshabilitado && seleccionando === 'end' && intervalo && fecha > intervalo.start_date
      ? { fecha, contexto: contextoVistaPrevia, datos } : null);
  }

  return <section className="availability-calendar" aria-labelledby={`${id}-title`}>
    <h3 id={`${id}-title`} className="availability-calendar-heading"><svg aria-hidden="true" viewBox="0 0 20 20" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><rect x="3" y="4" width="14" height="13" rx="2" /><path d="M6 2v4m8-4v4M3 8h14m-9 4h4" /></svg>{titulo}</h3>
    {interactivo && <>
      <div className="calendar-date-summary" role="group" aria-label="Fechas del alquiler">
        <div className="calendar-date-field"><button type="button" id="start_date" className={seleccionando === 'start' ? 'is-editing' : ''} disabled={deshabilitado} aria-pressed={seleccionando === 'start'} aria-invalid={!!errores.start_date} aria-describedby={errores.start_date ? `${id}-start-error` : undefined} aria-label={`Fecha de inicio: ${intervalo.start_date ? formatearFecha(intervalo.start_date) : 'Elegir día'}`} onClick={() => editarFecha('start')}><span>Recogida</span><strong>{intervalo.start_date ? formatearFecha(intervalo.start_date) : 'Elegir día'}</strong></button>{errores.start_date && <p className="field-error" id={`${id}-start-error`}>{errores.start_date}</p>}</div>
        <span className="calendar-date-arrow" aria-hidden="true">→</span>
        <div className="calendar-date-field"><button type="button" id="end_date" className={seleccionando === 'end' ? 'is-editing' : ''} disabled={deshabilitado} aria-pressed={seleccionando === 'end'} aria-invalid={!!errores.end_date} aria-describedby={errores.end_date ? `${id}-end-error` : undefined} aria-label={`Fecha de devolución: ${intervalo.end_date ? formatearFecha(intervalo.end_date) : 'Elegir día'}`} onClick={() => editarFecha('end')}><span>Devolución</span><strong>{intervalo.end_date ? formatearFecha(intervalo.end_date) : 'Elegir día'}</strong></button>{errores.end_date && <p className="field-error" id={`${id}-end-error`}>{errores.end_date}</p>}</div>
      </div>
      <div className="calendar-selection-hint"><p aria-live="polite">{seleccionando === 'end' ? '2. Elige el día de devolución' : intervaloValido ? 'Tus fechas están seleccionadas' : '1. Elige el día de recogida'}</p>{(intervalo.start_date || intervalo.end_date) && <button type="button" disabled={deshabilitado} onClick={() => { calendario.irA(mes); establecerSeleccion(null); alCambiar({ start_date: '', end_date: '' }); }}>Cambiar fechas</button>}</div>
    </>}
    <div className="availability-calendar-navigation">
      <p aria-live="polite">{etiqueta}</p>
      <div><button type="button" aria-label="Mes anterior" onClick={calendario.anterior} disabled={deshabilitado || mes <= '0001-01'}><IndicadorDesplegable /></button><button type="button" aria-label="Mes siguiente" onClick={calendario.siguiente} disabled={deshabilitado || mes >= '9999-11'}><IndicadorDesplegable siguiente /></button></div>
    </div>
    {cargando && !datos ? <div className="calendar-loading" role="status"><span className="calendar-loading-mark" aria-hidden="true" />Cargando disponibilidad…</div> : error ? <div className="calendar-load-error"><p role="alert">No se pudo actualizar el calendario. {error}</p><button type="button" className="button button-secondary" onClick={calendario.reintento}>Reintentar calendario</button></div> : datos && <>
      {cargando && <p role="status" className="availability-calendar-help">Actualizando disponibilidad…</p>}
      {!datos.can_book && <p className="availability-calendar-blocked">Este equipo no admite nuevas reservas en este momento. Consulta otro equipo o vuelve más adelante.</p>}
      <table ref={tabla} className="availability-calendar-table" aria-busy={cargando || undefined} onPointerLeave={() => establecerVistaPrevia(null)} onBlur={(evento) => { if (!evento.currentTarget.contains(evento.relatedTarget)) establecerVistaPrevia(null); }} aria-describedby={`${id}-legend ${id}-help${interactivo ? ` ${id}-keyboard` : ''}`}>
        <caption className="sr-only">Ocupación de {etiqueta}</caption>
        <thead><tr>{diasSemana.map((dia) => <th scope="col" key={dia}><abbr title={dia}>{dia.slice(0, 2)}</abbr></th>)}</tr></thead>
        <tbody>{semanas.map((semana, indice) => <tr key={indice}>{semana.map((dia, diaSemana) => {
          if (!dia) return <td key={diaSemana} />;
          const fecha = `${mes}-${String(dia).padStart(2, '0')}`;
          const reservado = datos.occupied_ranges.some((periodo) => periodo.start_date <= fecha && fecha < periodo.end_date);
          const pasado = fecha < hoy;
          const finalizando = seleccionando === 'end' && !!intervalo?.start_date && fecha > intervalo.start_date;
          const finNoDisponible = finalizando && datos.unavailable_end_dates?.includes(fecha);
          const cruzaOcupacion = finalizando && (!calendario.puedeAccederMes || finNoDisponible || datos.occupied_ranges.some((periodo) => periodo.start_date < fecha && periodo.end_date > intervalo.start_date));
          const devolucionPosible = finalizando && reservado && !cruzaOcupacion && datos.can_book && !pasado;
          const noDisponible = cargando || !datos.can_book || pasado || (reservado && !devolucionPosible) || cruzaOcupacion;
          const inicio = intervalo?.start_date === fecha;
          const fin = intervalo?.end_date === fecha;
          const enIntervalo = intervaloValido && fecha > intervalo.start_date && fecha < intervalo.end_date;
          const enVistaPrevia = !!finVistaPrevia && !!intervalo && fecha > intervalo.start_date && fecha < finVistaPrevia;
          const rutaServicioVistaPrevia = fecha === finVistaPrevia;
          const estado = reservado ? 'Ocupado' : !datos.can_book ? 'No admite reservas' : pasado ? 'Fecha pasada' : finNoDisponible ? 'No disponible para esta devolución' : 'Disponible';
          const nombreAccesible = `${formatearFecha(fecha)}: ${estado}`;
          const clases = ['calendar-day', reservado ? 'calendar-day-occupied' : !datos.can_book || finNoDisponible ? 'calendar-day-blocked' : pasado ? 'calendar-day-past' : 'calendar-day-available', devolucionPosible ? 'calendar-day-return' : '', inicio ? 'calendar-day-start' : '', fin ? 'calendar-day-end' : '', enIntervalo ? 'calendar-day-in-range' : '', enVistaPrevia ? 'calendar-day-preview' : '', rutaServicioVistaPrevia ? 'calendar-day-preview-end' : ''].filter(Boolean).join(' ');
          return <td key={diaSemana} className={clases} aria-label={nombreAccesible}>
            {interactivo ? <button type="button" data-date={fecha} tabIndex={fecha === fechaTabulacion ? 0 : -1} aria-label={`${nombreAccesible}${devolucionPosible ? '. Devolución posible' : finNoDisponible ? '. El periodo no está disponible desde la recogida seleccionada' : cruzaOcupacion ? '. El periodo cruza días ocupados' : ''}${inicio ? '. Recogida seleccionada' : fin ? '. Devolución seleccionada' : ''}`} aria-current={fecha === hoy ? 'date' : undefined} aria-pressed={inicio || fin || enIntervalo} aria-disabled={noDisponible || undefined} disabled={deshabilitado} onPointerEnter={(evento) => { if (evento.pointerType === 'mouse' || evento.pointerType === 'pen') fechaVistaPrevia(fecha, !noDisponible); }} onFocus={(evento) => { establecerFechaEnfocada(fecha); if (evento.currentTarget.matches(':focus-visible')) fechaVistaPrevia(fecha, !noDisponible); }} onClick={() => { if (!noDisponible) seleccionarFecha(fecha); }} onKeyDown={(evento) => moverEnfoque(evento, fecha)}><time dateTime={fecha}>{dia}</time><span className="calendar-day-indicator" aria-hidden="true" /></button> : <time dateTime={fecha}>{dia}</time>}
          </td>;
        })}</tr>)}</tbody>
      </table>
      <div className="availability-calendar-legend" id={`${id}-legend`}><span><span className={`calendar-legend-swatch ${datos.can_book ? 'calendar-swatch-available' : 'calendar-swatch-blocked'}`} aria-hidden="true" />{datos.can_book ? 'Disponible' : 'No admite reservas'}</span><span><span className="calendar-legend-swatch calendar-swatch-occupied" aria-hidden="true" />Ocupado</span>{interactivo && <span><span className="calendar-legend-swatch calendar-swatch-selected" aria-hidden="true" />Tus fechas</span>}</div>
    </>}
    <p className="availability-calendar-help" id={`${id}-help`}>La devolución no cuenta como día de alquiler.{interactivo && seleccionando === 'end' && !!datos?.unavailable_end_dates?.length && ' Los días desactivados no permiten reservar todo el periodo desde la recogida.'}</p>
    {interactivo && <p id={`${id}-keyboard`} className="sr-only">Usa las flechas para recorrer los días, Inicio y Fin para la semana, y Re Pág o Av Pág para cambiar de mes. Pulsa Intro para elegir una fecha.</p>}
  </section>;
}
