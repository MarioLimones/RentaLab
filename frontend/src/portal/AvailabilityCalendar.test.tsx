import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, type DateRange, type PublicAvailabilityCalendar } from '../api/client';
import { AvailabilityCalendar } from './AvailabilityCalendar';
import * as dateRange from './dateRange';
import { useAvailabilityCalendar } from './useAvailabilityCalendar';

function Calendar({ date = '2027-11-10', revision = 0 }: { date?: string; revision?: number }) {
  return <AvailabilityCalendar calendar={useAvailabilityCalendar(1, date, revision)} />;
}

function InteractiveCalendar({ initialRange = { start_date: '', end_date: '' }, disabled = false, onChange }: { initialRange?: DateRange; disabled?: boolean; onChange?: (range: DateRange) => void }) {
  const [range, setRange] = useState(initialRange);
  return <AvailabilityCalendar calendar={useAvailabilityCalendar(1, range.start_date, 0, true)} range={range} disabled={disabled} onChange={(next) => { setRange(next); onChange?.(next); }} />;
}

const occupied = { start_date: '2027-11-10', end_date: '2027-11-12' };
const november: PublicAvailabilityCalendar = { equipment_id: 1, start_date: '2027-11-01', end_date: '2027-12-01', occupied_ranges: [occupied], can_book: true };

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(dateRange, 'todayInMadrid').mockReturnValue('2027-11-01');
  vi.spyOn(api, 'getPublicAvailability').mockImplementation(async (equipment_id, range) => ({ equipment_id, start_date: range?.start_date ?? '2027-11-28', end_date: range?.end_date ?? '2027-12-01', available: true, status: 'available' }));
  vi.spyOn(api, 'getPublicAvailabilityCalendar').mockImplementation(async (equipment_id, range) => ({ ...november, equipment_id, ...range }));
});

describe('public occupied days calendar', () => {
  it('marks only full occupied days and leaves the excluded end available without private identity details', async () => {
    render(<Calendar />);
    expect(await screen.findByRole('table', { name: 'Ocupación de noviembre de 2027' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '10/11/2027: Ocupado' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '11/11/2027: Ocupado' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '12/11/2027: Disponible' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '09/11/2027: Disponible' })).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader')).toHaveLength(7);
    expect(screen.getByText(/La devolución no cuenta como día de alquiler\./)).toBeInTheDocument();
    expect(api.getPublicAvailabilityCalendar).toHaveBeenCalledExactlyOnceWith(1, { start_date: '2027-11-01', end_date: '2027-12-01' }, expect.any(AbortSignal));
  });

  it('explains the global booking block without presenting empty days as bookable', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockResolvedValue({ ...november, can_book: false });
    render(<Calendar />);
    expect(await screen.findByText('Este equipo no admite nuevas reservas en este momento. Consulta otro equipo o vuelve más adelante.')).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '12/11/2027: No admite reservas' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '10/11/2027: Ocupado' })).toBeInTheDocument();
  });

  it('queries another month by keyboard, including year transitions, and uses Monday as the first weekday', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockImplementation(async (equipment_id, range) => ({ equipment_id, ...range, occupied_ranges: [], can_book: true }));
    const user = userEvent.setup();
    render(<Calendar date="2027-12-10" />);
    await screen.findByRole('table', { name: 'Ocupación de diciembre de 2027' });
    const next = screen.getByRole('button', { name: 'Mes siguiente' });
    next.focus();
    await user.keyboard('{Enter}');
    expect(await screen.findByRole('table', { name: 'Ocupación de enero de 2028' })).toBeInTheDocument();
    expect(next).toHaveFocus();
    expect(api.getPublicAvailabilityCalendar).toHaveBeenLastCalledWith(1, { start_date: '2028-01-01', end_date: '2028-02-01' }, expect.any(AbortSignal));
    expect(screen.getAllByRole('columnheader')[0]).toHaveTextContent('Lu');
    await user.click(screen.getByRole('button', { name: 'Mes anterior' }));
    expect(await screen.findByRole('table', { name: 'Ocupación de diciembre de 2027' })).toBeInTheDocument();
  });

  it('discards late results from a previous month after selected dates change', async () => {
    let finishOld!: (value: PublicAvailabilityCalendar) => void;
    vi.mocked(api.getPublicAvailabilityCalendar).mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve; }))
      .mockResolvedValueOnce({ equipment_id: 1, start_date: '2028-02-01', end_date: '2028-03-01', occupied_ranges: [], can_book: true });
    const view = render(<Calendar />);
    await waitFor(() => expect(api.getPublicAvailabilityCalendar).toHaveBeenCalledTimes(1));
    view.rerender(<Calendar date="2028-02-10" />);
    expect(await screen.findByRole('table', { name: 'Ocupación de febrero de 2028' })).toBeInTheDocument();
    await act(async () => { finishOld(november); });
    expect(screen.getByRole('cell', { name: '29/02/2028: Disponible' })).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Ocupación de noviembre de 2027' })).not.toBeInTheDocument();
  });

  it('refetches confirmed ranges after a saved reservation and retains the selected month', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockResolvedValueOnce({ ...november, occupied_ranges: [] }).mockResolvedValue(november);
    const view = render(<Calendar />);
    expect(await screen.findByRole('cell', { name: '10/11/2027: Disponible' })).toBeInTheDocument();
    view.rerender(<Calendar revision={1} />);
    expect(await screen.findByRole('cell', { name: '10/11/2027: Ocupado' })).toBeInTheDocument();
    expect(api.getPublicAvailabilityCalendar).toHaveBeenCalledTimes(2);
  });

  it('makes a failed calendar recoverable and never shows stale occupancy as current', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockRejectedValueOnce(new ApiError('Sin conexión.', 0)).mockResolvedValue(november);
    const user = userEvent.setup();
    render(<Calendar />);
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo actualizar el calendario. Sin conexión.');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Reintentar calendario' }));
    expect(await screen.findByRole('cell', { name: '10/11/2027: Ocupado' })).toBeInTheDocument();
    expect(api.getPublicAvailabilityCalendar).toHaveBeenCalledTimes(2);
  });
});

