import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { api, ApiError } from './api/client';
import App from './App';

const administrator = { authenticated: true as const, username: 'operador', expires_at: '2026-10-15T18:00:00Z', role: 'admin' as const, user: null };

function Location() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}{location.search}</span>;
}

beforeEach(() => {
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.spyOn(api, 'session').mockResolvedValue(administrator);
  vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok' });
  vi.spyOn(api, 'listEquipment').mockResolvedValue([]);
  vi.spyOn(api, 'listReservations').mockResolvedValue([]);
  vi.spyOn(api, 'listIncidents').mockResolvedValue([]);
  vi.spyOn(api, 'listPublicEquipment').mockResolvedValue([]);
});

it('supports administrative deep links and navigation under /admin', async () => {
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/admin/importaciones']}><App /><Location /></MemoryRouter>);
  expect(await screen.findByRole('navigation', { name: 'Principal' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { level: 1, name: 'Importaciones' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Importaciones' })).toHaveAttribute('aria-current', 'page');
  await user.click(screen.getByRole('link', { name: 'Equipos' }));
  expect(await screen.findByRole('heading', { level: 1, name: 'Equipos' })).toBeInTheDocument();
  expect(screen.getByTestId('location')).toHaveTextContent('/admin/equipos');
  expect(screen.getByRole('link', { name: 'Saltar al contenido' })).toHaveAttribute('href', '#main-content');
});

it('provides a public recovery for an unknown route', async () => {
  render(<MemoryRouter initialEntries={['/ruta-inexistente']}><App /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'Página no encontrada' })).toBeInTheDocument());
  expect(screen.getByRole('link', { name: 'Volver al catálogo' })).toHaveAttribute('href', '/catalogo');
  expect(screen.queryByRole('navigation', { name: 'Principal' })).not.toBeInTheDocument();
});

it('lets a visitor browse the catalogue without a session or private API requests', async () => {
  vi.mocked(api.session).mockRejectedValue(new ApiError('Se requiere iniciar sesión.', 401));
  render(<MemoryRouter initialEntries={['/catalogo']}><App /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'El equipo para tu próxima idea.' })).toBeInTheDocument());
  expect(await screen.findByRole('link', { name: 'Acceder' })).toHaveAttribute('href', '/acceso?next=%2Fcatalogo');
  expect(screen.getByRole('link', { name: 'Crear cuenta' })).toHaveAttribute('href', '/registro?next=%2Fcatalogo');
  expect(screen.queryByRole('navigation', { name: 'Principal' })).not.toBeInTheDocument();
  expect(api.listPublicEquipment).toHaveBeenCalled();
  expect(api.listEquipment).not.toHaveBeenCalled();
  expect(api.listReservations).not.toHaveBeenCalled();
  expect(api.listIncidents).not.toHaveBeenCalled();
});

it('keeps public catalogue access usable while the session is being checked', async () => {
  let resolveSession: ((value: typeof administrator) => void) | undefined;
  vi.mocked(api.session).mockImplementation(() => new Promise((resolve) => { resolveSession = resolve; }));
  render(<MemoryRouter initialEntries={['/catalogo']}><App /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'El equipo para tu próxima idea.' })).toBeInTheDocument());
  expect(api.listPublicEquipment).toHaveBeenCalled();
  expect(api.listEquipment).not.toHaveBeenCalled();
  await act(async () => { resolveSession?.(administrator); });
});

it('opens the public catalogue from the application root', async () => {
  render(<MemoryRouter initialEntries={['/']}><App /><Location /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'El equipo para tu próxima idea.' })).toBeInTheDocument());
  expect(screen.getByTestId('location')).toHaveTextContent('/catalogo');
});

it('preserves the preselected equipment in an old administrative reservation link', async () => {
  vi.mocked(api.listEquipment).mockResolvedValue([{ id: 1, code: 'CAM-001', name: 'Cámara de prueba', category: 'Cámaras', description: '', active: true }]);
  render(<MemoryRouter initialEntries={['/reservas/nueva?equipment_id=1']}><App /><Location /></MemoryRouter>);
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/admin/reservas/nueva?equipment_id=1'));
  await waitFor(() => expect(screen.getByLabelText('Equipo')).toHaveValue('1'));
  expect(screen.getByRole('navigation', { name: 'Principal' })).toBeInTheDocument();
});
