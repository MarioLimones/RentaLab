import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ErrorApi } from '../api/cliente';
import type { ReservaCliente, EquipoPublico } from '../tipos/api';
import PaginaMiReserva from './PaginaMiReserva';

const equipo: EquipoPublico = { id: 3, name: 'Cámara Aurora', category: 'Cámaras', public_description: 'Cámara para vídeo.', technical_specs: {}, image_url: null, image_fallback_url: '/api/public/assets/equipment-placeholder.svg', active_reservations_count: 0 };
const reserva: ReservaCliente = { id: 41, equipment_id: 3, start_date: '2026-11-10', end_date: '2026-11-12', status: 'confirmed' };

function renderizarDetalle(id = '41') {
  return render(<MemoryRouter initialEntries={[`/mis-reservas/${id}`]}><Routes><Route path="/mis-reservas/:id" element={<PaginaMiReserva />} /></Routes></MemoryRouter>);
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-11-01T12:00:00Z'));
  vi.spyOn(api, 'obtenerMiReserva').mockResolvedValue(reserva);
  vi.spyOn(api, 'obtenerEquipoPublico').mockResolvedValue(equipo);
  vi.spyOn(api, 'obtenerDisponibilidadPublica').mockResolvedValue({ equipment_id: 3, start_date: reserva.start_date, end_date: reserva.end_date, available: true, status: 'available' });
  vi.spyOn(api, 'cancelarMiReserva').mockResolvedValue({ ...reserva, status: 'cancelled' });
  vi.spyOn(api, 'crearMiIncidencia').mockResolvedValue({ id: 7, reservation_id: 41, title: 'Conector suelto', description: 'Se pierde la conexión.', status: 'open', public_response: '' });
  vi.spyOn(api, 'obtenerEquipo');
});
afterEach(() => { vi.useRealTimers(); });

