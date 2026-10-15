import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '../api/client';
import type { ImportReport } from '../api/client';
import ImportsPage from './ImportsPage';

const reservation = { id: 8, equipment_id: 1, customer_name: 'Aurora', customer_email: 'aurora@example.test', start_date: '2026-11-10', end_date: '2026-11-12', status: 'cancelled' as const, external_reference: 'PED-1' };
const report: ImportReport = {
  totals: { total: 3, accepted: 1, already_imported: 1, rejected: 1 },
  rows: [
    { line: 2, external_reference: 'PED-NEW', status: 'accepted', reservation: { ...reservation, id: 9, external_reference: 'PED-NEW', status: 'confirmed' }, message: 'Reserva creada.' },
    { line: 3, external_reference: 'PED-1', status: 'already_imported', reservation, message: 'La reserva ya estaba importada; se conserva sin cambios.' },
    { line: 4, external_reference: 'PED-2', status: 'rejected', reservation: null, message: 'El equipo tiene una incidencia bloqueante sin resolver.' },
  ],
};

beforeEach(() => vi.restoreAllMocks());

describe('CSV import screen', () => {
  it('uploads the real file and renders every server outcome, including a cancelled existing reservation', async () => {
    const user = userEvent.setup();
    const submit = vi.spyOn(api, 'importReservations').mockResolvedValue(report);
    render(<MemoryRouter><ImportsPage /></MemoryRouter>);
    expect(screen.getByRole('link', { name: /Descargar CSV/ })).toHaveAttribute('href', '/api/imports/example');
    const file = new File(['csv contents'], 'pedidos.csv', { type: 'text/csv' });
    await user.upload(screen.getByLabelText('Archivo CSV'), file);
    await user.click(screen.getByRole('button', { name: 'Importar pedidos' }));
    const table = await screen.findByRole('table', { name: 'Resultado de la importación' });
    expect(submit).toHaveBeenCalledWith(file);
    expect(within(table).getAllByRole('row')).toHaveLength(4);
    expect(within(table).getByText('Aceptada')).toBeInTheDocument();
    expect(within(table).getByText('Ya importada')).toBeInTheDocument();
    expect(within(table).getByText('Rechazada')).toBeInTheDocument();
    expect(within(table).getByText('Cancelada')).toBeInTheDocument();
    expect(within(table).getByText(/incidencia bloqueante/)).toBeInTheDocument();
    expect(within(table).getByRole('link', { name: 'Reserva #8' })).toHaveAttribute('href', '/admin/reservas/8');
    expect(screen.getByRole('status')).toHaveTextContent('3 filas procesadas');
  });

  it('retains the selected file after a global failure and allows a successful retry', async () => {
    const user = userEvent.setup();
    const submit = vi.spyOn(api, 'importReservations').mockRejectedValueOnce(new ApiError('La cabecera debe ser exactamente la indicada.', 422)).mockResolvedValueOnce(report);
    render(<MemoryRouter><ImportsPage /></MemoryRouter>);
    const file = new File(['bad header'], 'pedidos.csv', { type: 'text/csv' });
    const input = screen.getByLabelText<HTMLInputElement>('Archivo CSV');
    await user.upload(input, file);
    await user.click(screen.getByRole('button', { name: 'Importar pedidos' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('La cabecera debe ser exactamente la indicada.');
    expect(input.files?.[0]).toBe(file);
    await user.click(screen.getByRole('button', { name: 'Importar pedidos' }));
    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(submit).toHaveBeenCalledTimes(2);
  });

  it('does not submit without a file and marks the field with an associated error', async () => {
    const user = userEvent.setup();
    const submit = vi.spyOn(api, 'importReservations');
    render(<MemoryRouter><ImportsPage /></MemoryRouter>);
    await user.click(screen.getByRole('button', { name: 'Importar pedidos' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Selecciona un archivo CSV.');
    expect(screen.getByLabelText('Archivo CSV')).toHaveAttribute('aria-invalid', 'true');
    expect(submit).not.toHaveBeenCalled();
  });
});
