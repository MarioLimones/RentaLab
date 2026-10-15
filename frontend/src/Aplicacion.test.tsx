import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { api, ErrorApi } from './api/cliente';
import Aplicacion from './Aplicacion';

const administrador = { authenticated: true as const, username: 'operador', expires_at: '2026-10-15T18:00:00Z', role: 'admin' as const, user: null };

function Ubicacion() {
  const ubicacion = useLocation();
  return <span data-testid="location">{ubicacion.pathname}{ubicacion.search}</span>;
}

beforeEach(() => {
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.spyOn(api, 'sesion').mockResolvedValue(administrador);
  vi.spyOn(api, 'saludServicio').mockResolvedValue({ status: 'ok' });
  vi.spyOn(api, 'listarEquipos').mockResolvedValue([]);
  vi.spyOn(api, 'listarReservas').mockResolvedValue([]);
  vi.spyOn(api, 'listarIncidencias').mockResolvedValue([]);
  vi.spyOn(api, 'listarEquiposPublicos').mockResolvedValue([]);
});

it("admite enlaces administrativos directos y navegación bajo /admin", async () => {
  const usuario = userEvent.setup();
  render(<MemoryRouter initialEntries={['/admin/importaciones']}><Aplicacion /><Ubicacion /></MemoryRouter>);
  expect(await screen.findByRole('navigation', { name: 'Principal' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { level: 1, name: 'Importaciones' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Importaciones' })).toHaveAttribute('aria-current', 'page');
  await usuario.click(screen.getByRole('link', { name: 'Equipos' }));
  expect(await screen.findByRole('heading', { level: 1, name: 'Equipos' })).toBeInTheDocument();
  expect(screen.getByTestId('location')).toHaveTextContent('/admin/equipos');
  expect(screen.getByRole('link', { name: 'Saltar al contenido' })).toHaveAttribute('href', '#main-content');
});

it("ofrece una salida pública para una ruta desconocida", async () => {
  render(<MemoryRouter initialEntries={['/ruta-inexistente']}><Aplicacion /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'Página no encontrada' })).toBeInTheDocument());
  expect(screen.getByRole('link', { name: 'Volver al catálogo' })).toHaveAttribute('href', '/catalogo');
  expect(screen.queryByRole('navigation', { name: 'Principal' })).not.toBeInTheDocument();
});

it("permite visitar el catálogo sin sesión ni solicitudes a la API privada", async () => {
  vi.mocked(api.sesion).mockRejectedValue(new ErrorApi('Se requiere iniciar sesión.', 401));
  render(<MemoryRouter initialEntries={['/catalogo']}><Aplicacion /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'El equipo para tu próxima idea.' })).toBeInTheDocument());
  expect(await screen.findByRole('link', { name: 'Acceder' })).toHaveAttribute('href', '/acceso?next=%2Fcatalogo');
  expect(screen.getByRole('link', { name: 'Crear cuenta' })).toHaveAttribute('href', '/registro?next=%2Fcatalogo');
  expect(screen.queryByRole('navigation', { name: 'Principal' })).not.toBeInTheDocument();
  expect(api.listarEquiposPublicos).toHaveBeenCalled();
  expect(api.listarEquipos).not.toHaveBeenCalled();
  expect(api.listarReservas).not.toHaveBeenCalled();
  expect(api.listarIncidencias).not.toHaveBeenCalled();
});

it("mantiene utilizable el catálogo público mientras se comprueba la sesión", async () => {
  let resolverSesion: ((valor: typeof administrador) => void) | undefined;
  vi.mocked(api.sesion).mockImplementation(() => new Promise((resolver) => { resolverSesion = resolver; }));
  render(<MemoryRouter initialEntries={['/catalogo']}><Aplicacion /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'El equipo para tu próxima idea.' })).toBeInTheDocument());
  expect(api.listarEquiposPublicos).toHaveBeenCalled();
  expect(api.listarEquipos).not.toHaveBeenCalled();
  await act(async () => { resolverSesion?.(administrador); });
});

it("abre el catálogo público desde la raíz de la aplicación", async () => {
  render(<MemoryRouter initialEntries={['/']}><Aplicacion /><Ubicacion /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'El equipo para tu próxima idea.' })).toBeInTheDocument());
  expect(screen.getByTestId('location')).toHaveTextContent('/catalogo');
});

it("conserva el equipo preseleccionado de un enlace administrativo antiguo de reserva", async () => {
  vi.mocked(api.listarEquipos).mockResolvedValue([{ id: 1, code: 'CAM-001', name: 'Cámara de prueba', category: 'Cámaras', description: '', active: true }]);
  render(<MemoryRouter initialEntries={['/reservas/nueva?equipment_id=1']}><Aplicacion /><Ubicacion /></MemoryRouter>);
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/admin/reservas/nueva?equipment_id=1'));
  await waitFor(() => expect(screen.getByLabelText('Equipo')).toHaveValue('1'));
  expect(screen.getByRole('navigation', { name: 'Principal' })).toBeInTheDocument();
});
