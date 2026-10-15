import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, type Incident } from '../api/client';
import IncidentsPage from './IncidentsPage';
import IncidentFormPage from './IncidentFormPage';
import IncidentDetailPage from './IncidentDetailPage';

const equipment = { id: 1, code: 'CAM-001', name: 'Cámara Aurora', category: 'Cámaras', description: '', active: true };
const incident: Incident = {
  id: 4, equipment_id: 1, title: 'Conector dañado', description: 'La señal se interrumpe.',
  priority: 'high', blocking: true, status: 'open', resolution: '',
  reservation_id: null, author_user_id: null, internal_notes: '', public_response: '',
  confirmed_reservation_ids: [12], warning: 'El equipo tiene reservas confirmadas. La incidencia no las cancela ni las modifica.',
};

function renderPage(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/admin/incidencias" element={<IncidentsPage />} />
    <Route path="/admin/incidencias/nueva" element={<IncidentFormPage />} />
    <Route path="/admin/incidencias/:id" element={<IncidentDetailPage />} />
  </Routes></MemoryRouter>);
}

beforeEach(() => {
  vi.spyOn(api, 'listEquipment').mockResolvedValue([equipment]);
  vi.spyOn(api, 'listIncidents').mockResolvedValue([incident]);
  vi.spyOn(api, 'getIncident').mockResolvedValue(incident);
});

afterEach(() => vi.restoreAllMocks());

