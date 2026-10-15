import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ErrorApi } from '../api/cliente';
import { ContextoAutenticacion } from '../autenticacion/contexto';
import type { ReservaCliente, EquipoPublico } from '../tipos/api';
import PaginaMiCuenta from './PaginaMiCuenta';
import PaginaMisIncidencias from './PaginaMisIncidencias';
import PaginaMisReservas from './PaginaMisReservas';

const equipo: EquipoPublico = { id: 3, name: 'Cámara Aurora', category: 'Cámaras', public_description: 'Cámara para vídeo.', technical_specs: { Resolución: '4K' }, image_url: null, image_fallback_url: '/api/public/assets/equipment-placeholder.svg', active_reservations_count: 0 };
const reserva: ReservaCliente = { id: 41, equipment_id: 3, start_date: '2026-11-10', end_date: '2026-11-12', status: 'confirmed' };

beforeEach(() => {
  vi.spyOn(api, 'listarMisReservas').mockResolvedValue([reserva]);
  vi.spyOn(api, 'obtenerEquipoPublico').mockResolvedValue(equipo);
  vi.spyOn(api, 'listarMisIncidencias').mockResolvedValue([]);
  vi.spyOn(api, 'listarReservas');
  vi.spyOn(api, 'obtenerEquipo');
});

describe("mis reservas", () => {
  it("muestra la respuesta propia de la API y el historial confirmado y cancelado con fechas y enlaces privados de detalle", async () => {
    vi.mocked(api.listarMisReservas).mockResolvedValue([reserva, { ...reserva, id: 42, status: 'cancelled' }]);
    render(<MemoryRouter><PaginaMisReservas /></MemoryRouter>);
    const lista = await screen.findByRole('list', { name: 'Tus reservas' });
    expect(within(lista).getAllByRole('listitem')).toHaveLength(2);
    expect(within(lista).getByText('Confirmada')).toBeInTheDocument();
    expect(within(lista).getByText('Cancelada')).toBeInTheDocument();
    expect(within(lista).getAllByText('10/11/2026')).toHaveLength(2);
    expect(screen.getByRole('link', { name: 'Ver reserva #41' })).toHaveAttribute('href', '/mis-reservas/41');
    expect(api.listarMisReservas).toHaveBeenCalledTimes(1);
    expect(api.obtenerEquipoPublico).toHaveBeenCalledTimes(1);
    expect(api.listarReservas).not.toHaveBeenCalled();
    expect(api.obtenerEquipo).not.toHaveBeenCalled();
    expect(screen.queryByRole('link', { name: /administración/i })).not.toBeInTheDocument();
  });

  it("mantiene visibles las reservas históricas cuando su equipo ya no tiene detalle público", async () => {
    vi.mocked(api.obtenerEquipoPublico).mockRejectedValue(new ErrorApi('Equipo no encontrado.', 404));
    render(<MemoryRouter><PaginaMisReservas /></MemoryRouter>);
    expect(await screen.findByRole('link', { name: 'Equipo #3 (ficha no disponible)' })).toHaveAttribute('href', '/mis-reservas/41');
    expect(api.obtenerEquipo).not.toHaveBeenCalled();
  });

  it("resuelve una unidad hermana oculta por su identificador asignado y muestra el nombre público compartido del producto", async () => {
    vi.mocked(api.listarMisReservas).mockResolvedValue([{ ...reserva, equipment_id: 4 }]);
    vi.mocked(api.obtenerEquipoPublico).mockResolvedValue(equipo);
    render(<MemoryRouter><PaginaMisReservas /></MemoryRouter>);
    expect(await screen.findByRole('link', { name: equipo.name })).toHaveAttribute('href', '/mis-reservas/41');
    expect(api.obtenerEquipoPublico).toHaveBeenCalledExactlyOnceWith(4);
    expect(screen.queryByText(/Equipo #4|unidades/i)).not.toBeInTheDocument();
  });

  it("ofrece una ruta al catálogo si la lista propia está vacía sin consultar equipos", async () => {
    vi.mocked(api.listarMisReservas).mockResolvedValue([]);
    render(<MemoryRouter><PaginaMisReservas /></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: 'Todavía no tienes reservas' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Explorar el catálogo' })).toHaveAttribute('href', '/catalogo');
    expect(api.obtenerEquipoPublico).not.toHaveBeenCalled();
  });

  it("anuncia una carga fallida y permite al cliente reintentar", async () => {
    vi.mocked(api.listarMisReservas).mockRejectedValueOnce(new ErrorApi('No se pudieron consultar tus reservas.', 503));
    const usuario = userEvent.setup();
    render(<MemoryRouter><PaginaMisReservas /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudieron consultar tus reservas.');
    await usuario.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByRole('link', { name: 'Ver reserva #41' })).toBeInTheDocument();
  });

  it("evita sustituir un error de red de equipos por una etiqueta engañosa de equipo inactivo", async () => {
    vi.mocked(api.obtenerEquipoPublico).mockRejectedValue(new ErrorApi('No hay conexión.', 0));
    render(<MemoryRouter><PaginaMisReservas /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('No hay conexión.');
    expect(screen.queryByText(/ficha no disponible/)).not.toBeInTheDocument();
  });
});

describe("mis incidencias y cuenta", () => {
  it("muestra avisos propios, su estado público y únicamente la respuesta pública de administración", async () => {
    vi.mocked(api.listarMisIncidencias).mockResolvedValue([
      { id: 7, reservation_id: 41, title: 'Conector suelto', description: 'Se pierde la conexión.', status: 'open', public_response: '' },
      { id: 8, reservation_id: 42, title: 'Consulta del objetivo', description: 'Falta la tapa.', status: 'resolved', public_response: 'Hemos preparado una tapa de repuesto.' },
    ]);
    render(<MemoryRouter><PaginaMisIncidencias /></MemoryRouter>);
    const lista = await screen.findByRole('list', { name: 'Tus incidencias' });
    expect(within(lista).getByText('Pendiente de gestión')).toBeInTheDocument();
    expect(within(lista).getByText('Resuelta')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Respuesta al aviso #7' })).toHaveTextContent('Pendiente de respuesta.');
    expect(screen.getByRole('region', { name: 'Respuesta al aviso #8' })).toHaveTextContent('Hemos preparado una tapa de repuesto.');
    expect(screen.queryByText(/prioridad|bloqueante|resolución interna|notas internas/i)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Reserva #41' })).toHaveAttribute('href', '/mis-reservas/41');
  });

  it("explica cómo comunicar un problema cuando no hay avisos propios", async () => {
    render(<MemoryRouter><PaginaMisIncidencias /></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: 'No has enviado ningún aviso' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver mis reservas' })).toHaveAttribute('href', '/mis-reservas');
  });

  it("consulta la identidad de la sesión real sin ofrecer edición del perfil ni de permisos", async () => {
    const usuario = { id: 12, name: 'Lucía Demo', email: 'lucia@example.test', role: 'customer' as const, active: true };
    render(<MemoryRouter><ContextoAutenticacion.Provider value={{ sesion: { authenticated: true, username: usuario.email, role: 'customer', user: usuario, expires_at: '2026-12-12T12:00:00Z' }, comprobando: false, errorComprobacion: null, caducado: false, comprobarSesion: vi.fn(), iniciarSesion: vi.fn(), cerrarSesionUsuario: vi.fn() }}><PaginaMiCuenta /></ContextoAutenticacion.Provider></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('Lucía Demo')).toBeInTheDocument());
    expect(screen.getByText('lucia@example.test')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });
});
