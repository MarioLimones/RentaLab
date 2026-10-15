import { act, fireEvent, render, screen } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../api/client';
import { EquipmentFormPage } from './EquipmentFormPage';
import ReservationFormPage from './ReservationFormPage';
import IncidentFormPage from './IncidentFormPage';

const equipment = { id: 1, code: 'CAM-001', name: 'Cámara de prueba', category: 'Cámaras', description: '', active: true };
const saved = {
  ...equipment, id: 8, equipment_id: 1, customer_name: 'Cliente', customer_email: 'cliente@example.test',
  start_date: '2026-11-10', end_date: '2026-11-12', status: 'confirmed' as const, external_reference: null,
};
const incident = {
  id: 8, equipment_id: 1, title: 'Revisar conexión', description: '', priority: 'medium' as const,
  blocking: false, status: 'open' as const, resolution: '', confirmed_reservation_ids: [], warning: null,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function Navigation() {
  const location = useLocation();
  return <><Link to="/admin">Resumen</Link><output aria-label="Pantalla actual">{location.pathname}</output></>;
}

function renderForm(path: string) {
  render(<MemoryRouter initialEntries={[path]}><Navigation /><Routes>
    <Route path="/admin" element={<h1>Resumen de administración</h1>} />
    <Route path="/admin/equipos/nuevo" element={<EquipmentFormPage />} />
    <Route path="/admin/equipos/:id/editar" element={<EquipmentFormPage />} />
    <Route path="/admin/reservas/nueva" element={<ReservationFormPage />} />
    <Route path="/admin/incidencias/nueva" element={<IncidentFormPage />} />
    <Route path="*" element={<h1>Detalle guardado</h1>} />
  </Routes></MemoryRouter>);
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, 'listEquipment').mockResolvedValue([equipment]);
  vi.spyOn(api, 'getEquipment').mockResolvedValue(equipment);
});

describe('leaving an administrative form while saving', () => {
  it.each(['create equipment', 'edit equipment', 'reservation', 'incident'] as const)(
    'keeps the selected destination after a late %s success', async (scenario) => {
      const equipmentRequest = deferred<typeof saved>();
      const incidentRequest = deferred<typeof incident>();
      const request = scenario === 'create equipment'
        ? vi.spyOn(api, 'createEquipment').mockReturnValue(equipmentRequest.promise)
        : scenario === 'edit equipment'
          ? vi.spyOn(api, 'patchEquipment').mockReturnValue(equipmentRequest.promise)
          : scenario === 'reservation'
            ? vi.spyOn(api, 'createReservation').mockReturnValue(equipmentRequest.promise)
            : vi.spyOn(api, 'createIncident').mockReturnValue(incidentRequest.promise);
      renderForm(scenario === 'create equipment' ? '/admin/equipos/nuevo' : scenario === 'edit equipment' ? '/admin/equipos/1/editar' : scenario === 'reservation' ? '/admin/reservas/nueva' : '/admin/incidencias/nueva');
      if (scenario === 'create equipment') {
        fireEvent.change(screen.getByLabelText('Código'), { target: { value: 'CAM-008' } });
        fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Cámara de prueba' } });
        fireEvent.change(screen.getByLabelText('Categoría'), { target: { value: 'Cámaras' } });
      } else if (scenario === 'edit equipment') {
        await screen.findByDisplayValue('CAM-001');
      } else {
        await screen.findByRole('option', { name: /CAM-001/ });
        fireEvent.change(screen.getByLabelText('Equipo'), { target: { value: '1' } });
        if (scenario === 'reservation') {
          fireEvent.change(screen.getByLabelText('Nombre del cliente'), { target: { value: 'Cliente' } });
          fireEvent.change(screen.getByLabelText('Correo del cliente'), { target: { value: 'cliente@example.test' } });
          fireEvent.change(screen.getByLabelText('Fecha de inicio'), { target: { value: '2026-11-10' } });
          fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2026-11-12' } });
        } else {
          fireEvent.change(screen.getByLabelText('Título'), { target: { value: incident.title } });
        }
      }
      fireEvent.click(screen.getByRole('button', { name: scenario === 'create equipment' ? 'Crear equipo' : scenario === 'edit equipment' ? 'Guardar cambios' : scenario === 'reservation' ? 'Crear reserva' : 'Registrar incidencia' }));
      expect(request).toHaveBeenCalledTimes(1);
      fireEvent.click(screen.getByRole('link', { name: 'Resumen' }));
      expect(screen.getByRole('heading', { name: 'Resumen de administración' })).toBeInTheDocument();
      await act(async () => {
        if (scenario === 'incident') incidentRequest.resolve(incident);
        else equipmentRequest.resolve(saved);
      });
      expect(screen.getByLabelText('Pantalla actual')).toHaveTextContent('/admin');
      expect(screen.getByRole('heading', { name: 'Resumen de administración' })).toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: 'Detalle guardado' })).not.toBeInTheDocument();
    },
  );

  it('ignores a late failure after leaving the equipment editor', async () => {
    const request = deferred<typeof saved>();
    vi.spyOn(api, 'patchEquipment').mockReturnValue(request.promise);
    renderForm('/admin/equipos/1/editar');
    await screen.findByDisplayValue('CAM-001');
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
    fireEvent.click(screen.getByRole('link', { name: 'Resumen' }));
    await act(async () => { request.reject(new ApiError('Error tardío de prueba.', 503)); });
    expect(screen.getByRole('heading', { name: 'Resumen de administración' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
