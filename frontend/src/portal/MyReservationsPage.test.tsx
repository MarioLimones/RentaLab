import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../api/client';
import { AuthContext } from '../auth/context';
import type { CustomerReservation, PublicEquipment } from '../types/api';
import MyAccountPage from './MyAccountPage';
import MyIncidentsPage from './MyIncidentsPage';
import MyReservationsPage from './MyReservationsPage';

const equipment: PublicEquipment = { id: 3, name: 'Cámara Aurora', category: 'Cámaras', public_description: 'Cámara para vídeo.', technical_specs: { Resolución: '4K' }, image_url: null, image_fallback_url: '/api/public/assets/equipment-placeholder.svg', active_reservations_count: 0 };
const reservation: CustomerReservation = { id: 41, equipment_id: 3, start_date: '2026-11-10', end_date: '2026-11-12', status: 'confirmed' };

beforeEach(() => {
  vi.spyOn(api, 'listMyReservations').mockResolvedValue([reservation]);
  vi.spyOn(api, 'getPublicEquipment').mockResolvedValue(equipment);
  vi.spyOn(api, 'listMyIncidents').mockResolvedValue([]);
  vi.spyOn(api, 'listReservations');
  vi.spyOn(api, 'getEquipment');
});

describe('my reservations', () => {
  it('renders the own API response, confirmed and cancelled history, with calendar dates and private detail links', async () => {
    vi.mocked(api.listMyReservations).mockResolvedValue([reservation, { ...reservation, id: 42, status: 'cancelled' }]);
    render(<MemoryRouter><MyReservationsPage /></MemoryRouter>);
    const list = await screen.findByRole('list', { name: 'Tus reservas' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(within(list).getByText('Confirmada')).toBeInTheDocument();
    expect(within(list).getByText('Cancelada')).toBeInTheDocument();
    expect(within(list).getAllByText('10/11/2026')).toHaveLength(2);
    expect(screen.getByRole('link', { name: 'Ver reserva #41' })).toHaveAttribute('href', '/mis-reservas/41');
    expect(api.listMyReservations).toHaveBeenCalledTimes(1);
    expect(api.getPublicEquipment).toHaveBeenCalledTimes(1);
    expect(api.listReservations).not.toHaveBeenCalled();
    expect(api.getEquipment).not.toHaveBeenCalled();
    expect(screen.queryByRole('link', { name: /administración/i })).not.toBeInTheDocument();
  });

  it('keeps historical reservations visible when their equipment no longer has a public detail', async () => {
    vi.mocked(api.getPublicEquipment).mockRejectedValue(new ApiError('Equipo no encontrado.', 404));
    render(<MemoryRouter><MyReservationsPage /></MemoryRouter>);
    expect(await screen.findByRole('link', { name: 'Equipo #3 (ficha no disponible)' })).toHaveAttribute('href', '/mis-reservas/41');
    expect(api.getEquipment).not.toHaveBeenCalled();
  });

  it('resolves a hidden sibling unit by its assigned id and shows the shared public product name', async () => {
    vi.mocked(api.listMyReservations).mockResolvedValue([{ ...reservation, equipment_id: 4 }]);
    vi.mocked(api.getPublicEquipment).mockResolvedValue(equipment);
    render(<MemoryRouter><MyReservationsPage /></MemoryRouter>);
    expect(await screen.findByRole('link', { name: equipment.name })).toHaveAttribute('href', '/mis-reservas/41');
    expect(api.getPublicEquipment).toHaveBeenCalledExactlyOnceWith(4);
    expect(screen.queryByText(/Equipo #4|unidades/i)).not.toBeInTheDocument();
  });

  it('provides a catalogue path for an empty own list without querying equipment', async () => {
    vi.mocked(api.listMyReservations).mockResolvedValue([]);
    render(<MemoryRouter><MyReservationsPage /></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: 'Todavía no tienes reservas' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Explorar el catálogo' })).toHaveAttribute('href', '/catalogo');
    expect(api.getPublicEquipment).not.toHaveBeenCalled();
  });

  it('announces a failed load and lets the customer retry', async () => {
    vi.mocked(api.listMyReservations).mockRejectedValueOnce(new ApiError('No se pudieron consultar tus reservas.', 503));
    const user = userEvent.setup();
    render(<MemoryRouter><MyReservationsPage /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudieron consultar tus reservas.');
    await user.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByRole('link', { name: 'Ver reserva #41' })).toBeInTheDocument();
  });

  it('does not replace an equipment network error with a misleading inactive-equipment label', async () => {
    vi.mocked(api.getPublicEquipment).mockRejectedValue(new ApiError('No hay conexión.', 0));
    render(<MemoryRouter><MyReservationsPage /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('No hay conexión.');
    expect(screen.queryByText(/ficha no disponible/)).not.toBeInTheDocument();
  });
});

describe('my incidents and account', () => {
  it('shows own notices, their public state and only the public administrator reply', async () => {
    vi.mocked(api.listMyIncidents).mockResolvedValue([
      { id: 7, reservation_id: 41, title: 'Conector suelto', description: 'Se pierde la conexión.', status: 'open', public_response: '' },
      { id: 8, reservation_id: 42, title: 'Consulta del objetivo', description: 'Falta la tapa.', status: 'resolved', public_response: 'Hemos preparado una tapa de repuesto.' },
    ]);
    render(<MemoryRouter><MyIncidentsPage /></MemoryRouter>);
    const list = await screen.findByRole('list', { name: 'Tus incidencias' });
    expect(within(list).getByText('Pendiente de gestión')).toBeInTheDocument();
    expect(within(list).getByText('Resuelta')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Respuesta al aviso #7' })).toHaveTextContent('Pendiente de respuesta.');
    expect(screen.getByRole('region', { name: 'Respuesta al aviso #8' })).toHaveTextContent('Hemos preparado una tapa de repuesto.');
    expect(screen.queryByText(/prioridad|bloqueante|resolución interna|notas internas/i)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Reserva #41' })).toHaveAttribute('href', '/mis-reservas/41');
  });

  it('explains how to report a problem when there are no own notices', async () => {
    render(<MemoryRouter><MyIncidentsPage /></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: 'No has enviado ningún aviso' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver mis reservas' })).toHaveAttribute('href', '/mis-reservas');
  });

  it('reads identity from the actual session without exposing profile or permission editing', async () => {
    const user = { id: 12, name: 'Lucía Demo', email: 'lucia@example.test', role: 'customer' as const, active: true };
    render(<MemoryRouter><AuthContext.Provider value={{ session: { authenticated: true, username: user.email, role: 'customer', user, expires_at: '2026-12-12T12:00:00Z' }, checking: false, checkError: null, expired: false, checkSession: vi.fn(), login: vi.fn(), logout: vi.fn() }}><MyAccountPage /></AuthContext.Provider></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('Lucía Demo')).toBeInTheDocument());
    expect(screen.getByText('lucia@example.test')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });
});
