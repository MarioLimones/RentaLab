import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, type PublicReservationDates } from '../api/client';
import { CatalogueReservations } from './CatalogueReservations';

const props = { id: 15, name: 'Altavoz activo Onda S12', count: 3, today: '2027-11-01' };
const dates: PublicReservationDates = {
  equipment_id: 15,
  reservations: [
    { start_date: '2027-10-31', end_date: '2027-11-03' },
    { start_date: '2027-11-10', end_date: '2027-11-12' },
    { start_date: '2027-11-10', end_date: '2027-11-12' },
  ],
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, 'getPublicReservationDates').mockResolvedValue(dates);
});

describe('catalogue reservation dates', () => {
  it('loads only on demand and shows separate original pickup/return ranges including duplicates', async () => {
    render(<CatalogueReservations {...props} />);
    const user = userEvent.setup();
    const button = screen.getByRole('button', { name: `Ver fechas de 3 reservas de ${props.name}` });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    expect(api.getPublicReservationDates).not.toHaveBeenCalled();
    button.focus();
    await user.keyboard('{Enter}');
    const list = await screen.findByRole('list', { name: `Fechas reservadas de ${props.name}` });
    expect(button).toHaveFocus();
    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('region')).toHaveAttribute('id', button.getAttribute('aria-controls'));
    expect(within(list).getAllByRole('listitem')).toHaveLength(3);
    expect(within(list).getByText('31/10/2027')).toHaveAttribute('datetime', '2027-10-31');
    expect(within(list).getByText('03/11/2027')).toHaveAttribute('datetime', '2027-11-03');
    expect(within(list).getAllByText('10/11/2027')).toHaveLength(2);
    expect(within(list).getAllByText('12/11/2027')).toHaveLength(2);
    expect(screen.getByText('El día de devolución no se incluye en el alquiler.')).toBeInTheDocument();
    expect(api.getPublicReservationDates).toHaveBeenCalledExactlyOnceWith(15, expect.any(AbortSignal));
  });

  it('allows checking an empty count and handles reservations cancelled since the catalogue loaded', async () => {
    vi.mocked(api.getPublicReservationDates).mockResolvedValue({ equipment_id: 15, reservations: [] });
    render(<CatalogueReservations {...props} count={0} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: `Ver fechas de 0 reservas de ${props.name}` }));
    expect(await screen.findByText('No hay reservas en curso ni próximas.')).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('updates the displayed count from fresh dates instead of keeping an outdated total', async () => {
    vi.mocked(api.getPublicReservationDates).mockResolvedValue({ equipment_id: 15, reservations: [dates.reservations[0]!] });
    render(<CatalogueReservations {...props} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button'));
    expect(await screen.findByRole('button', { name: `Ocultar fechas de 1 reserva de ${props.name}` })).toBeInTheDocument();
    await user.click(screen.getByRole('button'));
    expect(screen.getByRole('button', { name: `Ver fechas de 1 reserva de ${props.name}` })).toBeInTheDocument();
  });

  it('offers a retry after a failed read and preserves focus for closing with Escape', async () => {
    vi.mocked(api.getPublicReservationDates).mockRejectedValueOnce(new Error('No se pudieron cargar las fechas.'));
    render(<CatalogueReservations {...props} />);
    const user = userEvent.setup();
    const trigger = screen.getByRole('button');
    await user.click(trigger);
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudieron cargar las fechas.');
    await user.click(screen.getByRole('button', { name: 'Reintentar fechas' }));
    expect(await screen.findByRole('list')).toBeInTheDocument();
    expect(api.getPublicReservationDates).toHaveBeenCalledTimes(2);
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('aborts when closed, rechecks on reopening and ignores an older late response', async () => {
    let finish!: (value: PublicReservationDates) => void;
    vi.mocked(api.getPublicReservationDates).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }))
      .mockResolvedValueOnce({ equipment_id: 15, reservations: [] });
    render(<CatalogueReservations {...props} />);
    const user = userEvent.setup();
    const trigger = screen.getByRole('button');
    await user.click(trigger);
    expect(screen.getByRole('status')).toHaveTextContent('Cargando fechas…');
    const signal = vi.mocked(api.getPublicReservationDates).mock.calls[0]![1]!;
    await user.keyboard('{Escape}');
    expect(signal.aborted).toBe(true);
    expect(trigger).toHaveFocus();
    await user.keyboard(' ');
    await screen.findByText('No hay reservas en curso ni próximas.');
    await act(async () => { finish(dates); });
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
    expect(screen.getByText('No hay reservas en curso ni próximas.')).toBeInTheDocument();
    expect(api.getPublicReservationDates).toHaveBeenCalledTimes(2);
  });

  it('refreshes an open disclosure when the Madrid business day changes and aborts on unmount', async () => {
    const { rerender, unmount } = render(<CatalogueReservations {...props} />);
    await userEvent.setup().click(screen.getByRole('button'));
    await screen.findByRole('list');
    vi.mocked(api.getPublicReservationDates).mockResolvedValue({ equipment_id: 15, reservations: [] });
    rerender(<CatalogueReservations {...props} today="2027-11-02" />);
    await screen.findByText('No hay reservas en curso ni próximas.');
    await waitFor(() => expect(api.getPublicReservationDates).toHaveBeenCalledTimes(2));
    const signal = vi.mocked(api.getPublicReservationDates).mock.calls[1]![1]!;
    expect(signal.aborted).toBe(false);
    unmount();
    expect(signal.aborted).toBe(true);
  });
});
