import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SituacionConexion from './EstadoConexion';

const peticionSimulada = vi.fn<typeof fetch>();

beforeEach(() => {
  peticionSimulada.mockReset();
  vi.stubGlobal('fetch', peticionSimulada);
});

describe("pantalla de conexión", () => {
  it("anuncia la solicitud pendiente y después confirma la conexión con el servidor", async () => {
    let resolverSolicitud!: (respuesta: Response) => void;
    peticionSimulada.mockImplementation(() => new Promise((resolver) => { resolverSolicitud = resolver; }));
    render(<SituacionConexion />);
    expect(screen.getByRole('heading', { name: 'Estado del servidor' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Comprobando conexión');
    expect(screen.getByRole('button', { name: 'Comprobando…' })).toBeDisabled();
    resolverSolicitud(Response.json({ status: 'ok' }));
    expect(await screen.findByText('Conexión establecida')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Documentación de la API' })).toHaveAttribute('href', '/api/docs');
  });

  it("muestra un fallo con una acción disponible y permite comprobar de nuevo", async () => {
    const usuario = userEvent.setup();
    peticionSimulada.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    render(<SituacionConexion />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Comprueba que el backend está en marcha');
    peticionSimulada.mockResolvedValueOnce(Response.json({ status: 'ok' }));
    await usuario.click(screen.getByRole('button', { name: 'Volver a comprobar' }));
    expect(await screen.findByText('Conexión establecida')).toBeInTheDocument();
    expect(peticionSimulada).toHaveBeenCalledTimes(2);
  });

  it("evita indicar una conexión correcta ante una respuesta de estado no válida", async () => {
    peticionSimulada.mockResolvedValueOnce(Response.json({ inesperado: true }));
    render(<SituacionConexion />);
    expect(await screen.findByRole('alert')).toHaveTextContent('El servidor devolvió una respuesta no válida.');
    expect(screen.queryByText('Conexión establecida')).not.toBeInTheDocument();
  });
});