describe("detalle de reserva propia", () => {
  it("muestra el nombre compartido del producto de una unidad hermana asignada y conserva la identidad de la reserva", async () => {
    vi.mocked(api.obtenerMiReserva).mockResolvedValue({ ...reserva, equipment_id: 4 });
    renderizarDetalle();
    expect(await screen.findByRole('link', { name: equipo.name })).toHaveAttribute('href', '/equipos/4');
    expect(api.obtenerEquipoPublico).toHaveBeenCalledExactlyOnceWith(4);
    expect(screen.getByRole('heading', { name: 'Reserva #41' })).toBeInTheDocument();
    expect(screen.queryByText(/Equipo #4|unidades/i)).not.toBeInTheDocument();
  });

  it("exige cancelación explícita, gestiona el foco y muestra el estado persistido y la referencia conservada", async () => {
    const usuario = userEvent.setup();
    renderizarDetalle();
    const cancelar = await screen.findByRole('button', { name: 'Cancelar reserva' });
    await usuario.click(cancelar);
    expect(api.cancelarMiReserva).not.toHaveBeenCalled();
    const confirmar = screen.getByRole('button', { name: 'Sí, cancelar reserva' });
    expect(confirmar).toHaveFocus();
    await usuario.click(screen.getByRole('button', { name: 'Conservar reserva' }));
    expect(screen.getByRole('button', { name: 'Cancelar reserva' })).toHaveFocus();
    await usuario.click(screen.getByRole('button', { name: 'Cancelar reserva' }));
    vi.mocked(api.obtenerMiReserva).mockResolvedValue({ ...reserva, status: 'cancelled' });
    await usuario.click(screen.getByRole('button', { name: 'Sí, cancelar reserva' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Reserva cancelada.');
    expect(screen.getByText('Cancelada')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Datos de tu reserva' })).toHaveFocus();
    expect(screen.getByText('#41')).toBeInTheDocument();
    expect(api.cancelarMiReserva).toHaveBeenCalledExactlyOnceWith(41);
    expect(api.obtenerMiReserva).toHaveBeenCalledTimes(2);
    expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledExactlyOnceWith(3, { start_date: reserva.start_date, end_date: reserva.end_date });
    expect(await screen.findByText('Disponibilidad actualizada: el periodo vuelve a estar disponible.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Informar de un problema' })).not.toBeInTheDocument();
  });

  it("utiliza el día del calendario de Madrid para ocultar la cancelación desde el inicio, incluso antes de medianoche UTC", async () => {
    vi.setSystemTime(new Date('2026-11-09T23:30:00Z'));
    renderizarDetalle();
    expect(await screen.findByText(/El plazo de cancelación ha terminado/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancelar reserva' })).not.toBeInTheDocument();
    expect(api.cancelarMiReserva).not.toHaveBeenCalled();
  });

  it("conserva la reserva y anuncia un conflicto de cancelación del servidor sin simular un resultado correcto", async () => {
    vi.mocked(api.cancelarMiReserva).mockRejectedValue(new ErrorApi('Solo puedes cancelar antes del inicio de la reserva.', 409));
    const usuario = userEvent.setup();
    renderizarDetalle();
    await usuario.click(await screen.findByRole('button', { name: 'Cancelar reserva' }));
    await usuario.click(screen.getByRole('button', { name: 'Sí, cancelar reserva' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Solo puedes cancelar antes del inicio');
    expect(screen.getByRole('alert')).toHaveFocus();
    expect(screen.getByText('Confirmada')).toBeInTheDocument();
    expect(screen.getByText('10/11/2026')).toBeInTheDocument();
    expect(screen.queryByText(/Reserva cancelada\./)).not.toBeInTheDocument();
  });

  it("muestra 404 para un identificador propio no disponible sin consultar administración", async () => {
    vi.mocked(api.obtenerMiReserva).mockRejectedValue(new ErrorApi('Reserva no encontrada.', 404));
    renderizarDetalle('992');
    expect(await screen.findByRole('alert')).toHaveTextContent('Reserva no encontrada.');
    expect(api.obtenerMiReserva).toHaveBeenCalledWith(992);
    expect(api.obtenerEquipo).not.toHaveBeenCalled();
    expect(api.obtenerEquipoPublico).not.toHaveBeenCalled();
  });

  it("conserva una reserva histórica si se ha desactivado su equipo", async () => {
    vi.mocked(api.obtenerEquipoPublico).mockRejectedValue(new ErrorApi('Equipo no encontrado.', 404));
    renderizarDetalle();
    expect(await screen.findByRole('heading', { name: 'Equipo #3 (ficha no disponible)' })).toBeInTheDocument();
    expect(screen.getByText('10/11/2026')).toBeInTheDocument();
    expect(api.obtenerEquipo).not.toHaveBeenCalled();
  });

  it("valida el formulario de problemas, conserva un envío fallido y envía solo título y descripción", async () => {
    vi.mocked(api.crearMiIncidencia).mockRejectedValueOnce(new ErrorApi('Revisa los campos indicados.', 422, { description: 'Añade más detalle.' }));
    const usuario = userEvent.setup();
    renderizarDetalle();
    await usuario.click(await screen.findByRole('button', { name: 'Informar de un problema' }));
    expect(screen.getByLabelText('Título del problema')).toHaveFocus();
    await usuario.click(screen.getByRole('button', { name: 'Enviar aviso' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Escribe un título');
    expect(api.crearMiIncidencia).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Título del problema'), { target: { value: 'Conector suelto' } });
    fireEvent.change(screen.getByLabelText('Descripción del problema'), { target: { value: 'Se pierde la conexión.' } });
    await usuario.click(screen.getByRole('button', { name: 'Enviar aviso' }));
    expect(await screen.findByText('Añade más detalle.')).toBeInTheDocument();
    expect(screen.getByLabelText('Descripción del problema')).toHaveValue('Se pierde la conexión.');
    expect(screen.getByLabelText('Descripción del problema')).toHaveAttribute('aria-invalid', 'true');
    expect(api.crearMiIncidencia).toHaveBeenLastCalledWith(41, { title: 'Conector suelto', description: 'Se pierde la conexión.' });
    await usuario.click(screen.getByRole('button', { name: 'Enviar aviso' }));
    expect(await screen.findByRole('link', { name: 'Consultar mis incidencias' })).toHaveAttribute('href', '/mis-incidencias');
    expect(screen.queryByLabelText('Descripción del problema')).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it("mantiene el formulario de avisos no disponible para una reserva cancelada", async () => {
    vi.mocked(api.obtenerMiReserva).mockResolvedValue({ ...reserva, status: 'cancelled' });
    renderizarDetalle();
    await waitFor(() => expect(screen.getByText('Cancelada')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Informar de un problema' })).not.toBeInTheDocument();
  });

  it("impide cancelar dos veces mientras el servidor procesa y espera la respuesta persistida", async () => {
    let finalizar!: (valor: ReservaCliente) => void;
    vi.mocked(api.cancelarMiReserva).mockImplementation(() => new Promise((resolver) => { finalizar = resolver; }));
    const usuario = userEvent.setup();
    renderizarDetalle();
    await usuario.click(await screen.findByRole('button', { name: 'Cancelar reserva' }));
    await usuario.dblClick(screen.getByRole('button', { name: 'Sí, cancelar reserva' }));
    expect(api.cancelarMiReserva).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Cancelando…' })).toBeDisabled();
    expect(screen.queryByText('Cancelada')).not.toBeInTheDocument();
    await act(async () => { finalizar({ ...reserva, status: 'cancelled' }); });
    expect(await screen.findByText('Cancelada')).toBeInTheDocument();
    expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledTimes(1);
  });

  it("conserva una cancelación guardada como correcta aunque falle actualizar la disponibilidad pública", async () => {
    vi.mocked(api.obtenerDisponibilidadPublica).mockRejectedValue(new ErrorApi('Sin conexión.', 0));
    const usuario = userEvent.setup();
    renderizarDetalle();
    await usuario.click(await screen.findByRole('button', { name: 'Cancelar reserva' }));
    await usuario.click(screen.getByRole('button', { name: 'Sí, cancelar reserva' }));
    expect(await screen.findByText('La cancelación se ha guardado. No se pudo actualizar la disponibilidad; vuelve a la ficha del equipo para consultarla.')).toBeInTheDocument();
    expect(screen.getByText('Cancelada')).toBeInTheDocument();
    expect(api.cancelarMiReserva).toHaveBeenCalledTimes(1);
  });
});
