import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ErrorApi, api } from '../api/cliente';
import type { InformeImportacion } from '../api/cliente';
import PaginaImportaciones from './PaginaImportaciones';

const reserva = { id: 8, equipment_id: 1, customer_name: 'Aurora', customer_email: 'aurora@example.test', start_date: '2026-11-10', end_date: '2026-11-12', status: 'cancelled' as const, external_reference: 'PED-1' };
const informe: InformeImportacion = {
  totals: { total: 3, accepted: 1, already_imported: 1, rejected: 1 },
  rows: [
    { line: 2, external_reference: 'PED-NEW', status: 'accepted', reservation: { ...reserva, id: 9, external_reference: 'PED-NEW', status: 'confirmed' }, message: 'Reserva creada.' },
    { line: 3, external_reference: 'PED-1', status: 'already_imported', reservation: reserva, message: 'La reserva ya estaba importada; se conserva sin cambios.' },
    { line: 4, external_reference: 'PED-2', status: 'rejected', reservation: null, message: 'El equipo tiene una incidencia bloqueante sin resolver.' },
  ],
};

beforeEach(() => vi.restoreAllMocks());

describe("pantalla de importación CSV", () => {
  it("sube el archivo real y muestra todos los resultados del servidor, incluida una reserva existente cancelada", async () => {
    const usuario = userEvent.setup();
    const enviar = vi.spyOn(api, 'importarReservas').mockResolvedValue(informe);
    render(<MemoryRouter><PaginaImportaciones /></MemoryRouter>);
    expect(screen.getByRole('link', { name: /Descargar CSV/ })).toHaveAttribute('href', '/api/imports/example');
    const archivo = new File(['csv contents'], 'pedidos.csv', { type: 'text/csv' });
    await usuario.upload(screen.getByLabelText('Archivo CSV'), archivo);
    await usuario.click(screen.getByRole('button', { name: 'Importar pedidos' }));
    const tabla = await screen.findByRole('table', { name: 'Resultado de la importación' });
    expect(enviar).toHaveBeenCalledWith(archivo);
    expect(within(tabla).getAllByRole('row')).toHaveLength(4);
    expect(within(tabla).getByText('Aceptada')).toBeInTheDocument();
    expect(within(tabla).getByText('Ya importada')).toBeInTheDocument();
    expect(within(tabla).getByText('Rechazada')).toBeInTheDocument();
    expect(within(tabla).getByText('Cancelada')).toBeInTheDocument();
    expect(within(tabla).getByText(/incidencia bloqueante/)).toBeInTheDocument();
    expect(within(tabla).getByRole('link', { name: 'Reserva #8' })).toHaveAttribute('href', '/admin/reservas/8');
    expect(screen.getByRole('status')).toHaveTextContent('3 filas procesadas');
  });

  it("conserva el archivo seleccionado tras un fallo global y permite reintentar correctamente", async () => {
    const usuario = userEvent.setup();
    const enviar = vi.spyOn(api, 'importarReservas').mockRejectedValueOnce(new ErrorApi('La cabecera debe ser exactamente la indicada.', 422)).mockResolvedValueOnce(informe);
    render(<MemoryRouter><PaginaImportaciones /></MemoryRouter>);
    const archivo = new File(['bad header'], 'pedidos.csv', { type: 'text/csv' });
    const entrada = screen.getByLabelText<HTMLInputElement>('Archivo CSV');
    await usuario.upload(entrada, archivo);
    await usuario.click(screen.getByRole('button', { name: 'Importar pedidos' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('La cabecera debe ser exactamente la indicada.');
    expect(entrada.files?.[0]).toBe(archivo);
    await usuario.click(screen.getByRole('button', { name: 'Importar pedidos' }));
    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(enviar).toHaveBeenCalledTimes(2);
  });

  it("evita enviar sin archivo y marca el campo con un error asociado", async () => {
    const usuario = userEvent.setup();
    const enviar = vi.spyOn(api, 'importarReservas');
    render(<MemoryRouter><PaginaImportaciones /></MemoryRouter>);
    await usuario.click(screen.getByRole('button', { name: 'Importar pedidos' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Selecciona un archivo CSV.');
    expect(screen.getByLabelText('Archivo CSV')).toHaveAttribute('aria-invalid', 'true');
    expect(enviar).not.toHaveBeenCalled();
  });
});
