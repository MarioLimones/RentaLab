import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../api/client';
import type { Availability, Equipment, Reservation } from '../api/client';
import ReservationDetailPage from './ReservationDetailPage';
import ReservationFormPage from './ReservationFormPage';
import ReservationsPage from './ReservationsPage';

const equipment: Equipment[] = [
  { id: 1, code: 'CAM-001', name: 'Cámara Aurora', category: 'Cámaras', description: '', active: true },
  { id: 2, code: 'AUD-001', name: 'Micrófono Brisa', category: 'Sonido', description: '', active: false },
];
const reservation: Reservation = {
  id: 8, equipment_id: 1, customer_name: 'Estudio Ficticio', customer_email: 'estudio@example.test',
  start_date: '2026-11-10', end_date: '2026-11-12', status: 'confirmed', external_reference: 'DEMO-8',
};

function renderPage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/admin/reservas" element={<ReservationsPage />} />
        <Route path="/admin/reservas/nueva" element={<ReservationFormPage />} />
        <Route path="/admin/reservas/:id" element={<ReservationDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function fillReservation() {
  const user = userEvent.setup();
  await screen.findByRole('option', { name: /CAM-001/ });
  await user.selectOptions(screen.getByLabelText('Equipo'), '1');
  await user.type(screen.getByLabelText('Nombre del cliente'), 'Estudio Ficticio');
  await user.type(screen.getByLabelText('Correo del cliente'), 'estudio@example.test');
  fireEvent.change(screen.getByLabelText('Fecha de inicio'), { target: { value: '2026-11-10' } });
  fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2026-11-12' } });
  await user.type(screen.getByLabelText(/Referencia externa/), 'DEMO-8');
  return user;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, 'listEquipment').mockResolvedValue(equipment);
  vi.spyOn(api, 'listReservations').mockResolvedValue([reservation]);
  vi.spyOn(api, 'getReservation').mockResolvedValue(reservation);
  vi.spyOn(api, 'getEquipment').mockResolvedValue(equipment[0]!);
  vi.spyOn(api, 'createReservation').mockResolvedValue(reservation);
  vi.spyOn(api, 'cancelReservation').mockResolvedValue({ ...reservation, status: 'cancelled' });
  vi.spyOn(api, 'getEquipmentAvailability').mockResolvedValue({
    equipment_id: 1, start_date: '2026-11-10', end_date: '2026-11-12', available: true,
    reason: null, conflicting_reservation_ids: [],
  });
});

