import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import type { IntervaloFechas } from '../api/cliente';
import { formatearFecha } from '../utilidades/fechas';
import { completarIntervaloFechas, esFechaCalendario, hoyEnMadrid } from './intervaloFechas';
import './selector-fechas-catalogo.css';

type CampoFecha = keyof IntervaloFechas;
interface VistaCalendario { campo: CampoFecha; mes: string; enfocado: string; }
const diasSemana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

function IconoCalendario() {
  return <svg aria-hidden="true" viewBox="0 0 20 20" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><rect x="3" y="4" width="14" height="13" rx="2" /><path d="M6 2v4m8-4v4M3 8h14m-9 4h4" /></svg>;
}

export function SelectorFechasCatalogo({ valor, onChange: alCambiar, errores = {}, deshabilitado = false }: {
  valor: IntervaloFechas;
  onChange: (intervalo: IntervaloFechas) => void;
  errores?: Record<string, string>;
  deshabilitado?: boolean;
}) {
  const id = useId();
  const raiz = useRef<HTMLFieldSetElement>(null);
  const tabla = useRef<HTMLTableElement>(null);
  const activadorInicio = useRef<HTMLButtonElement>(null);
  const activadorFin = useRef<HTMLButtonElement>(null);
  const devolverEnfoque = useRef<HTMLButtonElement | null>(null);
  const enfoquePendiente = useRef<string | null>(null);
  const [vista, establecerVista] = useState<VistaCalendario | null>(null);
  const [vistaPrevia, establecerVistaPrevia] = useState<{ fecha: string; contexto: string } | null>(null);
  const abierto = !!vista && !deshabilitado;
  const hoy = hoyEnMadrid();
  const mes = vista?.mes ?? hoy.slice(0, 7);
  const primero = new Date(`${mes}-01T12:00:00Z`);
  const ultimo = new Date(primero);
  ultimo.setUTCMonth(ultimo.getUTCMonth() + 1, 0);
  const etiqueta = new Intl.DateTimeFormat('es-ES', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(primero);
  const desplazamiento = (primero.getUTCDay() + 6) % 7;
  const semanas = Array.from({ length: Math.ceil((desplazamiento + ultimo.getUTCDate()) / 7) }, (_, semana) => Array.from({ length: 7 }, (_, diaSemana) => {
    const dia = semana * 7 + diaSemana - desplazamiento + 1;
    return dia > 0 && dia <= ultimo.getUTCDate() ? dia : null;
  }));
  const intervaloValido = completarIntervaloFechas(valor);
  const contextoVistaPrevia = `${mes}:${vista?.campo}:${valor.start_date}:${valor.end_date}`;
  const finVistaPrevia = abierto && vista.campo === 'end_date' && esFechaCalendario(valor.start_date)
    && vistaPrevia?.contexto === contextoVistaPrevia && vistaPrevia.fecha > valor.start_date ? vistaPrevia.fecha : null;

  function fechaVistaPrevia(fecha: string, mesObjetivo = mes) {
    establecerVistaPrevia(vista?.campo === 'end_date' && esFechaCalendario(valor.start_date) && fecha > valor.start_date
      ? { fecha, contexto: `${mesObjetivo}:${vista.campo}:${valor.start_date}:${valor.end_date}` } : null);
  }

  useEffect(() => {
    if (!abierto) return;
    const descartar = (evento: PointerEvent) => {
      if (evento.target instanceof Node && !raiz.current?.contains(evento.target)) establecerVista(null);
    };
    document.addEventListener('pointerdown', descartar);
    return () => document.removeEventListener('pointerdown', descartar);
  }, [abierto]);

  useEffect(() => {
    if (abierto && enfoquePendiente.current) {
      tabla.current?.querySelector<HTMLButtonElement>(`[data-date="${enfoquePendiente.current}"]`)?.focus();
      enfoquePendiente.current = null;
    }
  }, [abierto, mes, vista?.enfocado]);

  function mostrar(campo: CampoFecha) {
    establecerVistaPrevia(null);
    const activador = campo === 'start_date' ? activadorInicio.current : activadorFin.current;
    if (abierto && vista.campo === campo) { establecerVista(null); return; }
    const seleccionado = [valor[campo], valor.start_date, hoy].find(esFechaCalendario) ?? hoy;
    devolverEnfoque.current = activador;
    enfoquePendiente.current = seleccionado;
    establecerVista({ campo: campo === 'end_date' && !esFechaCalendario(valor.start_date) ? 'start_date' : campo, mes: seleccionado.slice(0, 7), enfocado: seleccionado });
  }

  function cerrar() {
    establecerVistaPrevia(null);
    establecerVista(null);
    devolverEnfoque.current?.focus();
  }

  function elegir(fecha: string) {
    if (!vista || deshabilitado) return;
    establecerVistaPrevia(null);
    if (vista.campo === 'end_date' && esFechaCalendario(valor.start_date) && fecha > valor.start_date) {
      alCambiar({ start_date: valor.start_date, end_date: fecha });
      establecerVista(null);
      activadorFin.current?.focus();
    } else {
      alCambiar({ start_date: fecha, end_date: '' });
      establecerVista({ ...vista, campo: 'end_date', enfocado: fecha });
    }
  }

  function cambiarMes(importe: number) {
    if (!vista) return;
    establecerVistaPrevia(null);
    const destinoObjetivo = new Date(`${vista.mes}-01T12:00:00Z`);
    destinoObjetivo.setUTCMonth(destinoObjetivo.getUTCMonth() + importe);
    if (destinoObjetivo.getUTCFullYear() < 1 || destinoObjetivo.getUTCFullYear() > 9999) return;
    const fecha = destinoObjetivo.toISOString().slice(0, 10);
    establecerVista({ ...vista, mes: fecha.slice(0, 7), enfocado: fecha });
  }

  function moverEnfoque(evento: KeyboardEvent<HTMLButtonElement>, fecha: string) {
    if (!vista) return;
    const destinoObjetivo = new Date(`${fecha}T12:00:00Z`);
    const diaSemana = (destinoObjetivo.getUTCDay() + 6) % 7;
    const desplazamientos: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -diaSemana, End: 6 - diaSemana };
    if (evento.key in desplazamientos) destinoObjetivo.setUTCDate(destinoObjetivo.getUTCDate() + desplazamientos[evento.key]!);
    else if (evento.key === 'PageUp' || evento.key === 'PageDown') {
      const dia = destinoObjetivo.getUTCDate();
      destinoObjetivo.setUTCDate(1);
      destinoObjetivo.setUTCMonth(destinoObjetivo.getUTCMonth() + (evento.key === 'PageUp' ? -1 : 1));
      const fin = new Date(destinoObjetivo);
      fin.setUTCMonth(fin.getUTCMonth() + 1, 0);
      destinoObjetivo.setUTCDate(Math.min(dia, fin.getUTCDate()));
    } else return;
    evento.preventDefault();
    if (destinoObjetivo.getUTCFullYear() < 1 || destinoObjetivo.getUTCFullYear() > 9999) return;
    const siguiente = destinoObjetivo.toISOString().slice(0, 10);
    fechaVistaPrevia(siguiente, siguiente.slice(0, 7));
    enfoquePendiente.current = siguiente;
    establecerVista({ ...vista, mes: siguiente.slice(0, 7), enfocado: siguiente });
  }

  return <fieldset ref={raiz} className="catalogue-date-picker" disabled={deshabilitado} onKeyDown={(evento) => { if (evento.key === 'Escape' && abierto) { evento.preventDefault(); evento.stopPropagation(); cerrar(); } }} onBlur={(evento) => {
    if (abierto && evento.relatedTarget instanceof Node && !evento.currentTarget.contains(evento.relatedTarget)) establecerVista(null);
  }}>
    <legend className="sr-only">Fechas del alquiler</legend>
    {(['start_date', 'end_date'] as const).map((campo) => <div className="field catalogue-date-field" key={campo}>
      <label htmlFor={campo}>{campo === 'start_date' ? 'Fecha de inicio' : 'Fecha de fin'}</label>
      <button ref={campo === 'start_date' ? activadorInicio : activadorFin} id={campo} type="button" className={`catalogue-date-trigger${abierto && vista.campo === campo ? ' is-open' : ''}`} aria-label={`${campo === 'start_date' ? 'Fecha de inicio' : 'Fecha de fin'}: ${valor[campo] ? formatearFecha(valor[campo]) : 'Elegir fecha'}`} aria-haspopup="dialog" aria-expanded={abierto && vista.campo === campo} aria-controls={abierto ? `${id}-calendar` : undefined} aria-invalid={!!errores[campo]} aria-describedby={[campo === 'end_date' ? `${id}-return-help` : '', errores[campo] ? `${id}-${campo}-error` : ''].filter(Boolean).join(' ') || undefined} onClick={() => mostrar(campo)}><span className={valor[campo] ? '' : 'catalogue-date-placeholder'}>{valor[campo] ? formatearFecha(valor[campo]) : 'Elegir fecha'}</span><IconoCalendario /></button>
      {campo === 'end_date' && <p className="field-hint" id={`${id}-return-help`}>Día de devolución, no incluido en el alquiler.</p>}
      {errores[campo] && <p className="field-error" id={`${id}-${campo}-error`}>{errores[campo]}</p>}
    </div>)}
    {abierto && <div id={`${id}-calendar`} className="catalogue-date-popover" role="dialog" aria-label="Fechas del alquiler">
      <div className="catalogue-date-popover-heading"><div><p>Fechas del alquiler</p><span aria-live="polite">{vista.campo === 'start_date' ? 'Elige el día de recogida' : 'Elige el día de devolución'}</span></div><button className="catalogue-date-icon-button" type="button" aria-label="Cerrar calendario" onClick={cerrar}><svg aria-hidden="true" viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="m5 5 10 10M15 5 5 15" /></svg></button></div>
      <div className="catalogue-date-navigation"><p aria-live="polite">{etiqueta}</p><div>{[-1, 1].map((importe) => <button key={importe} type="button" className="catalogue-date-icon-button" aria-label={importe === -1 ? 'Mes anterior' : 'Mes siguiente'} disabled={importe === -1 ? mes <= '0001-01' : mes >= '9999-12'} onClick={() => cambiarMes(importe)}><svg aria-hidden="true" viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={importe === -1 ? 'm12 5-5 5 5 5' : 'm8 5 5 5-5 5'} /></svg></button>)}</div></div>
      <table ref={tabla} className="catalogue-date-table" onPointerLeave={() => establecerVistaPrevia(null)} onBlur={(evento) => { if (!evento.currentTarget.contains(evento.relatedTarget)) establecerVistaPrevia(null); }} aria-describedby={`${id}-calendar-help`}>
        <caption className="sr-only">{etiqueta}</caption>
        <thead><tr>{diasSemana.map((dia) => <th scope="col" key={dia}><abbr title={dia}>{dia.slice(0, 2)}</abbr></th>)}</tr></thead>
        <tbody>{semanas.map((semana, indice) => <tr key={indice}>{semana.map((dia, diaSemana) => {
          if (!dia) return <td key={diaSemana} />;
          const fecha = `${mes}-${String(dia).padStart(2, '0')}`;
          const inicio = valor.start_date === fecha;
          const fin = valor.end_date === fecha;
          const entre = intervaloValido && fecha > valor.start_date && fecha < valor.end_date;
          const enVistaPrevia = !!finVistaPrevia && fecha > valor.start_date && fecha < finVistaPrevia;
          return <td key={diaSemana} className={[inicio || fin ? 'is-endpoint' : entre ? 'is-in-range' : '', fecha < hoy ? 'is-past' : '', enVistaPrevia ? 'is-preview' : '', fecha === finVistaPrevia ? 'is-preview-end' : ''].filter(Boolean).join(' ')}><button type="button" data-date={fecha} tabIndex={fecha === vista.enfocado ? 0 : -1} aria-label={formatearFecha(fecha)} aria-current={fecha === hoy ? 'date' : undefined} aria-pressed={inicio || fin || entre} onPointerEnter={(evento) => { if (evento.pointerType === 'mouse' || evento.pointerType === 'pen') fechaVistaPrevia(fecha); }} onFocus={(evento) => { establecerVista((anterior) => anterior && anterior.enfocado !== fecha ? { ...anterior, enfocado: fecha } : anterior); if (evento.currentTarget.matches(':focus-visible')) fechaVistaPrevia(fecha); }} onKeyDown={(evento) => moverEnfoque(evento, fecha)} onClick={() => elegir(fecha)}><time dateTime={fecha}>{dia}</time></button></td>;
        })}</tr>)}</tbody>
      </table>
      <p className="catalogue-date-calendar-help" id={`${id}-calendar-help`}>La devolución no cuenta como día de alquiler.<span className="sr-only"> Usa las flechas para recorrer los días, Inicio y Fin para la semana, Re Pág o Av Pág para cambiar de mes e Intro para elegir.</span></p>
      <div className="catalogue-date-footer"><button type="button" onClick={() => { enfoquePendiente.current = hoy; establecerVista({ ...vista, mes: hoy.slice(0, 7), enfocado: hoy }); }}>Hoy</button><button type="button" disabled={!valor.start_date && !valor.end_date} onClick={() => { alCambiar({ start_date: '', end_date: '' }); establecerVista(null); activadorInicio.current?.focus(); }}>Borrar fechas</button></div>
    </div>}
  </fieldset>;
}
