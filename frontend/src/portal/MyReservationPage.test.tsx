import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../api/client';
import type { CustomerReservation, PublicEquipment } from '../types/api';
import MyReservationPage from './MyReservationPage';

const equipment: PublicEquipment = { id: 3, name: 'Cámara Aurora', category: 'Cámaras', public_description: 'Cámara para vídeo.', technical_specs: {}, image_url: null, image_fallback_url: '/api/public/assets/equipment-placeholder.svg', active_reservations_count: 0 };
const reservation: CustomerReservation = { id: 41, equipment_id: 3, start_date: '2026-11-10', end_date: '2026-11-12', status: 'confirmed' };

function renderDetail(id = '41') {
  return render(<MemoryRouter initialEntries={[`/mis-reservas/${id}`]}><Routes><Route path="/mis-reservas/:id" element={<MyReservationPage />} /></Routes></MemoryRouter>);
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-11-01T12:00:00Z'));
  vi.spyOn(api, 'getMyReservation').mockResolvedValue(reservation);
  vi.spyOn(api, 'getPublicEquipment').mockResolvedValue(equipment);
  vi.spyOn(api, 'getPublicAvailability').mockResolvedValue({ equipment_id: 3, start_date: reservation.start_date, end_date: reservation.end_date, available: true, status: 'available' });
  vi.spyOn(api, 'cancelMyReservation').mockResolvedValue({ ...reservation, status: 'cancelled' });
  vi.spyOn(api, 'createMyIncident').mockResolvedValue({ id: 7, reservation_id: 41, title: 'Conector suelto', description: 'Se pierde la conexión.', status: 'open', public_response: '' });
  vi.spyOn(api, 'getEquipment');
});
afterEach(() => { vi.useRealTimers(); });