describe('reservation form', () => {
  it('preserves all inputs after a conflict, focuses the explanation and retries successfully', async () => {
    vi.mocked(api.createReservation).mockRejectedValueOnce(new ApiError('El equipo ya tiene una reserva confirmada en ese intervalo.', 409));
    renderPage('/admin/reservas/nueva');
    const user = await fillReservation();
    await user.click(screen.getByRole('button', { name: 'Crear reserva' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('El equipo ya tiene una reserva confirmada');
    expect(alert).toHaveFocus();
    expect(screen.getByLabelText('Equipo')).toHaveValue('1');
    expect(screen.getByLabelText('Nombre del cliente')).toHaveValue('Estudio Ficticio');
    expect(screen.getByLabelText('Correo del cliente')).toHaveValue('estudio@example.test');
    expect(screen.getByLabelText('Fecha de inicio')).toHaveValue('2026-11-10');
    expect(screen.getByLabelText('Fecha de fin')).toHaveValue('2026-11-12');
    expect(screen.getByLabelText(/Referencia externa/)).toHaveValue('DEMO-8');
    fireEvent.change(screen.getByLabelText('Fecha de inicio'), { target: { value: '2026-11-12' } });
    fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2026-11-14' } });
    await user.click(screen.getByRole('button', { name: 'Crear reserva' }));
    expect(await screen.findByRole('heading', { name: 'Reserva #8' })).toBeInTheDocument();
    expect(api.createReservation).toHaveBeenLastCalledWith({
      equipment_id: 1, customer_name: 'Estudio Ficticio', customer_email: 'estudio@example.test',
      start_date: '2026-11-12', end_date: '2026-11-14', external_reference: 'DEMO-8',
    });
  });

  it('preselects equipment, labels inactive units and sends dates without a timezone conversion', async () => {
    renderPage('/admin/reservas/nueva?equipment_id=2');
    const inactive = await screen.findByRole('option', { name: /AUD-001.*inactivo/i });
    expect(inactive).toBeEnabled();
    expect(screen.getByLabelText('Equipo')).toHaveValue('2');
    const user = await fillReservation();
    await user.clear(screen.getByLabelText(/Referencia externa/));
    await user.click(screen.getByRole('button', { name: 'Crear reserva' }));
    await waitFor(() => expect(api.createReservation).toHaveBeenCalledWith({
      equipment_id: 1, customer_name: 'Estudio Ficticio', customer_email: 'estudio@example.test',
      start_date: '2026-11-10', end_date: '2026-11-12', external_reference: null,
    }));
  });

  it('displays availability for the exact equipment and range, hides it when dates change and still submits a blocked range', async () => {
    vi.mocked(api.getEquipmentAvailability).mockResolvedValue({
      equipment_id: 1, start_date: '2026-11-10', end_date: '2026-11-12', available: false,
      reason: 'blocking_incident', conflicting_reservation_ids: [],
    });
    renderPage('/admin/reservas/nueva');
    const user = await fillReservation();
    await user.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
    const result = await screen.findByRole('region', { name: 'Resultado de disponibilidad' });
    expect(result).toHaveTextContent('CAM-001');
    expect(result).toHaveTextContent('10/11/2026');
    expect(result).toHaveTextContent('12/11/2026');
    expect(result).toHaveTextContent(/incidencia bloqueante/i);
    expect(api.getEquipmentAvailability).toHaveBeenCalledWith(1, { start_date: '2026-11-10', end_date: '2026-11-12' });
    fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2026-11-13' } });
    expect(screen.queryByRole('region', { name: 'Resultado de disponibilidad' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Crear reserva' }));
    expect(api.createReservation).toHaveBeenCalledTimes(1);
  });

  it('does not show an old availability result arriving after the queried range changed', async () => {
    let finish!: (value: Availability) => void;
    vi.mocked(api.getEquipmentAvailability).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    renderPage('/admin/reservas/nueva');
    const user = await fillReservation();
    await user.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
    fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2026-11-14' } });
    finish({ equipment_id: 1, start_date: '2026-11-10', end_date: '2026-11-12', available: true, reason: null, conflicting_reservation_ids: [] });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Consultar disponibilidad' })).toBeEnabled());
    expect(screen.queryByRole('region', { name: 'Resultado de disponibilidad' })).not.toBeInTheDocument();
  });
});

describe('reservation detail', () => {
  it('requires explicit inline confirmation and renders the cancelled response without erasing history', async () => {
    renderPage('/admin/reservas/8');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Cancelar reserva' }));
    expect(api.cancelReservation).not.toHaveBeenCalled();
    const confirmation = screen.getByRole('group', { name: 'Confirmar cancelación' });
    expect(confirmation).toHaveTextContent('historial');
    await user.click(within(confirmation).getByRole('button', { name: 'Volver' }));
    expect(screen.queryByRole('group', { name: 'Confirmar cancelación' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancelar reserva' })).toHaveFocus();
    await user.click(screen.getByRole('button', { name: 'Cancelar reserva' }));
    await user.click(screen.getByRole('button', { name: 'Sí, cancelar reserva' }));
    await waitFor(() => expect(api.cancelReservation).toHaveBeenCalledWith(8));
    expect(await screen.findByText('Cancelada')).toBeInTheDocument();
    expect(screen.getByText('Estudio Ficticio')).toBeInTheDocument();
    expect(screen.getByText('DEMO-8')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancelar reserva' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Datos de la reserva' })).toHaveFocus();
  });
});

describe('reservation list filters', () => {
  it('sends customer, owner and origin together with the existing server filters', async () => {
    renderPage('/admin/reservas?customer_user_id=27');
    await screen.findByRole('link', { name: 'Ver reserva #8' });
    expect(api.listReservations).toHaveBeenCalledWith({ customer_user_id: 27 });
    expect(screen.getByLabelText('ID de cuenta')).toHaveValue('27');
    fireEvent.change(screen.getByLabelText('Cliente'), { target: { value: '  estudio@example.test  ' } });
    fireEvent.change(screen.getByLabelText('Origen'), { target: { value: 'portal' } });
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }));
    await waitFor(() => expect(api.listReservations).toHaveBeenLastCalledWith({ customer: 'estudio@example.test', customer_user_id: 27, origin: 'portal' }));
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }));
    await waitFor(() => expect(api.listReservations).toHaveBeenLastCalledWith({}));
  });

  it('identifies account ownership and leaves unowned imports and history explicit', async () => {
    vi.mocked(api.listReservations).mockResolvedValue([
      { ...reservation, customer_user_id: 27, origin: 'portal' },
      { ...reservation, id: 9, customer_user_id: null, origin: 'csv' },
      { ...reservation, id: 10, customer_user_id: null, origin: 'legacy' },
    ]);
    renderPage('/admin/reservas');
    await screen.findByRole('link', { name: 'Ver reserva #10' });
    expect(screen.getByText('Cuenta cliente #27')).toBeInTheDocument();
    expect(screen.getAllByText('Sin propietario de cuenta')).toHaveLength(2);
    expect(screen.getByText('Importación CSV', { selector: '.cell-subtitle' })).toBeInTheDocument();
    expect(screen.getByText('Histórico · origen no conocido', { selector: '.cell-subtitle' })).toBeInTheDocument();
  });

  it('loads updated reservations after cancelling and returning to the list', async () => {
    vi.mocked(api.cancelReservation).mockImplementation(async () => {
      const cancelled = { ...reservation, status: 'cancelled' as const };
      vi.mocked(api.listReservations).mockResolvedValue([cancelled]);
      return cancelled;
    });
    renderPage('/admin/reservas');
    fireEvent.click(await screen.findByRole('link', { name: 'Ver reserva #8' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar reserva' }));
    fireEvent.click(screen.getByRole('button', { name: 'Sí, cancelar reserva' }));
    await screen.findByText('Cancelada');
    fireEvent.click(screen.getByRole('link', { name: '← Reservas' }));
    expect(await screen.findByText('Cancelada')).toBeInTheDocument();
    expect(api.listReservations).toHaveBeenCalledTimes(2);
  });
  it('combines server filters and explains that the date interval selects overlaps', async () => {
    renderPage('/admin/reservas');
    const user = userEvent.setup();
    await screen.findByRole('link', { name: 'Ver reserva #8' });
    await user.selectOptions(screen.getByLabelText('Equipo'), '1');
    await user.selectOptions(screen.getByLabelText('Estado'), 'confirmed');
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-11-11' } });
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-11-20' } });
    await user.click(screen.getByRole('button', { name: 'Aplicar filtros' }));
    await waitFor(() => expect(api.listReservations).toHaveBeenLastCalledWith({
      equipment_id: 1, status: 'confirmed', start_date: '2026-11-11', end_date: '2026-11-20',
    }));
    expect(screen.getByText(/solapan el intervalo/i)).toBeInTheDocument();
  });

  it('keeps an incomplete date filter in the form and does not send it to the server', async () => {
    renderPage('/admin/reservas');
    const user = userEvent.setup();
    await screen.findByRole('link', { name: 'Ver reserva #8' });
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-11-11' } });
    await user.click(screen.getByRole('button', { name: 'Aplicar filtros' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/ambas fechas/i);
    expect(screen.getByLabelText('Desde')).toHaveValue('2026-11-11');
    expect(api.listReservations).toHaveBeenCalledTimes(1);
  });
});
