import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api, type Disponibilidad, type Equipo } from '../api/cliente';
import ResumenDisponibilidad from './ResumenDisponibilidad';

const equipo: Equipo[] = [
  { id: 1, code: 'A', name: 'Cámara', category: 'Cámaras', description: '', active: true },
  { id: 2, code: 'B', name: 'Inactivo', category: 'Audio', description: '', active: false },
  { id: 3, code: 'C', name: 'Panel', category: 'Luz', description: '', active: true },
];
const disponible: Disponibilidad = { equipment_id: 1, start_date: '2030-11-10', end_date: '2030-11-12', available: true, reason: null, conflicting_reservation_ids: [] };

beforeEach(() => {
  vi.spyOn(api, 'obtenerDisponibilidadEquipo').mockImplementation(async (id) => ({ ...disponible, equipment_id: id, available: id === 1, reason: id === 1 ? null : 'blocking_incident' }));
});

function establecerFechas(fin = '2030-11-12') {
  fireEvent.change(screen.getByLabelText('Fecha de inicio'), { target: { value: '2030-11-10' } });
  fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: fin } });
}

it("exige ambas fechas antes de consultar o afirmar la disponibilidad", async () => {
  render(<ResumenDisponibilidad equipo={equipo} />);
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
  expect(await screen.findByRole('alert')).toHaveFocus();
  expect(api.obtenerDisponibilidadEquipo).not.toHaveBeenCalled();
});

it("cuenta las respuestas del servicio para las unidades activas e indica el intervalo exclusivo exacto", async () => {
  render(<ResumenDisponibilidad equipo={equipo} />);
  establecerFechas();
  fireEvent.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
  expect(await screen.findByRole('status')).toHaveTextContent('1 de 2 equipos activos disponibles');
  expect(screen.getByRole('status')).toHaveTextContent('10/11/2030 al 12/11/2030 (fin excluido)');
  expect(api.obtenerDisponibilidadEquipo).toHaveBeenCalledTimes(2);
  expect(api.obtenerDisponibilidadEquipo).toHaveBeenCalledWith(1, { start_date: '2030-11-10', end_date: '2030-11-12' });
  expect(api.obtenerDisponibilidadEquipo).not.toHaveBeenCalledWith(2, expect.anything());
  fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2030-11-13' } });
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

it("descarta la respuesta de un intervalo que ha cambiado", async () => {
  let finalizar!: (valor: Disponibilidad) => void;
  vi.mocked(api.obtenerDisponibilidadEquipo).mockImplementation(() => new Promise((resolver) => { finalizar = resolver; }));
  render(<ResumenDisponibilidad equipo={[equipo[0]!]} />);
  establecerFechas();
  fireEvent.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
  fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2030-11-13' } });
  await act(async () => { finalizar(disponible); });
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Consultar disponibilidad' })).toBeEnabled();
});

it("conserva las fechas tras una consulta fallida y permite reintentar expresamente", async () => {
  vi.mocked(api.obtenerDisponibilidadEquipo).mockRejectedValueOnce(new Error('Servicio no disponible.'));
  render(<ResumenDisponibilidad equipo={[equipo[0]!]} />);
  establecerFechas();
  fireEvent.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Servicio no disponible.');
  expect(screen.getByLabelText('Fecha de inicio')).toHaveValue('2030-11-10');
  expect(screen.getByLabelText('Fecha de fin')).toHaveValue('2030-11-12');
  fireEvent.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('1 de 1 equipos activos disponibles'));
});
