import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DateRange } from '../api/client';
import { CatalogueDatePicker } from './CatalogueDatePicker';
import * as dateRange from './dateRange';

function Picker({ initialRange = { start_date: '', end_date: '' }, errors, disabled = false, onChange }: {
  initialRange?: DateRange;
  errors?: Record<string, string>;
  disabled?: boolean;
  onChange?: (range: DateRange) => void;
}) {
  const [value, setValue] = useState(initialRange);
  return <>
    <CatalogueDatePicker value={value} errors={errors ?? {}} disabled={disabled} onChange={(next) => { setValue(next); onChange?.(next); }} />
    <button type="button">Otro filtro</button>
  </>;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(dateRange, 'todayInMadrid').mockReturnValue('2027-11-01');
});

describe('catalogue rental date picker', () => {
  it('previews all intermediate days on hover without choosing the return, and clears on exit', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<Picker initialRange={{ start_date: '2027-11-15', end_date: '' }} onChange={changed} />);
    await user.click(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' }));
    const endpoint = screen.getByRole('button', { name: '22/11/2027' });
    await user.hover(endpoint);
    for (const day of ['16', '17', '18', '19', '20', '21']) {
      const button = screen.getByRole('button', { name: `${day}/11/2027` });
      expect(button.closest('td')).toHaveClass('is-preview');
      expect(button).toHaveAttribute('aria-pressed', 'false');
    }
    expect(endpoint.closest('td')).toHaveClass('is-preview-end');
    expect(changed).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toBeInTheDocument();
    await user.hover(screen.getByRole('button', { name: '18/11/2027' }));
    expect(screen.getByRole('button', { name: '19/11/2027' }).closest('td')).not.toHaveClass('is-preview');
    await user.unhover(screen.getByRole('button', { name: '18/11/2027' }));
    expect(document.querySelectorAll('.is-preview, .is-preview-end')).toHaveLength(0);
    await user.click(endpoint);
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-15', end_date: '2027-11-22' });
  });

  it('previews keyboard movement and clears the trail when navigating months or hovering before pickup', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<Picker initialRange={{ start_date: '2027-11-15', end_date: '' }} onChange={changed} />);
    await user.click(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' }));
    await user.keyboard('{ArrowRight}{ArrowRight}');
    expect(screen.getByRole('button', { name: '16/11/2027' }).closest('td')).toHaveClass('is-preview');
    expect(screen.getByRole('button', { name: '17/11/2027' }).closest('td')).toHaveClass('is-preview-end');
    await user.hover(screen.getByRole('button', { name: '14/11/2027' }));
    expect(document.querySelectorAll('.is-preview, .is-preview-end')).toHaveLength(0);
    await user.hover(screen.getByRole('button', { name: '22/11/2027' }));
    await user.click(screen.getByRole('button', { name: 'Mes siguiente' }));
    expect(document.querySelectorAll('.is-preview, .is-preview-end')).toHaveLength(0);
    expect(changed).not.toHaveBeenCalled();
  });

  it('exposes labelled date controls and opens an accessible calendar with today marked', async () => {
    const user = userEvent.setup();
    render(<Picker />);
    const start = screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' });
    const end = screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' });
    expect(start).toHaveAttribute('id', 'start_date');
    expect(end).toHaveAttribute('id', 'end_date');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await user.click(start);
    const calendar = screen.getByRole('dialog', { name: 'Fechas del alquiler' });
    expect(calendar).not.toHaveAttribute('aria-modal', 'true');
    expect(start).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: '01/11/2027' })).toHaveAttribute('aria-current', 'date');
    expect(screen.getByRole('button', { name: 'Mes anterior' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mes siguiente' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cerrar calendario' })).toBeInTheDocument();
  });

  it('chooses the start and excluded return in two clicks, then returns focus to the end control', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<Picker onChange={changed} />);
    await user.click(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' }));
    await user.click(screen.getByRole('button', { name: '08/11/2027' }));
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-08', end_date: '' });
    expect(screen.getByRole('dialog', { name: 'Fechas del alquiler' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '08/11/2027' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: '11/11/2027' }));
    expect(changed).toHaveBeenLastCalledWith({ start_date: '2027-11-08', end_date: '2027-11-11' });
    expect(changed).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de inicio: 08/11/2027' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de fin: 11/11/2027' })).toHaveFocus();
  });

  it('marks both endpoints and the days inside an existing range', async () => {
    const user = userEvent.setup();
    render(<Picker initialRange={{ start_date: '2027-11-08', end_date: '2027-11-11' }} />);
    await user.click(screen.getByRole('button', { name: 'Fecha de fin: 11/11/2027' }));
    for (const day of ['08', '09', '10', '11']) {
      expect(screen.getByRole('button', { name: `${day}/11/2027` })).toHaveAttribute('aria-pressed', 'true');
    }
    expect(screen.getByRole('button', { name: '07/11/2027' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: '12/11/2027' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('starts a range when the end control is opened before any start exists', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<Picker onChange={changed} />);
    await user.click(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' }));
    await user.click(screen.getByRole('button', { name: '08/11/2027' }));
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-08', end_date: '' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it.each(['07/11/2027', '08/11/2027'])('restarts the range when the attempted return is %s, on or before the start', async (day) => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<Picker initialRange={{ start_date: '2027-11-08', end_date: '2027-11-11' }} onChange={changed} />);
    await user.click(screen.getByRole('button', { name: 'Fecha de fin: 11/11/2027' }));
    await user.click(screen.getByRole('button', { name: day }));
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: `2027-11-${day.slice(0, 2)}`, end_date: '' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '12/11/2027' }));
    expect(changed).toHaveBeenLastCalledWith({ start_date: `2027-11-${day.slice(0, 2)}`, end_date: '2027-11-12' });
  });

  it('clears the previous return whenever a new start is chosen', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<Picker initialRange={{ start_date: '2027-11-08', end_date: '2027-11-11' }} onChange={changed} />);
    await user.click(screen.getByRole('button', { name: 'Fecha de inicio: 08/11/2027' }));
    await user.click(screen.getByRole('button', { name: '09/11/2027' }));
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-09', end_date: '' });
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toBeInTheDocument();
  });

  it('opens the month belonging to the requested field and falls back to a valid start', async () => {
    const user = userEvent.setup();
    const view = render(<Picker initialRange={{ start_date: '2027-12-28', end_date: '2028-01-04' }} />);
    await user.click(screen.getByRole('button', { name: 'Fecha de fin: 04/01/2028' }));
    expect(screen.getByRole('button', { name: '04/01/2028' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cerrar calendario' }));
    await user.click(screen.getByRole('button', { name: 'Fecha de inicio: 28/12/2027' }));
    expect(screen.getByRole('button', { name: '28/12/2027' })).toBeInTheDocument();
    view.unmount();
    render(<Picker initialRange={{ start_date: '2027-12-28', end_date: '' }} />);
    await user.click(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' }));
    expect(screen.getByRole('button', { name: '28/12/2027' })).toBeInTheDocument();
  });

  it('allows historical dates and preserves focus on month navigation controls', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<Picker onChange={changed} />);
    await user.click(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' }));
    const previous = screen.getByRole('button', { name: 'Mes anterior' });
    await user.click(previous);
    expect(previous).toHaveFocus();
    const historical = screen.getByRole('button', { name: '25/10/2027' });
    expect(historical).toBeEnabled();
    await user.click(historical);
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-10-25', end_date: '' });
    const next = screen.getByRole('button', { name: 'Mes siguiente' });
    await user.click(next);
    expect(next).toHaveFocus();
    expect(screen.getByRole('button', { name: '25/11/2027' })).toBeInTheDocument();
  });

  it('supports arrow keys, week boundaries, and Enter selection without changing dates while navigating', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<Picker onChange={changed} />);
    await user.click(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' }));
    screen.getByRole('button', { name: '17/11/2027' }).focus();
    await user.keyboard('{ArrowRight}{ArrowDown}{ArrowLeft}{ArrowUp}');
    expect(screen.getByRole('button', { name: '17/11/2027' })).toHaveFocus();
    await user.keyboard('{Home}');
    expect(screen.getByRole('button', { name: '15/11/2027' })).toHaveFocus();
    await user.keyboard('{End}');
    expect(screen.getByRole('button', { name: '21/11/2027' })).toHaveFocus();
    expect(changed).not.toHaveBeenCalled();
    await user.keyboard('{Enter}');
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-21', end_date: '' });
  });

  it('moves keyboard focus across month boundaries and supports PageUp and PageDown', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<Picker onChange={changed} />);
    await user.click(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' }));
    screen.getByRole('button', { name: '30/11/2027' }).focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('button', { name: '01/12/2027' })).toHaveFocus();
    await user.keyboard('{PageDown}');
    expect(screen.getByRole('button', { name: '01/01/2028' })).toHaveFocus();
    await user.keyboard('{PageUp}');
    expect(screen.getByRole('button', { name: '01/12/2027' })).toHaveFocus();
    expect(changed).not.toHaveBeenCalled();
  });

  it('returns to today without changing the range, and clears both dates from its clear action', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<Picker initialRange={{ start_date: '2028-01-08', end_date: '2028-01-11' }} onChange={changed} />);
    await user.click(screen.getByRole('button', { name: 'Fecha de fin: 11/01/2028' }));
    await user.click(screen.getByRole('button', { name: 'Hoy' }));
    expect(screen.getByRole('button', { name: '01/11/2027' })).toHaveAttribute('aria-current', 'date');
    expect(changed).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Borrar fechas' }));
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '', end_date: '' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' })).toHaveFocus();
  });

  it('closes on Escape or the close button and restores focus to the opening control', async () => {
    const user = userEvent.setup();
    render(<Picker />);
    const end = screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' });
    await user.click(end);
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(end).toHaveFocus();
    const start = screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' });
    await user.click(start);
    await user.click(screen.getByRole('button', { name: 'Cerrar calendario' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(start).toHaveFocus();
  });

  it('closes after an outside click while leaving focus on the clicked filter', async () => {
    const user = userEvent.setup();
    render(<Picker />);
    await user.click(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' }));
    const otherFilter = screen.getByRole('button', { name: 'Otro filtro' });
    await user.click(otherFilter);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(otherFilter).toHaveFocus();
  });

  it('associates validation messages with their fields and disables both controls while busy', () => {
    const view = render(<Picker errors={{ start_date: 'Selecciona una fecha de inicio válida.', end_date: 'La fecha de fin debe ser posterior al inicio.' }} />);
    const start = screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' });
    const end = screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' });
    expect(start).toHaveAttribute('aria-invalid', 'true');
    expect(end).toHaveAttribute('aria-invalid', 'true');
    expect(start).toHaveAccessibleDescription(/Selecciona una fecha de inicio válida\./);
    expect(end).toHaveAccessibleDescription(/La fecha de fin debe ser posterior al inicio\./);
    view.unmount();
    render(<Picker disabled />);
    expect(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toBeDisabled();
  });

  it('falls back safely to today for invalid calendar dates received through a URL', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<Picker initialRange={{ start_date: '2027-02-31', end_date: 'not-a-date' }} onChange={changed} />);
    await user.click(screen.getByRole('button', { name: /^Fecha de fin:/ }));
    expect(screen.getByRole('dialog', { name: 'Fechas del alquiler' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '01/11/2027' })).toHaveAttribute('aria-current', 'date');
    expect(changed).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '08/11/2027' }));
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-08', end_date: '' });
  });
});
