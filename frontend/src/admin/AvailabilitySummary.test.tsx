import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api, type Availability, type Equipment } from '../api/client';
import AvailabilitySummary from './AvailabilitySummary';

const equipment: Equipment[] = [
  { id: 1, code: 'A', name: 'Cámara', category: 'Cámaras', description: '', active: true },
  { id: 2, code: 'B', name: 'Inactivo', category: 'Audio', description: '', active: false },
  { id: 3, code: 'C', name: 'Panel', category: 'Luz', description: '', active: true },
];
const available: Availability = { equipment_id: 1, start_date: '2030-11-10', end_date: '2030-11-12', available: true, reason: null, conflicting_reservation_ids: [] };

beforeEach(() => {
  vi.spyOn(api, 'getEquipmentAvailability').mockImplementation(async (id) => ({ ...available, equipment_id: id, available: id === 1, reason: id === 1 ? null : 'blocking_incident' }));
});

function setDates(end = '2030-11-12') {
  fireEvent.change(screen.getByLabelText('Fecha de inicio'), { target: { value: '2030-11-10' } });
  fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: end } });
}

it('requires both dates before making or claiming an availability check', async () => {
  render(<AvailabilitySummary equipment={equipment} />);
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
  expect(await screen.findByRole('alert')).toHaveFocus();
  expect(api.getEquipmentAvailability).not.toHaveBeenCalled();
});

it('counts service responses for active units and states the exact exclusive range', async () => {
  render(<AvailabilitySummary equipment={equipment} />);
  setDates();
  fireEvent.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
  expect(await screen.findByRole('status')).toHaveTextContent('1 de 2 equipos activos disponibles');
  expect(screen.getByRole('status')).toHaveTextContent('10/11/2030 al 12/11/2030 (fin excluido)');
  expect(api.getEquipmentAvailability).toHaveBeenCalledTimes(2);
  expect(api.getEquipmentAvailability).toHaveBeenCalledWith(1, { start_date: '2030-11-10', end_date: '2030-11-12' });
  expect(api.getEquipmentAvailability).not.toHaveBeenCalledWith(2, expect.anything());
  fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2030-11-13' } });
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

it('discards a response for a range that has been changed', async () => {
  let finish!: (value: Availability) => void;
  vi.mocked(api.getEquipmentAvailability).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  render(<AvailabilitySummary equipment={[equipment[0]!]} />);
  setDates();
  fireEvent.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
  fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2030-11-13' } });
  await act(async () => { finish(available); });
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Consultar disponibilidad' })).toBeEnabled();
});

it('keeps dates after a failed query and permits an explicit retry', async () => {
  vi.mocked(api.getEquipmentAvailability).mockRejectedValueOnce(new Error('Servicio no disponible.'));
  render(<AvailabilitySummary equipment={[equipment[0]!]} />);
  setDates();
  fireEvent.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Servicio no disponible.');
  expect(screen.getByLabelText('Fecha de inicio')).toHaveValue('2030-11-10');
  expect(screen.getByLabelText('Fecha de fin')).toHaveValue('2030-11-12');
  fireEvent.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('1 de 1 equipos activos disponibles'));
});