describe('own reservation detail', () => {
  it('shows the shared product name for an assigned sibling while retaining its reservation identity', async () => {
    vi.mocked(api.getMyReservation).mockResolvedValue({ ...reservation, equipment_id: 4 });
    renderDetail();
    expect(await screen.findByRole('link', { name: equipment.name })).toHaveAttribute('href', '/equipos/4');
    expect(api.getPublicEquipment).toHaveBeenCalledExactlyOnceWith(4);
    expect(screen.getByRole('heading', { name: 'Reserva #41' })).toBeInTheDocument();
    expect(screen.queryByText(/Equipo #4|unidades/i)).not.toBeInTheDocument();
  });

  it('requires explicit cancellation, manages focus and renders the persisted state and retained reference', async () => {
    const user = userEvent.setup();
    renderDetail();
    const cancel = await screen.findByRole('button', { name: 'Cancelar reserva' });
    await user.click(cancel);
    expect(api.cancelMyReservation).not.toHaveBeenCalled();
    const confirm = screen.getByRole('button', { name: 'Sí, cancelar reserva' });
    expect(confirm).toHaveFocus();
    await user.click(screen.getByRole('button', { name: 'Conservar reserva' }));
    expect(screen.getByRole('button', { name: 'Cancelar reserva' })).toHaveFocus();
    await user.click(screen.getByRole('button', { name: 'Cancelar reserva' }));
    vi.mocked(api.getMyReservation).mockResolvedValue({ ...reservation, status: 'cancelled' });
    await user.click(screen.getByRole('button', { name: 'Sí, cancelar reserva' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Reserva cancelada.');
    expect(screen.getByText('Cancelada')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Datos de tu reserva' })).toHaveFocus();
    expect(screen.getByText('#41')).toBeInTheDocument();
    expect(api.cancelMyReservation).toHaveBeenCalledExactlyOnceWith(41);
    expect(api.getMyReservation).toHaveBeenCalledTimes(2);
    expect(api.getPublicAvailability).toHaveBeenCalledExactlyOnceWith(3, { start_date: reservation.start_date, end_date: reservation.end_date });
    expect(await screen.findByText('Disponibilidad actualizada: el periodo vuelve a estar disponible.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Informar de un problema' })).not.toBeInTheDocument();
  });

  it('uses Madrid calendar day to hide cancellation from the start date, even before UTC midnight', async () => {
    vi.setSystemTime(new Date('2026-11-09T23:30:00Z'));
    renderDetail();
    expect(await screen.findByText(/El plazo de cancelación ha terminado/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancelar reserva' })).not.toBeInTheDocument();
    expect(api.cancelMyReservation).not.toHaveBeenCalled();
  });

  it('retains the reservation and announces a server cancellation conflict without pretending success', async () => {
    vi.mocked(api.cancelMyReservation).mockRejectedValue(new ApiError('Solo puedes cancelar antes del inicio de la reserva.', 409));
    const user = userEvent.setup();
    renderDetail();
    await user.click(await screen.findByRole('button', { name: 'Cancelar reserva' }));
    await user.click(screen.getByRole('button', { name: 'Sí, cancelar reserva' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Solo puedes cancelar antes del inicio');
    expect(screen.getByRole('alert')).toHaveFocus();
    expect(screen.getByText('Confirmada')).toBeInTheDocument();
    expect(screen.getByText('10/11/2026')).toBeInTheDocument();
    expect(screen.queryByText(/Reserva cancelada\./)).not.toBeInTheDocument();
  });

  it('shows 404 for an unavailable own-resource ID without consulting administration', async () => {
    vi.mocked(api.getMyReservation).mockRejectedValue(new ApiError('Reserva no encontrada.', 404));
    renderDetail('992');
    expect(await screen.findByRole('alert')).toHaveTextContent('Reserva no encontrada.');
    expect(api.getMyReservation).toHaveBeenCalledWith(992);
    expect(api.getEquipment).not.toHaveBeenCalled();
    expect(api.getPublicEquipment).not.toHaveBeenCalled();
  });

  it('retains a historical reservation if its equipment has been deactivated', async () => {
    vi.mocked(api.getPublicEquipment).mockRejectedValue(new ApiError('Equipo no encontrado.', 404));
    renderDetail();
    expect(await screen.findByRole('heading', { name: 'Equipo #3 (ficha no disponible)' })).toBeInTheDocument();
    expect(screen.getByText('10/11/2026')).toBeInTheDocument();
    expect(api.getEquipment).not.toHaveBeenCalled();
  });

  it('validates a problem form, preserves a failed submission and sends only title and description', async () => {
    vi.mocked(api.createMyIncident).mockRejectedValueOnce(new ApiError('Revisa los campos indicados.', 422, { description: 'Añade más detalle.' }));
    const user = userEvent.setup();
    renderDetail();
    await user.click(await screen.findByRole('button', { name: 'Informar de un problema' }));
    expect(screen.getByLabelText('Título del problema')).toHaveFocus();
    await user.click(screen.getByRole('button', { name: 'Enviar aviso' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Escribe un título');
    expect(api.createMyIncident).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Título del problema'), { target: { value: 'Conector suelto' } });
    fireEvent.change(screen.getByLabelText('Descripción del problema'), { target: { value: 'Se pierde la conexión.' } });
    await user.click(screen.getByRole('button', { name: 'Enviar aviso' }));
    expect(await screen.findByText('Añade más detalle.')).toBeInTheDocument();
    expect(screen.getByLabelText('Descripción del problema')).toHaveValue('Se pierde la conexión.');
    expect(screen.getByLabelText('Descripción del problema')).toHaveAttribute('aria-invalid', 'true');
    expect(api.createMyIncident).toHaveBeenLastCalledWith(41, { title: 'Conector suelto', description: 'Se pierde la conexión.' });
    await user.click(screen.getByRole('button', { name: 'Enviar aviso' }));
    expect(await screen.findByRole('link', { name: 'Consultar mis incidencias' })).toHaveAttribute('href', '/mis-incidencias');
    expect(screen.queryByLabelText('Descripción del problema')).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('keeps the report form unavailable for a cancelled reservation', async () => {
    vi.mocked(api.getMyReservation).mockResolvedValue({ ...reservation, status: 'cancelled' });
    renderDetail();
    await waitFor(() => expect(screen.getByText('Cancelada')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Informar de un problema' })).not.toBeInTheDocument();
  });

  it('prevents duplicate cancellation while the server is processing and waits for the persisted response', async () => {
    let finish!: (value: CustomerReservation) => void;
    vi.mocked(api.cancelMyReservation).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const user = userEvent.setup();
    renderDetail();
    await user.click(await screen.findByRole('button', { name: 'Cancelar reserva' }));
    await user.dblClick(screen.getByRole('button', { name: 'Sí, cancelar reserva' }));
    expect(api.cancelMyReservation).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Cancelando…' })).toBeDisabled();
    expect(screen.queryByText('Cancelada')).not.toBeInTheDocument();
    await act(async () => { finish({ ...reservation, status: 'cancelled' }); });
    expect(await screen.findByText('Cancelada')).toBeInTheDocument();
    expect(api.getPublicAvailability).toHaveBeenCalledTimes(1);
  });

  it('keeps a saved cancellation successful if refreshing public availability fails', async () => {
    vi.mocked(api.getPublicAvailability).mockRejectedValue(new ApiError('Sin conexión.', 0));
    const user = userEvent.setup();
    renderDetail();
    await user.click(await screen.findByRole('button', { name: 'Cancelar reserva' }));
    await user.click(screen.getByRole('button', { name: 'Sí, cancelar reserva' }));
    expect(await screen.findByText('La cancelación se ha guardado. No se pudo actualizar la disponibilidad; vuelve a la ficha del equipo para consultarla.')).toBeInTheDocument();
    expect(screen.getByText('Cancelada')).toBeInTheDocument();
    expect(api.cancelMyReservation).toHaveBeenCalledTimes(1);
  });
});
