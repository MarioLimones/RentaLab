import { act, fireEvent, render, screen } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ErrorApi } from '../api/cliente';
import { PaginaFormularioEquipo } from './PaginaFormularioEquipo';
import PaginaFormularioReserva from './PaginaFormularioReserva';
import PaginaFormularioIncidencia from './PaginaFormularioIncidencia';

const equipo = { id: 1, code: 'CAM-001', name: 'Cámara de prueba', category: 'Cámaras', description: '', active: true };
const guardado = {
  ...equipo, id: 8, equipment_id: 1, customer_name: 'Cliente', customer_email: 'cliente@example.test',
  start_date: '2026-11-10', end_date: '2026-11-12', status: 'confirmed' as const, external_reference: null,
};
const incidencia = {
  id: 8, equipment_id: 1, title: 'Revisar conexión', description: '', priority: 'medium' as const,
  blocking: false, status: 'open' as const, resolution: '', confirmed_reservation_ids: [], warning: null,
};

function diferido<T>() {
  let resolver!: (valor: T) => void;
  let rechazar!: (error: Error) => void;
  const promesa = new Promise<T>((si, no) => { resolver = si; rechazar = no; });
  return { promise: promesa, resolve: resolver, reject: rechazar };
}

function Navegacion() {
  const ubicacion = useLocation();
  return <><Link to="/admin">Resumen</Link><output aria-label="Pantalla actual">{ubicacion.pathname}</output></>;
}

function renderizarFormulario(ruta: string) {
  render(<MemoryRouter initialEntries={[ruta]}><Navegacion /><Routes>
    <Route path="/admin" element={<h1>Resumen de administración</h1>} />
    <Route path="/admin/equipos/nuevo" element={<PaginaFormularioEquipo />} />
    <Route path="/admin/equipos/:id/editar" element={<PaginaFormularioEquipo />} />
    <Route path="/admin/reservas/nueva" element={<PaginaFormularioReserva />} />
    <Route path="/admin/incidencias/nueva" element={<PaginaFormularioIncidencia />} />
    <Route path="*" element={<h1>Detalle guardado</h1>} />
  </Routes></MemoryRouter>);
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, 'listarEquipos').mockResolvedValue([equipo]);
  vi.spyOn(api, 'obtenerEquipo').mockResolvedValue(equipo);
});

describe("salida de un formulario administrativo mientras se guarda", () => {
  it.each(['create equipment', 'edit equipment', 'reservation', 'incident'] as const)(
    "conserva el destino seleccionado tras un guardado de %s que termina tarde", async (escenario) => {
      const solicitudEquipos = diferido<typeof guardado>();
      const solicitudIncidencia = diferido<typeof incidencia>();
      const solicitud = escenario === 'create equipment'
        ? vi.spyOn(api, 'crearEquipo').mockReturnValue(solicitudEquipos.promise)
        : escenario === 'edit equipment'
          ? vi.spyOn(api, 'modificarEquipo').mockReturnValue(solicitudEquipos.promise)
          : escenario === 'reservation'
            ? vi.spyOn(api, 'crearReserva').mockReturnValue(solicitudEquipos.promise)
            : vi.spyOn(api, 'crearIncidencia').mockReturnValue(solicitudIncidencia.promise);
      renderizarFormulario(escenario === 'create equipment' ? '/admin/equipos/nuevo' : escenario === 'edit equipment' ? '/admin/equipos/1/editar' : escenario === 'reservation' ? '/admin/reservas/nueva' : '/admin/incidencias/nueva');
      if (escenario === 'create equipment') {
        fireEvent.change(screen.getByLabelText('Código'), { target: { value: 'CAM-008' } });
        fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Cámara de prueba' } });
        fireEvent.change(screen.getByLabelText('Categoría'), { target: { value: 'Cámaras' } });
      } else if (escenario === 'edit equipment') {
        await screen.findByDisplayValue('CAM-001');
      } else {
        await screen.findByRole('option', { name: /CAM-001/ });
        fireEvent.change(screen.getByLabelText('Equipo'), { target: { value: '1' } });
        if (escenario === 'reservation') {
          fireEvent.change(screen.getByLabelText('Nombre del cliente'), { target: { value: 'Cliente' } });
          fireEvent.change(screen.getByLabelText('Correo del cliente'), { target: { value: 'cliente@example.test' } });
          fireEvent.change(screen.getByLabelText('Fecha de inicio'), { target: { value: '2026-11-10' } });
          fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2026-11-12' } });
        } else {
          fireEvent.change(screen.getByLabelText('Título'), { target: { value: incidencia.title } });
        }
      }
      fireEvent.click(screen.getByRole('button', { name: escenario === 'create equipment' ? 'Crear equipo' : escenario === 'edit equipment' ? 'Guardar cambios' : escenario === 'reservation' ? 'Crear reserva' : 'Registrar incidencia' }));
      expect(solicitud).toHaveBeenCalledTimes(1);
      fireEvent.click(screen.getByRole('link', { name: 'Resumen' }));
      expect(screen.getByRole('heading', { name: 'Resumen de administración' })).toBeInTheDocument();
      await act(async () => {
        if (escenario === 'incident') solicitudIncidencia.resolve(incidencia);
        else solicitudEquipos.resolve(guardado);
      });
      expect(screen.getByLabelText('Pantalla actual')).toHaveTextContent('/admin');
      expect(screen.getByRole('heading', { name: 'Resumen de administración' })).toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: 'Detalle guardado' })).not.toBeInTheDocument();
    },
  );

  it("ignora un fallo tardío después de salir del editor de equipos", async () => {
    const solicitud = diferido<typeof guardado>();
    vi.spyOn(api, 'modificarEquipo').mockReturnValue(solicitud.promise);
    renderizarFormulario('/admin/equipos/1/editar');
    await screen.findByDisplayValue('CAM-001');
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
    fireEvent.click(screen.getByRole('link', { name: 'Resumen' }));
    await act(async () => { solicitud.reject(new ErrorApi('Error tardío de prueba.', 503)); });
    expect(screen.getByRole('heading', { name: 'Resumen de administración' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
