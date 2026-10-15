import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ConnectionStatus from './ConnectionStatus';

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

describe('connection screen', () => {
  it('announces the pending request then confirms the backend connection', async () => {
    let resolveRequest!: (response: Response) => void;
    fetchMock.mockImplementation(() => new Promise((resolve) => { resolveRequest = resolve; }));
    render(<ConnectionStatus />);
    expect(screen.getByRole('heading', { name: 'Estado del servidor' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Comprobando conexión');
    expect(screen.getByRole('button', { name: 'Comprobando…' })).toBeDisabled();
    resolveRequest(Response.json({ status: 'ok' }));
    expect(await screen.findByText('Conexión establecida')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Documentación de la API' })).toHaveAttribute('href', '/api/docs');
  });

  it('shows an actionable failure and allows a new check', async () => {
    const user = userEvent.setup();
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    render(<ConnectionStatus />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Comprueba que el backend está en marcha');
    fetchMock.mockResolvedValueOnce(Response.json({ status: 'ok' }));
    await user.click(screen.getByRole('button', { name: 'Volver a comprobar' }));
    expect(await screen.findByText('Conexión establecida')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('does not show a successful connection for an invalid health response', async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ unexpected: true }));
    render(<ConnectionStatus />);
    expect(await screen.findByRole('alert')).toHaveTextContent('El servidor devolvió una respuesta no válida.');
    expect(screen.queryByText('Conexión establecida')).not.toBeInTheDocument();
  });
});
