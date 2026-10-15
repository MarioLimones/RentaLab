import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { IntervaloFechas } from '../api/cliente';
import { SelectorFechasCatalogo } from './SelectorFechasCatalogo';
import * as intervaloFechas from './intervaloFechas';

function Selector({ intervaloInicial = { start_date: '', end_date: '' }, errors: errores, disabled: deshabilitado = false, onChange: alCambiar }: {
  intervaloInicial?: IntervaloFechas;
  errors?: Record<string, string>;
  disabled?: boolean;
  onChange?: (intervalo: IntervaloFechas) => void;
}) {
  const [valor, establecerValor] = useState(intervaloInicial);
  return <>
    <SelectorFechasCatalogo valor={valor} errores={errores ?? {}} deshabilitado={deshabilitado} onChange={(siguiente) => { establecerValor(siguiente); alCambiar?.(siguiente); }} />
    <button type="button">Otro filtro</button>
  </>;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(intervaloFechas, 'hoyEnMadrid').mockReturnValue('2027-11-01');
});

describe("selector de fechas de alquiler del catálogo", () => {
  it("previsualiza todos los días intermedios al pasar el puntero sin elegir devolución y los limpia al salir", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<Selector intervaloInicial={{ start_date: '2027-11-15', end_date: '' }} onChange={cambiado} />);
    await usuario.click(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' }));
    const rutaServicio = screen.getByRole('button', { name: '22/11/2027' });
    await usuario.hover(rutaServicio);
    for (const dia of ['16', '17', '18', '19', '20', '21']) {
      const boton = screen.getByRole('button', { name: `${dia}/11/2027` });
      expect(boton.closest('td')).toHaveClass('is-preview');
      expect(boton).toHaveAttribute('aria-pressed', 'false');
    }
    expect(rutaServicio.closest('td')).toHaveClass('is-preview-end');
    expect(cambiado).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toBeInTheDocument();
    await usuario.hover(screen.getByRole('button', { name: '18/11/2027' }));
    expect(screen.getByRole('button', { name: '19/11/2027' }).closest('td')).not.toHaveClass('is-preview');
    await usuario.unhover(screen.getByRole('button', { name: '18/11/2027' }));
    expect(document.querySelectorAll('.is-preview, .is-preview-end')).toHaveLength(0);
    await usuario.click(rutaServicio);
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-15', end_date: '2027-11-22' });
  });

  it("previsualiza el movimiento del teclado y limpia el rastro al cambiar de mes o pasar antes de la recogida", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<Selector intervaloInicial={{ start_date: '2027-11-15', end_date: '' }} onChange={cambiado} />);
    await usuario.click(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' }));
    await usuario.keyboard('{ArrowRight}{ArrowRight}');
    expect(screen.getByRole('button', { name: '16/11/2027' }).closest('td')).toHaveClass('is-preview');
    expect(screen.getByRole('button', { name: '17/11/2027' }).closest('td')).toHaveClass('is-preview-end');
    await usuario.hover(screen.getByRole('button', { name: '14/11/2027' }));
    expect(document.querySelectorAll('.is-preview, .is-preview-end')).toHaveLength(0);
    await usuario.hover(screen.getByRole('button', { name: '22/11/2027' }));
    await usuario.click(screen.getByRole('button', { name: 'Mes siguiente' }));
    expect(document.querySelectorAll('.is-preview, .is-preview-end')).toHaveLength(0);
    expect(cambiado).not.toHaveBeenCalled();
  });

  it("ofrece controles de fecha etiquetados y abre un calendario accesible con el día actual marcado", async () => {
    const usuario = userEvent.setup();
    render(<Selector />);
    const inicio = screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' });
    const fin = screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' });
    expect(inicio).toHaveAttribute('id', 'start_date');
    expect(fin).toHaveAttribute('id', 'end_date');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await usuario.click(inicio);
    const calendario = screen.getByRole('dialog', { name: 'Fechas del alquiler' });
    expect(calendario).not.toHaveAttribute('aria-modal', 'true');
    expect(inicio).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: '01/11/2027' })).toHaveAttribute('aria-current', 'date');
    expect(screen.getByRole('button', { name: 'Mes anterior' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mes siguiente' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cerrar calendario' })).toBeInTheDocument();
  });

  it("elige inicio y devolución excluida en dos clics y devuelve el foco al control de fin", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<Selector onChange={cambiado} />);
    await usuario.click(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' }));
    await usuario.click(screen.getByRole('button', { name: '08/11/2027' }));
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-08', end_date: '' });
    expect(screen.getByRole('dialog', { name: 'Fechas del alquiler' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '08/11/2027' })).toHaveAttribute('aria-pressed', 'true');
    await usuario.click(screen.getByRole('button', { name: '11/11/2027' }));
    expect(cambiado).toHaveBeenLastCalledWith({ start_date: '2027-11-08', end_date: '2027-11-11' });
    expect(cambiado).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de inicio: 08/11/2027' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de fin: 11/11/2027' })).toHaveFocus();
  });

  it("marca ambos extremos y los días incluidos en un intervalo existente", async () => {
    const usuario = userEvent.setup();
    render(<Selector intervaloInicial={{ start_date: '2027-11-08', end_date: '2027-11-11' }} />);
    await usuario.click(screen.getByRole('button', { name: 'Fecha de fin: 11/11/2027' }));
    for (const dia of ['08', '09', '10', '11']) {
      expect(screen.getByRole('button', { name: `${dia}/11/2027` })).toHaveAttribute('aria-pressed', 'true');
    }
    expect(screen.getByRole('button', { name: '07/11/2027' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: '12/11/2027' })).toHaveAttribute('aria-pressed', 'false');
  });

  it("comienza un intervalo si se abre el control de fin antes de tener inicio", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<Selector onChange={cambiado} />);
    await usuario.click(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' }));
    await usuario.click(screen.getByRole('button', { name: '08/11/2027' }));
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-08', end_date: '' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it.each(['07/11/2027', '08/11/2027'])("reinicia el intervalo si la devolución intentada es %s, igual o anterior al inicio", async (dia) => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<Selector intervaloInicial={{ start_date: '2027-11-08', end_date: '2027-11-11' }} onChange={cambiado} />);
    await usuario.click(screen.getByRole('button', { name: 'Fecha de fin: 11/11/2027' }));
    await usuario.click(screen.getByRole('button', { name: dia }));
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: `2027-11-${dia.slice(0, 2)}`, end_date: '' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: '12/11/2027' }));
    expect(cambiado).toHaveBeenLastCalledWith({ start_date: `2027-11-${dia.slice(0, 2)}`, end_date: '2027-11-12' });
  });

  it("limpia la devolución anterior cada vez que se elige un inicio nuevo", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<Selector intervaloInicial={{ start_date: '2027-11-08', end_date: '2027-11-11' }} onChange={cambiado} />);
    await usuario.click(screen.getByRole('button', { name: 'Fecha de inicio: 08/11/2027' }));
    await usuario.click(screen.getByRole('button', { name: '09/11/2027' }));
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-09', end_date: '' });
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toBeInTheDocument();
  });

  it("abre el mes del campo solicitado y utiliza un inicio válido como alternativa", async () => {
    const usuario = userEvent.setup();
    const vista = render(<Selector intervaloInicial={{ start_date: '2027-12-28', end_date: '2028-01-04' }} />);
    await usuario.click(screen.getByRole('button', { name: 'Fecha de fin: 04/01/2028' }));
    expect(screen.getByRole('button', { name: '04/01/2028' })).toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: 'Cerrar calendario' }));
    await usuario.click(screen.getByRole('button', { name: 'Fecha de inicio: 28/12/2027' }));
    expect(screen.getByRole('button', { name: '28/12/2027' })).toBeInTheDocument();
    vista.unmount();
    render(<Selector intervaloInicial={{ start_date: '2027-12-28', end_date: '' }} />);
    await usuario.click(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' }));
    expect(screen.getByRole('button', { name: '28/12/2027' })).toBeInTheDocument();
  });

  it("permite fechas históricas y conserva el foco en los controles de navegación mensual", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<Selector onChange={cambiado} />);
    await usuario.click(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' }));
    const anterior = screen.getByRole('button', { name: 'Mes anterior' });
    await usuario.click(anterior);
    expect(anterior).toHaveFocus();
    const historico = screen.getByRole('button', { name: '25/10/2027' });
    expect(historico).toBeEnabled();
    await usuario.click(historico);
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-10-25', end_date: '' });
    const siguiente = screen.getByRole('button', { name: 'Mes siguiente' });
    await usuario.click(siguiente);
    expect(siguiente).toHaveFocus();
    expect(screen.getByRole('button', { name: '25/11/2027' })).toBeInTheDocument();
  });

  it("admite flechas, límites de semana y selección con Enter sin cambiar fechas al navegar", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<Selector onChange={cambiado} />);
    await usuario.click(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' }));
    screen.getByRole('button', { name: '17/11/2027' }).focus();
    await usuario.keyboard('{ArrowRight}{ArrowDown}{ArrowLeft}{ArrowUp}');
    expect(screen.getByRole('button', { name: '17/11/2027' })).toHaveFocus();
    await usuario.keyboard('{Home}');
    expect(screen.getByRole('button', { name: '15/11/2027' })).toHaveFocus();
    await usuario.keyboard('{End}');
    expect(screen.getByRole('button', { name: '21/11/2027' })).toHaveFocus();
    expect(cambiado).not.toHaveBeenCalled();
    await usuario.keyboard('{Enter}');
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-21', end_date: '' });
  });

  it("mueve el foco del teclado entre meses y admite PageUp y PageDown", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<Selector onChange={cambiado} />);
    await usuario.click(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' }));
    screen.getByRole('button', { name: '30/11/2027' }).focus();
    await usuario.keyboard('{ArrowRight}');
    expect(screen.getByRole('button', { name: '01/12/2027' })).toHaveFocus();
    await usuario.keyboard('{PageDown}');
    expect(screen.getByRole('button', { name: '01/01/2028' })).toHaveFocus();
    await usuario.keyboard('{PageUp}');
    expect(screen.getByRole('button', { name: '01/12/2027' })).toHaveFocus();
    expect(cambiado).not.toHaveBeenCalled();
  });

  it("vuelve al día actual sin cambiar el intervalo y limpia ambas fechas mediante su acción de borrado", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<Selector intervaloInicial={{ start_date: '2028-01-08', end_date: '2028-01-11' }} onChange={cambiado} />);
    await usuario.click(screen.getByRole('button', { name: 'Fecha de fin: 11/01/2028' }));
    await usuario.click(screen.getByRole('button', { name: 'Hoy' }));
    expect(screen.getByRole('button', { name: '01/11/2027' })).toHaveAttribute('aria-current', 'date');
    expect(cambiado).not.toHaveBeenCalled();
    await usuario.click(screen.getByRole('button', { name: 'Borrar fechas' }));
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '', end_date: '' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' })).toHaveFocus();
  });

  it("cierra con Escape o con el botón de cierre y devuelve el foco al control de apertura", async () => {
    const usuario = userEvent.setup();
    render(<Selector />);
    const fin = screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' });
    await usuario.click(fin);
    await usuario.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(fin).toHaveFocus();
    const inicio = screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' });
    await usuario.click(inicio);
    await usuario.click(screen.getByRole('button', { name: 'Cerrar calendario' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(inicio).toHaveFocus();
  });

  it("cierra tras pulsar fuera y deja el foco en el filtro pulsado", async () => {
    const usuario = userEvent.setup();
    render(<Selector />);
    await usuario.click(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' }));
    const otroFiltro = screen.getByRole('button', { name: 'Otro filtro' });
    await usuario.click(otroFiltro);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(otroFiltro).toHaveFocus();
  });

  it("asocia los mensajes de validación con sus campos y deshabilita ambos controles mientras espera", () => {
    const vista = render(<Selector errors={{ start_date: 'Selecciona una fecha de inicio válida.', end_date: 'La fecha de fin debe ser posterior al inicio.' }} />);
    const inicio = screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' });
    const fin = screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' });
    expect(inicio).toHaveAttribute('aria-invalid', 'true');
    expect(fin).toHaveAttribute('aria-invalid', 'true');
    expect(inicio).toHaveAccessibleDescription(/Selecciona una fecha de inicio válida\./);
    expect(fin).toHaveAccessibleDescription(/La fecha de fin debe ser posterior al inicio\./);
    vista.unmount();
    render(<Selector disabled />);
    expect(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toBeDisabled();
  });

  it("utiliza el día actual como alternativa segura ante fechas de calendario no válidas recibidas por URL", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<Selector intervaloInicial={{ start_date: '2027-02-31', end_date: 'not-a-date' }} onChange={cambiado} />);
    await usuario.click(screen.getByRole('button', { name: /^Fecha de fin:/ }));
    expect(screen.getByRole('dialog', { name: 'Fechas del alquiler' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '01/11/2027' })).toHaveAttribute('aria-current', 'date');
    expect(cambiado).not.toHaveBeenCalled();
    await usuario.click(screen.getByRole('button', { name: '08/11/2027' }));
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-08', end_date: '' });
  });
});
