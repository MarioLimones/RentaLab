import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api, type Incidencia, type Reserva } from '../api/cliente';
import { PaginaResumen } from './PaginaResumen';

const reserva: Reserva = { id: 2, equipment_id: 1, customer_name: 'Estudio Nube', customer_email: 'nube@example.test', start_date: '2026-10-14', end_date: '2026-10-17', status: 'confirmed', external_reference: null };
const incidencia: Incidencia = { id: 4, equipment_id: 1, title: 'Sensor averiado', description: '', priority: 'high', blocking: true, status: 'open', resolution: '', confirmed_reservation_ids: [2], warning: 'Hay reservas confirmadas.' };

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, 'listarEquipos').mockResolvedValue([
    { id: 1, code: 'CAM-001', name: 'Cámara Aurora', category: 'Cámaras', description: '', active: true },
    { id: 2, code: 'AUD-001', name: 'Micrófono Brisa', category: 'Audio', description: '', active: false },
  ]);
  vi.spyOn(api, 'listarReservas').mockResolvedValue([reserva, { ...reserva, id: 3, status: 'cancelled', customer_name: 'Reserva cancelada' }, { ...reserva, id: 4, start_date: '2026-10-10', end_date: '2026-10-15', customer_name: 'Reserva finalizada' }]);
  vi.spyOn(api, 'listarIncidencias').mockResolvedValue([incidencia, { ...incidencia, id: 5, title: 'Funda revisada', status: 'resolved' }]);
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 9, 15, 12));
});

afterEach(() => vi.useRealTimers());

it('presenta cifras reales, incluye reservas en curso y omite canceladas o finalizadas', async () => {
  render(<MemoryRouter><PaginaResumen /></MemoryRouter>);
  await screen.findByRole('heading', { name: 'Resumen', level: 1 });
  expect(await screen.findByText('Equipos en catálogo')).toBeInTheDocument();
  expect(within(screen.getByText('Equipos en catálogo').closest('article')!).getByText('2')).toBeInTheDocument();
  expect(within(screen.getByText('Equipos activos').closest('article')!).getByText('1')).toBeInTheDocument();
  expect(within(screen.getByText('Reservas confirmadas').closest('article')!).getByText('2')).toBeInTheDocument();
  expect(within(screen.getByText('Incidencias sin resolver').closest('article')!).getByText('1')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Estudio Nube/ })).toHaveAttribute('href', '/admin/reservas/2');
  expect(screen.queryByText('Reserva cancelada')).not.toBeInTheDocument();
  expect(screen.queryByText('Reserva finalizada')).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Sensor averiado/ })).toHaveAttribute('href', '/admin/incidencias/4');
  expect(screen.queryByText('Funda revisada')).not.toBeInTheDocument();
  expect(screen.queryByText(/equipos disponibles/i)).not.toBeInTheDocument();
});

it('muestra estados vacíos cuando todavía no hay actividad', async () => {
  vi.mocked(api.listarEquipos).mockResolvedValue([]);
  vi.mocked(api.listarReservas).mockResolvedValue([]);
  vi.mocked(api.listarIncidencias).mockResolvedValue([]);
  render(<MemoryRouter><PaginaResumen /></MemoryRouter>);
  expect(await screen.findByText('No hay próximas reservas')).toBeInTheDocument();
  expect(screen.getByText('Sin incidencias bloqueantes')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Crear primer equipo' })).toHaveAttribute('href', '/admin/equipos/nuevo');
});