describe('incident pages', () => {
  it('filters server results and sends blocking=false rather than omitting it', async () => {
    const user = userEvent.setup();
    renderPage('/admin/incidencias');
    expect(await screen.findByRole('link', { name: 'Conector dañado' })).toHaveAttribute('href', '/admin/incidencias/4');
    await user.selectOptions(screen.getByLabelText('Equipo'), '1');
    await user.selectOptions(screen.getByLabelText('Estado'), 'in_progress');
    await user.selectOptions(screen.getByLabelText('Prioridad'), 'low');
    await user.selectOptions(screen.getByLabelText('Bloqueo'), 'false');
    await user.click(screen.getByRole('button', { name: 'Aplicar filtros' }));
    await waitFor(() => expect(api.listIncidents).toHaveBeenLastCalledWith({
      equipment_id: 1, status: 'in_progress', priority: 'low', blocking: false,
    }));
  });

  it('creates a blocking incident for the preselected equipment and shows its confirmed reservations', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'createIncident').mockResolvedValue(incident);
    renderPage('/admin/incidencias/nueva?equipment_id=1');
    await screen.findByRole('option', { name: 'CAM-001 · Cámara Aurora' });
    expect(screen.getByLabelText('Equipo')).toHaveValue('1');
    await user.type(screen.getByLabelText('Título'), incident.title);
    await user.type(screen.getByLabelText('Descripción'), incident.description);
    await user.selectOptions(screen.getByLabelText('Prioridad'), 'high');
    await user.click(screen.getByLabelText('Bloquea nuevas reservas'));
    await user.click(screen.getByRole('button', { name: 'Registrar incidencia' }));
    expect(api.createIncident).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Sí, registrar y bloquear' })).toHaveFocus();
    await user.click(screen.getByRole('button', { name: 'Sí, registrar y bloquear' }));
    await waitFor(() => expect(api.createIncident).toHaveBeenCalledWith({
      equipment_id: 1, title: incident.title, description: incident.description, priority: 'high', blocking: true,
    }));
    expect(await screen.findByRole('heading', { name: 'Conector dañado' })).toBeInTheDocument();
    expect(screen.getByText(incident.warning ?? '')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Reserva #12' })).toHaveAttribute('href', '/admin/reservas/12');
  });

  it('keeps creation values when the server rejects the request and allows correction', async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(api, 'createIncident').mockRejectedValueOnce(new ApiError('El equipo ya no existe.', 404));
    renderPage('/admin/incidencias/nueva?equipment_id=1');
    await screen.findByRole('option', { name: 'CAM-001 · Cámara Aurora' });
    await user.type(screen.getByLabelText('Título'), 'Revisar conexión');
    await user.type(screen.getByLabelText('Descripción'), 'Fallo intermitente.');
    await user.click(screen.getByRole('button', { name: 'Registrar incidencia' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('El equipo ya no existe.');
    expect(screen.getByLabelText('Título')).toHaveValue('Revisar conexión');
    expect(screen.getByLabelText('Descripción')).toHaveValue('Fallo intermitente.');
    create.mockResolvedValueOnce(incident);
    await user.click(screen.getByRole('button', { name: 'Registrar incidencia' }));
    expect(await screen.findByRole('heading', { name: 'Conector dañado' })).toBeInTheDocument();
  });

  it('requires a resolution, retains it after conflict and presents the persisted resolution on retry', async () => {
    const user = userEvent.setup();
    const resolved = { ...incident, status: 'resolved' as const, resolution: 'Conector sustituido.' };
    const change = vi.spyOn(api, 'changeIncidentStatus')
      .mockRejectedValueOnce(new ApiError('La incidencia cambió. Comprueba su estado.', 409))
      .mockResolvedValueOnce(resolved);
    vi.mocked(api.getIncident).mockResolvedValueOnce(incident).mockResolvedValue(resolved);
    renderPage('/admin/incidencias/4');
    await screen.findByRole('heading', { name: incident.title });
    await user.type(screen.getByLabelText('Resolución'), '   ');
    await user.click(screen.getByRole('button', { name: 'Resolver incidencia' }));
    expect(change).not.toHaveBeenCalled();
    expect(await screen.findByRole('alert')).toHaveTextContent('Explica cómo se ha resuelto la incidencia.');
    expect(screen.getByLabelText('Resolución')).toHaveAttribute('aria-invalid', 'true');
    await user.clear(screen.getByLabelText('Resolución'));
    await user.type(screen.getByLabelText('Resolución'), 'Conector sustituido.');
    await user.click(screen.getByRole('button', { name: 'Resolver incidencia' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('La incidencia cambió. Comprueba su estado.');
    expect(screen.getByLabelText('Resolución')).toHaveValue('Conector sustituido.');
    await user.click(screen.getByRole('button', { name: 'Resolver incidencia' }));
    await waitFor(() => expect(change).toHaveBeenLastCalledWith(4, { status: 'resolved', resolution: 'Conector sustituido.' }));
    expect(await screen.findByText('Conector sustituido.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resolver incidencia' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Iniciar trabajo' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Datos de la incidencia' })).toHaveFocus();
  });

  it('starts work through the API and offers only resolution after the persisted transition', async () => {
    const user = userEvent.setup();
    const inProgress = { ...incident, status: 'in_progress' as const };
    const change = vi.spyOn(api, 'changeIncidentStatus').mockResolvedValue(inProgress);
    vi.mocked(api.getIncident).mockResolvedValueOnce(incident).mockResolvedValue(inProgress);
    renderPage('/admin/incidencias/4');
    await user.click(await screen.findByRole('button', { name: 'Iniciar trabajo' }));
    await waitFor(() => expect(change).toHaveBeenCalledWith(4, { status: 'in_progress' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Iniciar trabajo' })).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Resolver incidencia' })).toBeInTheDocument();
    expect(screen.getByLabelText('Resolución')).toHaveFocus();
  });

  it('does not expose the previous incident when another id fails to load in the same route', async () => {
    const user = userEvent.setup();
    const change = vi.spyOn(api, 'changeIncidentStatus');
    vi.mocked(api.getIncident).mockResolvedValueOnce(incident).mockRejectedValue(new ApiError('La incidencia no existe.', 404));
    render(<MemoryRouter initialEntries={['/admin/incidencias/4']}>
      <Link to="/admin/incidencias/999">Ir a otra incidencia</Link>
      <Routes><Route path="/admin/incidencias/:id" element={<IncidentDetailPage />} /></Routes>
    </MemoryRouter>);
    await screen.findByRole('heading', { name: incident.title });
    await user.type(screen.getByLabelText('Resolución'), 'Borrador del equipo anterior');
    await user.click(screen.getByRole('link', { name: 'Ir a otra incidencia' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('La incidencia no existe.');
    expect(screen.queryByRole('heading', { name: incident.title })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Iniciar trabajo' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resolver incidencia' })).not.toBeInTheDocument();
    expect(change).not.toHaveBeenCalled();
  });

  it('shows the persisted PATCH result even when the follow-up GET fails', async () => {
    const user = userEvent.setup();
    const resolved = { ...incident, status: 'resolved' as const, resolution: 'Conector sustituido.' };
    vi.spyOn(api, 'changeIncidentStatus').mockResolvedValue(resolved);
    vi.mocked(api.getIncident).mockResolvedValueOnce(incident).mockRejectedValue(new ApiError('No se pudo actualizar la consulta.', 0));
    renderPage('/admin/incidencias/4');
    await screen.findByRole('heading', { name: incident.title });
    await user.type(screen.getByLabelText('Resolución'), resolved.resolution);
    await user.click(screen.getByRole('button', { name: 'Resolver incidencia' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo actualizar la consulta.');
    expect(screen.queryByRole('button', { name: 'Resolver incidencia' })).not.toBeInTheDocument();
    expect(screen.getByText(resolved.resolution)).toBeInTheDocument();
    expect(screen.getByText('Resuelta')).toBeInTheDocument();
  });

  it('identifies customer reports by their reservation and keeps historical authorless incidents visible', async () => {
    const report = { ...incident, id: 5, title: 'Aviso desde el portal', reservation_id: 23, author_user_id: 8, blocking: false };
    vi.mocked(api.listIncidents).mockResolvedValue([incident, report]);
    renderPage('/admin/incidencias');
    const customerRow = (await screen.findByRole('link', { name: report.title })).closest('tr')!;
    expect(within(customerRow).getByText('Aviso de cliente')).toBeInTheDocument();
    expect(within(customerRow).getByRole('link', { name: 'Reserva #23' })).toHaveAttribute('href', '/admin/reservas/23');
    expect(within(customerRow).getByText('Usuario #8')).toBeInTheDocument();
    const historicalRow = screen.getByRole('link', { name: incident.title }).closest('tr')!;
    expect(within(historicalRow).getByText('Interna o histórica sin reserva vinculada')).toBeInTheDocument();
    expect(within(historicalRow).getByText('Sin autor de cuenta registrado')).toBeInTheDocument();
  });

  it('saves priority, internal notes and a separate customer reply without resolving the incident', async () => {
    const user = userEvent.setup();
    const saved = { ...incident, priority: 'low' as const, internal_notes: 'Diagnóstico para el taller.', public_response: 'Estamos revisando tu aviso.' };
    const patch = vi.spyOn(api, 'patchIncident').mockResolvedValue(saved);
    const changeStatus = vi.spyOn(api, 'changeIncidentStatus');
    vi.mocked(api.getIncident).mockResolvedValueOnce(incident).mockResolvedValue(saved);
    renderPage('/admin/incidencias/4');
    await screen.findByRole('heading', { name: incident.title });
    await user.selectOptions(screen.getByLabelText('Prioridad'), 'low');
    await user.type(screen.getByLabelText('Notas internas'), saved.internal_notes);
    await user.type(screen.getByLabelText('Respuesta visible al cliente'), saved.public_response);
    await user.type(screen.getByLabelText('Resolución'), 'Borrador de resolución interna.');
    await user.click(screen.getByRole('button', { name: 'Guardar gestión' }));
    await waitFor(() => expect(patch).toHaveBeenCalledWith(4, {
      priority: 'low', blocking: true, internal_notes: saved.internal_notes, public_response: saved.public_response,
    }));
    expect(changeStatus).not.toHaveBeenCalled();
    expect(await screen.findByText('Gestión de la incidencia guardada.')).toBeInTheDocument();
    expect(screen.getByLabelText('Notas internas')).toHaveValue(saved.internal_notes);
    expect(screen.getByLabelText('Respuesta visible al cliente')).toHaveValue(saved.public_response);
    expect(screen.getByLabelText('Resolución')).toHaveValue('Borrador de resolución interna.');
    expect(screen.getByRole('heading', { name: 'Datos de la incidencia' })).toHaveFocus();
  });

  it('requires confirmation before blocking a customer report and keeps values on conflict for an explicit retry', async () => {
    const user = userEvent.setup();
    const report = { ...incident, reservation_id: 23, author_user_id: 8, blocking: false };
    const saved = { ...report, blocking: true, priority: 'high' as const, public_response: 'Revisaremos la conexión.', internal_notes: 'No publicar el diagnóstico.' };
    vi.mocked(api.getIncident).mockResolvedValueOnce(report).mockResolvedValue(saved);
    const patch = vi.spyOn(api, 'patchIncident').mockRejectedValueOnce(new ApiError('No se pudo guardar. Inténtalo de nuevo.', 409)).mockResolvedValueOnce(saved);
    renderPage('/admin/incidencias/4');
    await screen.findByRole('heading', { name: report.title });
    expect(screen.getByText('Aviso de cliente')).toBeInTheDocument();
    expect(screen.getByText('Usuario #8')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Notas internas'), saved.internal_notes);
    await user.type(screen.getByLabelText('Respuesta visible al cliente'), saved.public_response);
    await user.click(screen.getByLabelText('Bloquea nuevas reservas'));
    await user.click(screen.getByRole('button', { name: 'Guardar gestión' }));
    expect(patch).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Sí, guardar y bloquear' })).toHaveFocus();
    expect(screen.getByRole('group', { name: 'Confirmar bloqueo del equipo' })).toHaveTextContent('no se cancelan automáticamente');
    await user.click(screen.getByRole('button', { name: 'Volver a editar' }));
    expect(screen.getByRole('button', { name: 'Guardar gestión' })).toHaveFocus();
    expect(patch).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Guardar gestión' }));
    await user.click(screen.getByRole('button', { name: 'Sí, guardar y bloquear' }));
    const error = await screen.findByRole('alert');
    expect(error).toHaveTextContent('No se pudo guardar. Inténtalo de nuevo.');
    expect(error).toHaveFocus();
    expect(screen.getByLabelText('Notas internas')).toHaveValue(saved.internal_notes);
    expect(screen.getByLabelText('Respuesta visible al cliente')).toHaveValue(saved.public_response);
    await user.click(screen.getByRole('button', { name: 'Sí, guardar y bloquear' }));
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Impide nuevas reservas de este equipo.')).toBeInTheDocument();
  });

  it('retains the management response after a failed refresh and leaves internal resolution private and unchanged', async () => {
    const user = userEvent.setup();
    const resolved = { ...incident, status: 'resolved' as const, resolution: 'Trabajo técnico interno.', internal_notes: 'Nota anterior.', public_response: 'Aviso recibido.' };
    const saved = { ...resolved, priority: 'low' as const, internal_notes: 'Nota nueva.', public_response: 'El equipo está revisado.' };
    vi.mocked(api.getIncident).mockResolvedValueOnce(resolved).mockRejectedValue(new ApiError('No se pudo recargar la incidencia.', 0));
    vi.spyOn(api, 'patchIncident').mockResolvedValue(saved);
    const changeStatus = vi.spyOn(api, 'changeIncidentStatus');
    renderPage('/admin/incidencias/4');
    await screen.findByRole('heading', { name: resolved.title });
    await user.selectOptions(screen.getByLabelText('Prioridad'), 'low');
    await user.clear(screen.getByLabelText('Notas internas'));
    await user.type(screen.getByLabelText('Notas internas'), saved.internal_notes);
    await user.clear(screen.getByLabelText('Respuesta visible al cliente'));
    await user.type(screen.getByLabelText('Respuesta visible al cliente'), saved.public_response);
    await user.click(screen.getByRole('button', { name: 'Guardar gestión' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo recargar la incidencia.');
    expect(screen.getByLabelText('Prioridad')).toHaveValue('low');
    expect(screen.getByLabelText('Notas internas')).toHaveValue(saved.internal_notes);
    expect(screen.getByLabelText('Respuesta visible al cliente')).toHaveValue(saved.public_response);
    expect(screen.getByText(resolved.resolution)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resolver incidencia' })).not.toBeInTheDocument();
    expect(changeStatus).not.toHaveBeenCalled();
  });

  it('refreshes the administrative list after an external status change', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listIncidents).mockResolvedValueOnce([incident]).mockResolvedValue([{ ...incident, status: 'in_progress' }]);
    renderPage('/admin/incidencias');
    await screen.findByRole('link', { name: incident.title });
    expect(within(screen.getByRole('table')).getByText('Abierta')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Actualizar listado' }));
    expect(within(await screen.findByRole('table')).getByText('En curso')).toBeInTheDocument();
    expect(api.listIncidents).toHaveBeenCalledTimes(2);
  });

  it('shows field errors without losing management drafts or copying private notes to the customer response', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'patchIncident').mockRejectedValue(new ApiError('Contenido inválido.', 422, { public_response: 'Revisa el texto de respuesta.' }));
    renderPage('/admin/incidencias/4');
    await screen.findByRole('heading', { name: incident.title });
    await user.type(screen.getByLabelText('Notas internas'), 'Diagnóstico reservado.');
    await user.type(screen.getByLabelText('Respuesta visible al cliente'), 'Respuesta por revisar.');
    await user.click(screen.getByRole('button', { name: 'Guardar gestión' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Revisa los campos indicados.');
    expect(screen.getByLabelText('Respuesta visible al cliente')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Respuesta visible al cliente')).toHaveValue('Respuesta por revisar.');
    expect(screen.getByLabelText('Notas internas')).toHaveValue('Diagnóstico reservado.');
    expect(screen.getByLabelText('Resolución')).toHaveValue('');
  });

  it('hides the previous results when a new filter fails, without claiming they match the selected status', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listIncidents).mockResolvedValueOnce([incident]).mockRejectedValueOnce(new ApiError('No se pudieron consultar las incidencias resueltas.', 503));
    renderPage('/admin/incidencias');
    await screen.findByRole('link', { name: incident.title });
    await user.selectOptions(screen.getByLabelText('Estado'), 'resolved');
    await user.click(screen.getByRole('button', { name: 'Aplicar filtros' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudieron consultar las incidencias resueltas.');
    expect(screen.getByLabelText('Estado')).toHaveValue('resolved');
    expect(screen.queryByRole('link', { name: incident.title })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Listado de incidencias' })).not.toBeInTheDocument();
    expect(api.listIncidents).toHaveBeenLastCalledWith({ status: 'resolved' });
  });
});