describe('interactive reservation calendar', () => {
  it('blocks a fragmented full interval even when every individual day has equipment available', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockImplementation(async (equipment_id, range) => ({
      equipment_id, ...range, occupied_ranges: [], can_book: true,
      unavailable_end_dates: range.booking_start === '2027-11-15' ? ['2027-11-19', '2027-11-20'] : [],
    }));
    const changed = vi.fn();
    const user = userEvent.setup();
    const view = render(<InteractiveCalendar initialRange={{ start_date: '2027-11-15', end_date: '' }} onChange={changed} />);
    const blockedReturn = await screen.findByRole('button', { name: /20\/11\/2027: No disponible para esta devolución/ });
    expect(api.getPublicAvailabilityCalendar).toHaveBeenCalledExactlyOnceWith(1, { start_date: '2027-11-01', end_date: '2027-12-01', booking_start: '2027-11-15' }, expect.any(AbortSignal));
    expect(blockedReturn).toHaveAttribute('aria-disabled', 'true');
    expect(blockedReturn.closest('td')).toHaveClass('calendar-day-blocked');
    await user.hover(blockedReturn);
    await user.click(blockedReturn);
    expect(view.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
    expect(changed).not.toHaveBeenCalled();
    const allowedReturn = screen.getByRole('button', { name: '18/11/2027: Disponible' });
    await user.click(allowedReturn);
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-15', end_date: '2027-11-18' });
  });

  it('refreshes eligible returns after a pickup change within the month and preserves keyboard focus while checking', async () => {
    let finish!: (value: PublicAvailabilityCalendar) => void;
    vi.mocked(api.getPublicAvailabilityCalendar).mockResolvedValueOnce({ ...november, occupied_ranges: [], unavailable_end_dates: [] })
      .mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<InteractiveCalendar onChange={changed} />);
    const pickup = await screen.findByRole('button', { name: '15/11/2027: Disponible' });
    pickup.focus();
    await user.keyboard('{Enter}');
    expect(pickup).toHaveFocus();
    expect(screen.getByRole('table')).toHaveAttribute('aria-busy', 'true');
    const pendingReturn = screen.getByRole('button', { name: /^20\/11\/2027: Disponible/ });
    expect(pendingReturn).toHaveAttribute('aria-disabled', 'true');
    await user.click(pendingReturn);
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-15', end_date: '' });
    expect(api.getPublicAvailabilityCalendar).toHaveBeenLastCalledWith(1, { start_date: '2027-11-01', end_date: '2027-12-01', booking_start: '2027-11-15' }, expect.any(AbortSignal));
    await act(async () => { finish({ ...november, occupied_ranges: [], unavailable_end_dates: ['2027-11-20'] }); });
    expect(screen.getByRole('button', { name: /20\/11\/2027: No disponible para esta devolución/ })).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByRole('button', { name: '18/11/2027: Disponible' })).not.toHaveAttribute('aria-disabled', 'true');
  });

  it('previews the available return range on hover without selecting the dates', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    const view = render(<InteractiveCalendar initialRange={{ start_date: '2027-11-06', end_date: '' }} onChange={changed} />);
    const hoveredReturn = await screen.findByRole('button', { name: '09/11/2027: Disponible' });
    await user.hover(hoveredReturn);

    expect(screen.getByRole('button', { name: /^06\/11\/2027:/ }).closest('td')).toHaveClass('calendar-day-start');
    expect(screen.getByRole('button', { name: '07/11/2027: Disponible' }).closest('td')).toHaveClass('calendar-day-preview');
    expect(screen.getByRole('button', { name: '08/11/2027: Disponible' }).closest('td')).toHaveClass('calendar-day-preview');
    expect(hoveredReturn.closest('td')).toHaveClass('calendar-day-preview-end');
    expect(screen.getByRole('button', { name: '05/11/2027: Disponible' }).closest('td')).not.toHaveClass('calendar-day-preview');
    expect(hoveredReturn).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: '08/11/2027: Disponible' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Fecha de devolución: Elegir día' })).toBeInTheDocument();
    expect(changed).not.toHaveBeenCalled();

    await user.unhover(hoveredReturn);
    expect(view.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
    expect(changed).not.toHaveBeenCalled();
  });

  it('clears the preview for blocked intervals but permits the first occupied day as an excluded return', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    const view = render(<InteractiveCalendar initialRange={{ start_date: '2027-11-06', end_date: '' }} onChange={changed} />);
    await user.hover(await screen.findByRole('button', { name: '09/11/2027: Disponible' }));
    expect(view.container.querySelector('.calendar-day-preview-end')).toBeInTheDocument();

    await user.hover(screen.getByRole('button', { name: /^13\/11\/2027:/ }));
    expect(view.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
    await user.hover(screen.getByRole('button', { name: /^11\/11\/2027: Ocupado/ }));
    expect(view.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();

    const adjacentReturn = screen.getByRole('button', { name: '10/11/2027: Ocupado. Devolución posible' });
    await user.hover(adjacentReturn);
    expect(adjacentReturn.closest('td')).toHaveClass('calendar-day-preview-end');
    expect(screen.getByRole('button', { name: '09/11/2027: Disponible' }).closest('td')).toHaveClass('calendar-day-preview');
    expect(adjacentReturn).toHaveAttribute('aria-pressed', 'false');
    expect(changed).not.toHaveBeenCalled();
  });

  it('previews the focused return date with the keyboard before Enter confirms it', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    const view = render(<InteractiveCalendar initialRange={{ start_date: '2027-11-06', end_date: '' }} onChange={changed} />);
    const pickup = await screen.findByRole('button', { name: /^06\/11\/2027:/ });
    act(() => pickup.focus());
    await user.keyboard('{ArrowRight}{ArrowRight}');
    const focusedReturn = screen.getByRole('button', { name: '08/11/2027: Disponible' });
    expect(focusedReturn).toHaveFocus();
    expect(focusedReturn.closest('td')).toHaveClass('calendar-day-preview-end');
    expect(screen.getByRole('button', { name: '07/11/2027: Disponible' }).closest('td')).toHaveClass('calendar-day-preview');
    expect(focusedReturn).toHaveAttribute('aria-pressed', 'false');
    expect(changed).not.toHaveBeenCalled();

    await user.keyboard('{Enter}');
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-06', end_date: '2027-11-08' });
    expect(screen.getByRole('button', { name: /^08\/11\/2027:/ })).toHaveAttribute('aria-pressed', 'true');
    expect(view.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
  });

  it('does not preview past days or dates while confirmation disables the calendar', async () => {
    vi.mocked(dateRange.todayInMadrid).mockReturnValue('2027-11-05');
    const changed = vi.fn();
    const user = userEvent.setup();
    const view = render(<InteractiveCalendar initialRange={{ start_date: '2027-11-06', end_date: '' }} onChange={changed} />);
    await user.hover(await screen.findByRole('button', { name: '04/11/2027: Fecha pasada' }));
    expect(view.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
    view.rerender(<InteractiveCalendar initialRange={{ start_date: '2027-11-06', end_date: '' }} disabled onChange={changed} />);
    await user.hover(screen.getByRole('button', { name: '09/11/2027: Disponible' }));
    expect(view.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
    expect(changed).not.toHaveBeenCalled();
  });

  it('never previews dates when the equipment does not admit reservations', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockResolvedValue({ ...november, can_book: false });
    const changed = vi.fn();
    const user = userEvent.setup();
    const view = render(<InteractiveCalendar initialRange={{ start_date: '2027-11-06', end_date: '' }} onChange={changed} />);
    await user.hover(await screen.findByRole('button', { name: '09/11/2027: No admite reservas' }));
    expect(view.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
    expect(changed).not.toHaveBeenCalled();
  });

  it('does not create a lingering hover preview from a touch pointer', async () => {
    const changed = vi.fn();
    const view = render(<InteractiveCalendar initialRange={{ start_date: '2027-11-06', end_date: '' }} onChange={changed} />);
    const returnDate = await screen.findByRole('button', { name: '09/11/2027: Disponible' });
    fireEvent.pointerEnter(returnDate, { pointerType: 'touch', pointerId: 1 });
    expect(view.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
    expect(returnDate).toHaveAttribute('aria-pressed', 'false');
    expect(changed).not.toHaveBeenCalled();
  });

  it('starts with the pickup when return is opened before choosing any dates', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<InteractiveCalendar onChange={changed} />);
    await user.click(await screen.findByRole('button', { name: 'Fecha de devolución: Elegir día' }));
    await user.click(screen.getByRole('button', { name: '08/11/2027: Disponible' }));
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-08', end_date: '' });
  });

  it('shows availability before selection and chooses the rental start and excluded return in two clicks', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<InteractiveCalendar onChange={changed} />);
    const start = await screen.findByRole('button', { name: '08/11/2027: Disponible' });
    expect(screen.getByRole('button', { name: /^Fecha de inicio:/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Fecha de devolución:/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '10/11/2027: Ocupado' })).toHaveAttribute('aria-disabled', 'true');
    expect(changed).not.toHaveBeenCalled();
    await user.click(start);
    expect(changed).toHaveBeenLastCalledWith({ start_date: '2027-11-08', end_date: '' });
    await user.click(screen.getByRole('button', { name: '09/11/2027: Disponible' }));
    expect(changed).toHaveBeenLastCalledWith({ start_date: '2027-11-08', end_date: '2027-11-09' });
    expect(changed).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: /^Fecha de inicio:.*08\/11\/2027/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Fecha de devolución:.*09\/11\/2027/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cambiar fechas' })).toBeInTheDocument();
  });

  it('prevents choosing a range with occupied days between an available start and return', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<InteractiveCalendar onChange={changed} />);
    await user.click(await screen.findByRole('button', { name: '08/11/2027: Disponible' }));
    const returnAfterOccupation = screen.getByRole('button', { name: /^13\/11\/2027:/ });
    expect(returnAfterOccupation).toHaveAttribute('aria-disabled', 'true');
    await user.click(returnAfterOccupation);
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-08', end_date: '' });
  });

  it('allows returning on the occupied start of the next reservation because that day is excluded', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<InteractiveCalendar onChange={changed} />);
    await user.click(await screen.findByRole('button', { name: '08/11/2027: Disponible' }));
    const adjacentReturn = screen.getByRole('button', { name: '10/11/2027: Ocupado. Devolución posible' });
    expect(adjacentReturn).not.toHaveAttribute('aria-disabled', 'true');
    await user.click(adjacentReturn);
    expect(changed).toHaveBeenLastCalledWith({ start_date: '2027-11-08', end_date: '2027-11-10' });
    expect(changed).toHaveBeenCalledTimes(2);
  });

  it('does not mistake a reservation clipped at the month boundary for a possible return', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockImplementation(async (equipment_id, range) => ({
      equipment_id, ...range, can_book: true,
      occupied_ranges: range.start_date === '2027-11-01'
        ? [{ start_date: '2027-11-29', end_date: '2027-12-01' }]
        : [{ start_date: '2027-12-01', end_date: '2027-12-03' }],
    }));
    vi.mocked(api.getPublicAvailability).mockImplementation(async (equipment_id, range) => ({ equipment_id, start_date: range?.start_date ?? '2027-11-28', end_date: range?.end_date ?? '2027-12-01', available: false, status: 'unavailable' }));
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<InteractiveCalendar initialRange={{ start_date: '2027-11-28', end_date: '' }} onChange={changed} />);
    await screen.findByRole('table', { name: 'Ocupación de noviembre de 2027' });
    await user.click(screen.getByRole('button', { name: 'Mes siguiente' }));
    const clippedOccupied = await screen.findByRole('button', { name: /^01\/12\/2027: Ocupado/ });
    expect(api.getPublicAvailability).toHaveBeenCalledExactlyOnceWith(1, { start_date: '2027-11-28', end_date: '2027-12-01' }, expect.any(AbortSignal));
    expect(clippedOccupied).toHaveAttribute('aria-disabled', 'true');
    expect(clippedOccupied).not.toHaveAccessibleName(/Devolución posible/);
    const clearDayAfterOccupation = screen.getByRole('button', { name: /^04\/12\/2027: Disponible/ });
    expect(clearDayAfterOccupation).toHaveAttribute('aria-disabled', 'true');
    await user.click(clippedOccupied);
    await user.click(clearDayAfterOccupation);
    expect(changed).not.toHaveBeenCalled();
  });

  it('allows a return on the first occupied day of a new month when the entire preceding period is free', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockImplementation(async (equipment_id, range) => ({
      equipment_id, ...range, can_book: true,
      occupied_ranges: range.start_date === '2027-12-01' ? [{ start_date: '2027-12-01', end_date: '2027-12-03' }] : [],
    }));
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<InteractiveCalendar initialRange={{ start_date: '2027-11-28', end_date: '' }} onChange={changed} />);
    await screen.findByRole('table', { name: 'Ocupación de noviembre de 2027' });
    await user.click(screen.getByRole('button', { name: 'Mes siguiente' }));
    const adjacentReturn = await screen.findByRole('button', { name: '01/12/2027: Ocupado. Devolución posible' });
    expect(api.getPublicAvailability).toHaveBeenCalledExactlyOnceWith(1, { start_date: '2027-11-28', end_date: '2027-12-01' }, expect.any(AbortSignal));
    expect(adjacentReturn).not.toHaveAttribute('aria-disabled', 'true');
    await user.click(adjacentReturn);
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-28', end_date: '2027-12-01' });
  });

  it('keeps the original pickup when checking fragmented availability across a month boundary', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockImplementation(async (equipment_id, range) => ({
      equipment_id, ...range, can_book: true, occupied_ranges: [],
      unavailable_end_dates: range.start_date === '2027-12-01' ? ['2027-12-03'] : [],
    }));
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<InteractiveCalendar initialRange={{ start_date: '2027-11-28', end_date: '' }} onChange={changed} />);
    await screen.findByRole('table', { name: 'Ocupación de noviembre de 2027' });
    await user.click(screen.getByRole('button', { name: 'Mes siguiente' }));
    const blockedReturn = await screen.findByRole('button', { name: /03\/12\/2027: No disponible para esta devolución/ });
    expect(api.getPublicAvailabilityCalendar).toHaveBeenLastCalledWith(1, { start_date: '2027-12-01', end_date: '2028-01-01', booking_start: '2027-11-28' }, expect.any(AbortSignal));
    expect(blockedReturn).toHaveAttribute('aria-disabled', 'true');
    await user.click(blockedReturn);
    expect(changed).not.toHaveBeenCalled();
  });

  it('keeps invalid URL months recoverable when editing the selected dates', async () => {
    const query = new URLSearchParams('start_date=2027-99-10&end_date=2027-11-12');
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<InteractiveCalendar initialRange={{ start_date: query.get('start_date')!, end_date: query.get('end_date')! }} onChange={changed} />);
    await screen.findByRole('table', { name: 'Ocupación de noviembre de 2027' });
    await user.click(screen.getByRole('button', { name: 'Fecha de inicio: 10/99/2027' }));
    expect(screen.getByRole('table', { name: 'Ocupación de noviembre de 2027' })).toBeInTheDocument();
    expect(api.getPublicAvailabilityCalendar).toHaveBeenCalledExactlyOnceWith(1, { start_date: '2027-11-01', end_date: '2027-12-01' }, expect.any(AbortSignal));
    expect(changed).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '08/11/2027: Disponible' }));
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-08', end_date: '' });
  });

  it('keeps past days keyboard discoverable while refusing to select them', async () => {
    vi.mocked(dateRange.todayInMadrid).mockReturnValue('2027-11-05');
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<InteractiveCalendar onChange={changed} />);
    const today = await screen.findByRole('button', { name: /^05\/11\/2027:/ });
    const past = screen.getByRole('button', { name: /^04\/11\/2027:/ });
    expect(past).toHaveAttribute('aria-disabled', 'true');
    expect(past).not.toBeDisabled();
    today.focus();
    await user.keyboard('{ArrowLeft}{Enter}');
    expect(past).toHaveFocus();
    await user.click(past);
    expect(changed).not.toHaveBeenCalled();
    await user.click(today);
    expect(changed).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-05', end_date: '' });
  });

  it('keeps occupied days keyboard discoverable without selecting them as a rental start', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<InteractiveCalendar onChange={changed} />);
    const beforeOccupation = await screen.findByRole('button', { name: '09/11/2027: Disponible' });
    const unavailable = screen.getByRole('button', { name: '10/11/2027: Ocupado' });
    expect(unavailable).not.toBeDisabled();
    beforeOccupation.focus();
    await user.keyboard('{ArrowRight}{Enter}');
    expect(unavailable).toHaveFocus();
    expect(unavailable).toHaveAttribute('aria-disabled', 'true');
    expect(changed).not.toHaveBeenCalled();
  });

  it('blocks selection while confirming and when the product does not admit reservations', async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    const view = render(<InteractiveCalendar disabled onChange={changed} />);
    await user.click(await screen.findByRole('button', { name: '08/11/2027: Disponible' }));
    expect(changed).not.toHaveBeenCalled();
    view.unmount();
    vi.mocked(api.getPublicAvailabilityCalendar).mockResolvedValue({ ...november, can_book: false });
    render(<InteractiveCalendar onChange={changed} />);
    const unavailable = await screen.findByRole('button', { name: '08/11/2027: No admite reservas' });
    expect(unavailable).toHaveAttribute('aria-disabled', 'true');
    await user.click(unavailable);
    expect(changed).not.toHaveBeenCalled();
  });

  it('moves keyboard focus across a month boundary and selects the new dates with Enter', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockImplementation(async (equipment_id, range) => ({ equipment_id, ...range, occupied_ranges: [], can_book: true }));
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<InteractiveCalendar onChange={changed} />);
    const lastNovemberDay = await screen.findByRole('button', { name: '30/11/2027: Disponible' });
    lastNovemberDay.focus();
    await user.keyboard('{ArrowRight}');
    const decemberStart = await screen.findByRole('button', { name: '01/12/2027: Disponible' });
    await waitFor(() => expect(decemberStart).toHaveFocus());
    expect(api.getPublicAvailabilityCalendar).toHaveBeenLastCalledWith(1, { start_date: '2027-12-01', end_date: '2028-01-01' }, expect.any(AbortSignal));
    await user.keyboard('{Enter}{ArrowRight}{Enter}');
    expect(changed).toHaveBeenLastCalledWith({ start_date: '2027-12-01', end_date: '2027-12-02' });
    expect(changed).toHaveBeenCalledTimes(2);
  });

  it('supports week edges, weekly movement and page keys without changing the selected range', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockImplementation(async (equipment_id, range) => ({ equipment_id, ...range, occupied_ranges: [], can_book: true }));
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<InteractiveCalendar onChange={changed} />);
    (await screen.findByRole('button', { name: '17/11/2027: Disponible' })).focus();
    await user.keyboard('{Home}');
    expect(screen.getByRole('button', { name: '15/11/2027: Disponible' })).toHaveFocus();
    await user.keyboard('{End}');
    expect(screen.getByRole('button', { name: '21/11/2027: Disponible' })).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('button', { name: '28/11/2027: Disponible' })).toHaveFocus();
    await user.keyboard('{ArrowUp}{PageDown}');
    await waitFor(() => expect(screen.getByRole('button', { name: '21/12/2027: Disponible' })).toHaveFocus());
    await user.keyboard('{PageUp}');
    await waitFor(() => expect(screen.getByRole('button', { name: '21/11/2027: Disponible' })).toHaveFocus());
    expect(changed).not.toHaveBeenCalled();
  });
});
