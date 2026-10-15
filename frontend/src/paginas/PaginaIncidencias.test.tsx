import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ErrorApi, type Incidencia } from '../api/cliente';
import PaginaIncidencias from './PaginaIncidencias';
import PaginaFormularioIncidencia from './PaginaFormularioIncidencia';
import PaginaDetalleIncidencia from './PaginaDetalleIncidencia';

const equipo = { id: 1, code: 'CAM-001', name: 'Cámara Aurora', category: 'Cámaras', description: '', active: true };
const incidencia: Incidencia = {
  id: 4, equipment_id: 1, title: 'Conector dañado', description: 'La señal se interrumpe.',
  priority: 'high', blocking: true, status: 'open', resolution: '',
  reservation_id: null, author_user_id: null, internal_notes: '', public_response: '',
  confirmed_reservation_ids: [12], warning: 'El equipo tiene reservas confirmadas. La incidencia no las cancela ni las modifica.',
};

function renderizarPagina(ruta: string) {
  return render(<MemoryRouter initialEntries={[ruta]}><Routes>
    <Route path="/admin/incidencias" element={<PaginaIncidencias />} />
    <Route path="/admin/incidencias/nueva" element={<PaginaFormularioIncidencia />} />
    <Route path="/admin/incidencias/:id" element={<PaginaDetalleIncidencia />} />
  </Routes></MemoryRouter>);
}

beforeEach(() => {
  vi.spyOn(api, 'listarEquipos').mockResolvedValue([equipo]);
  vi.spyOn(api, 'listarIncidencias').mockResolvedValue([incidencia]);
  vi.spyOn(api, 'obtenerIncidencia').mockResolvedValue(incidencia);
});

afterEach(() => vi.restoreAllMocks());

describe("páginas de incidencias", () => {
  it("filtra los resultados del servidor y envía blocking=false sin omitirlo", async () => {
    const usuario = userEvent.setup();
    renderizarPagina('/admin/incidencias');
    expect(await screen.findByRole('link', { name: 'Conector dañado' })).toHaveAttribute('href', '/admin/incidencias/4');
    await usuario.selectOptions(screen.getByLabelText('Equipo'), '1');
    await usuario.selectOptions(screen.getByLabelText('Estado'), 'in_progress');
    await usuario.selectOptions(screen.getByLabelText('Prioridad'), 'low');
    await usuario.selectOptions(screen.getByLabelText('Bloqueo'), 'false');
    await usuario.click(screen.getByRole('button', { name: 'Aplicar filtros' }));
    await waitFor(() => expect(api.listarIncidencias).toHaveBeenLastCalledWith({
      equipment_id: 1, status: 'in_progress', priority: 'low', blocking: false,
    }));
  });

  it("crea una incidencia bloqueante para el equipo preseleccionado y muestra sus reservas confirmadas", async () => {
    const usuario = userEvent.setup();
    vi.spyOn(api, 'crearIncidencia').mockResolvedValue(incidencia);
    renderizarPagina('/admin/incidencias/nueva?equipment_id=1');
    await screen.findByRole('option', { name: 'CAM-001 · Cámara Aurora' });
    expect(screen.getByLabelText('Equipo')).toHaveValue('1');
    await usuario.type(screen.getByLabelText('Título'), incidencia.title);
    await usuario.type(screen.getByLabelText('Descripción'), incidencia.description);
    await usuario.selectOptions(screen.getByLabelText('Prioridad'), 'high');
    await usuario.click(screen.getByLabelText('Bloquea nuevas reservas'));
    await usuario.click(screen.getByRole('button', { name: 'Registrar incidencia' }));
    expect(api.crearIncidencia).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Sí, registrar y bloquear' })).toHaveFocus();
    await usuario.click(screen.getByRole('button', { name: 'Sí, registrar y bloquear' }));
    await waitFor(() => expect(api.crearIncidencia).toHaveBeenCalledWith({
      equipment_id: 1, title: incidencia.title, description: incidencia.description, priority: 'high', blocking: true,
    }));
    expect(await screen.findByRole('heading', { name: 'Conector dañado' })).toBeInTheDocument();
    expect(screen.getByText(incidencia.warning ?? '')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Reserva #12' })).toHaveAttribute('href', '/admin/reservas/12');
  });

  it("conserva los datos de creación cuando el servidor rechaza la solicitud y permite corregirlos", async () => {
    const usuario = userEvent.setup();
    const crear = vi.spyOn(api, 'crearIncidencia').mockRejectedValueOnce(new ErrorApi('El equipo ya no existe.', 404));
    renderizarPagina('/admin/incidencias/nueva?equipment_id=1');
    await screen.findByRole('option', { name: 'CAM-001 · Cámara Aurora' });
    await usuario.type(screen.getByLabelText('Título'), 'Revisar conexión');
    await usuario.type(screen.getByLabelText('Descripción'), 'Fallo intermitente.');
    await usuario.click(screen.getByRole('button', { name: 'Registrar incidencia' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('El equipo ya no existe.');
    expect(screen.getByLabelText('Título')).toHaveValue('Revisar conexión');
    expect(screen.getByLabelText('Descripción')).toHaveValue('Fallo intermitente.');
    crear.mockResolvedValueOnce(incidencia);
    await usuario.click(screen.getByRole('button', { name: 'Registrar incidencia' }));
    expect(await screen.findByRole('heading', { name: 'Conector dañado' })).toBeInTheDocument();
  });

  it("exige una resolución, la conserva tras un conflicto y presenta la resolución persistida al reintentar", async () => {
    const usuario = userEvent.setup();
    const resuelto = { ...incidencia, status: 'resolved' as const, resolution: 'Conector sustituido.' };
    const cambio = vi.spyOn(api, 'cambiarEstadoIncidencia')
      .mockRejectedValueOnce(new ErrorApi('La incidencia cambió. Comprueba su estado.', 409))
      .mockResolvedValueOnce(resuelto);
    vi.mocked(api.obtenerIncidencia).mockResolvedValueOnce(incidencia).mockResolvedValue(resuelto);
    renderizarPagina('/admin/incidencias/4');
    await screen.findByRole('heading', { name: incidencia.title });
    await usuario.type(screen.getByLabelText('Resolución'), '   ');
    await usuario.click(screen.getByRole('button', { name: 'Resolver incidencia' }));
    expect(cambio).not.toHaveBeenCalled();
    expect(await screen.findByRole('alert')).toHaveTextContent('Explica cómo se ha resuelto la incidencia.');
    expect(screen.getByLabelText('Resolución')).toHaveAttribute('aria-invalid', 'true');
    await usuario.clear(screen.getByLabelText('Resolución'));
    await usuario.type(screen.getByLabelText('Resolución'), 'Conector sustituido.');
    await usuario.click(screen.getByRole('button', { name: 'Resolver incidencia' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('La incidencia cambió. Comprueba su estado.');
    expect(screen.getByLabelText('Resolución')).toHaveValue('Conector sustituido.');
    await usuario.click(screen.getByRole('button', { name: 'Resolver incidencia' }));
    await waitFor(() => expect(cambio).toHaveBeenLastCalledWith(4, { status: 'resolved', resolution: 'Conector sustituido.' }));
    expect(await screen.findByText('Conector sustituido.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resolver incidencia' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Iniciar trabajo' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Datos de la incidencia' })).toHaveFocus();
  });

  it("inicia el trabajo mediante la API y ofrece solo resolver tras persistir la transición", async () => {
    const usuario = userEvent.setup();
    const enCurso = { ...incidencia, status: 'in_progress' as const };
    const cambio = vi.spyOn(api, 'cambiarEstadoIncidencia').mockResolvedValue(enCurso);
    vi.mocked(api.obtenerIncidencia).mockResolvedValueOnce(incidencia).mockResolvedValue(enCurso);
    renderizarPagina('/admin/incidencias/4');
    await usuario.click(await screen.findByRole('button', { name: 'Iniciar trabajo' }));
    await waitFor(() => expect(cambio).toHaveBeenCalledWith(4, { status: 'in_progress' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Iniciar trabajo' })).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Resolver incidencia' })).toBeInTheDocument();
    expect(screen.getByLabelText('Resolución')).toHaveFocus();
  });

  it("evita mostrar la incidencia anterior cuando falla la carga de otro identificador en la misma ruta", async () => {
    const usuario = userEvent.setup();
    const cambio = vi.spyOn(api, 'cambiarEstadoIncidencia');
    vi.mocked(api.obtenerIncidencia).mockResolvedValueOnce(incidencia).mockRejectedValue(new ErrorApi('La incidencia no existe.', 404));
    render(<MemoryRouter initialEntries={['/admin/incidencias/4']}>
      <Link to="/admin/incidencias/999">Ir a otra incidencia</Link>
      <Routes><Route path="/admin/incidencias/:id" element={<PaginaDetalleIncidencia />} /></Routes>
    </MemoryRouter>);
    await screen.findByRole('heading', { name: incidencia.title });
    await usuario.type(screen.getByLabelText('Resolución'), 'Borrador del equipo anterior');
    await usuario.click(screen.getByRole('link', { name: 'Ir a otra incidencia' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('La incidencia no existe.');
    expect(screen.queryByRole('heading', { name: incidencia.title })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Iniciar trabajo' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resolver incidencia' })).not.toBeInTheDocument();
    expect(cambio).not.toHaveBeenCalled();
  });

  it("muestra el resultado persistido del PATCH aunque falle el GET posterior", async () => {
    const usuario = userEvent.setup();
    const resuelto = { ...incidencia, status: 'resolved' as const, resolution: 'Conector sustituido.' };
    vi.spyOn(api, 'cambiarEstadoIncidencia').mockResolvedValue(resuelto);
    vi.mocked(api.obtenerIncidencia).mockResolvedValueOnce(incidencia).mockRejectedValue(new ErrorApi('No se pudo actualizar la consulta.', 0));
    renderizarPagina('/admin/incidencias/4');
    await screen.findByRole('heading', { name: incidencia.title });
    await usuario.type(screen.getByLabelText('Resolución'), resuelto.resolution);
    await usuario.click(screen.getByRole('button', { name: 'Resolver incidencia' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo actualizar la consulta.');
    expect(screen.queryByRole('button', { name: 'Resolver incidencia' })).not.toBeInTheDocument();
    expect(screen.getByText(resuelto.resolution)).toBeInTheDocument();
    expect(screen.getByText('Resuelta')).toBeInTheDocument();
  });

  it("identifica avisos de clientes por su reserva y mantiene visibles las incidencias históricas sin autor", async () => {
    const informe = { ...incidencia, id: 5, title: 'Aviso desde el portal', reservation_id: 23, author_user_id: 8, blocking: false };
    vi.mocked(api.listarIncidencias).mockResolvedValue([incidencia, informe]);
    renderizarPagina('/admin/incidencias');
    const filaCliente = (await screen.findByRole('link', { name: informe.title })).closest('tr')!;
    expect(within(filaCliente).getByText('Aviso de cliente')).toBeInTheDocument();
    expect(within(filaCliente).getByRole('link', { name: 'Reserva #23' })).toHaveAttribute('href', '/admin/reservas/23');
    expect(within(filaCliente).getByText('Usuario #8')).toBeInTheDocument();
    const filaHistorica = screen.getByRole('link', { name: incidencia.title }).closest('tr')!;
    expect(within(filaHistorica).getByText('Interna o histórica sin reserva vinculada')).toBeInTheDocument();
    expect(within(filaHistorica).getByText('Sin autor de cuenta registrado')).toBeInTheDocument();
  });

  it("guarda prioridad, notas internas y una respuesta al cliente independiente sin resolver la incidencia", async () => {
    const usuario = userEvent.setup();
    const guardado = { ...incidencia, priority: 'low' as const, internal_notes: 'Diagnóstico para el taller.', public_response: 'Estamos revisando tu aviso.' };
    const cambios = vi.spyOn(api, 'modificarIncidencia').mockResolvedValue(guardado);
    const cambiarEstado = vi.spyOn(api, 'cambiarEstadoIncidencia');
    vi.mocked(api.obtenerIncidencia).mockResolvedValueOnce(incidencia).mockResolvedValue(guardado);
    renderizarPagina('/admin/incidencias/4');
    await screen.findByRole('heading', { name: incidencia.title });
    await usuario.selectOptions(screen.getByLabelText('Prioridad'), 'low');
    await usuario.type(screen.getByLabelText('Notas internas'), guardado.internal_notes);
    await usuario.type(screen.getByLabelText('Respuesta visible al cliente'), guardado.public_response);
    await usuario.type(screen.getByLabelText('Resolución'), 'Borrador de resolución interna.');
    await usuario.click(screen.getByRole('button', { name: 'Guardar gestión' }));
    await waitFor(() => expect(cambios).toHaveBeenCalledWith(4, {
      priority: 'low', blocking: true, internal_notes: guardado.internal_notes, public_response: guardado.public_response,
    }));
    expect(cambiarEstado).not.toHaveBeenCalled();
    expect(await screen.findByText('Gestión de la incidencia guardada.')).toBeInTheDocument();
    expect(screen.getByLabelText('Notas internas')).toHaveValue(guardado.internal_notes);
    expect(screen.getByLabelText('Respuesta visible al cliente')).toHaveValue(guardado.public_response);
    expect(screen.getByLabelText('Resolución')).toHaveValue('Borrador de resolución interna.');
    expect(screen.getByRole('heading', { name: 'Datos de la incidencia' })).toHaveFocus();
  });

  it("exige confirmación antes de bloquear un aviso de cliente y conserva los valores tras un conflicto para reintentar expresamente", async () => {
    const usuario = userEvent.setup();
    const informe = { ...incidencia, reservation_id: 23, author_user_id: 8, blocking: false };
    const guardado = { ...informe, blocking: true, priority: 'high' as const, public_response: 'Revisaremos la conexión.', internal_notes: 'No publicar el diagnóstico.' };
    vi.mocked(api.obtenerIncidencia).mockResolvedValueOnce(informe).mockResolvedValue(guardado);
    const cambios = vi.spyOn(api, 'modificarIncidencia').mockRejectedValueOnce(new ErrorApi('No se pudo guardar. Inténtalo de nuevo.', 409)).mockResolvedValueOnce(guardado);
    renderizarPagina('/admin/incidencias/4');
    await screen.findByRole('heading', { name: informe.title });
    expect(screen.getByText('Aviso de cliente')).toBeInTheDocument();
    expect(screen.getByText('Usuario #8')).toBeInTheDocument();
    await usuario.type(screen.getByLabelText('Notas internas'), guardado.internal_notes);
    await usuario.type(screen.getByLabelText('Respuesta visible al cliente'), guardado.public_response);
    await usuario.click(screen.getByLabelText('Bloquea nuevas reservas'));
    await usuario.click(screen.getByRole('button', { name: 'Guardar gestión' }));
    expect(cambios).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Sí, guardar y bloquear' })).toHaveFocus();
    expect(screen.getByRole('group', { name: 'Confirmar bloqueo del equipo' })).toHaveTextContent('no se cancelan automáticamente');
    await usuario.click(screen.getByRole('button', { name: 'Volver a editar' }));
    expect(screen.getByRole('button', { name: 'Guardar gestión' })).toHaveFocus();
    expect(cambios).not.toHaveBeenCalled();
    await usuario.click(screen.getByRole('button', { name: 'Guardar gestión' }));
    await usuario.click(screen.getByRole('button', { name: 'Sí, guardar y bloquear' }));
    const error = await screen.findByRole('alert');
    expect(error).toHaveTextContent('No se pudo guardar. Inténtalo de nuevo.');
    expect(error).toHaveFocus();
    expect(screen.getByLabelText('Notas internas')).toHaveValue(guardado.internal_notes);
    expect(screen.getByLabelText('Respuesta visible al cliente')).toHaveValue(guardado.public_response);
    await usuario.click(screen.getByRole('button', { name: 'Sí, guardar y bloquear' }));
    await waitFor(() => expect(cambios).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Impide nuevas reservas de este equipo.')).toBeInTheDocument();
  });

  it("conserva la respuesta de gestión tras una actualización fallida y mantiene privada y sin cambios la resolución interna", async () => {
    const usuario = userEvent.setup();
    const resuelto = { ...incidencia, status: 'resolved' as const, resolution: 'Trabajo técnico interno.', internal_notes: 'Nota anterior.', public_response: 'Aviso recibido.' };
    const guardado = { ...resuelto, priority: 'low' as const, internal_notes: 'Nota nueva.', public_response: 'El equipo está revisado.' };
    vi.mocked(api.obtenerIncidencia).mockResolvedValueOnce(resuelto).mockRejectedValue(new ErrorApi('No se pudo recargar la incidencia.', 0));
    vi.spyOn(api, 'modificarIncidencia').mockResolvedValue(guardado);
    const cambiarEstado = vi.spyOn(api, 'cambiarEstadoIncidencia');
    renderizarPagina('/admin/incidencias/4');
    await screen.findByRole('heading', { name: resuelto.title });
    await usuario.selectOptions(screen.getByLabelText('Prioridad'), 'low');
    await usuario.clear(screen.getByLabelText('Notas internas'));
    await usuario.type(screen.getByLabelText('Notas internas'), guardado.internal_notes);
    await usuario.clear(screen.getByLabelText('Respuesta visible al cliente'));
    await usuario.type(screen.getByLabelText('Respuesta visible al cliente'), guardado.public_response);
    await usuario.click(screen.getByRole('button', { name: 'Guardar gestión' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo recargar la incidencia.');
    expect(screen.getByLabelText('Prioridad')).toHaveValue('low');
    expect(screen.getByLabelText('Notas internas')).toHaveValue(guardado.internal_notes);
    expect(screen.getByLabelText('Respuesta visible al cliente')).toHaveValue(guardado.public_response);
    expect(screen.getByText(resuelto.resolution)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resolver incidencia' })).not.toBeInTheDocument();
    expect(cambiarEstado).not.toHaveBeenCalled();
  });

  it("actualiza la lista administrativa después de un cambio externo de estado", async () => {
    const usuario = userEvent.setup();
    vi.mocked(api.listarIncidencias).mockResolvedValueOnce([incidencia]).mockResolvedValue([{ ...incidencia, status: 'in_progress' }]);
    renderizarPagina('/admin/incidencias');
    await screen.findByRole('link', { name: incidencia.title });
    expect(within(screen.getByRole('table')).getByText('Abierta')).toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: 'Actualizar listado' }));
    expect(within(await screen.findByRole('table')).getByText('En curso')).toBeInTheDocument();
    expect(api.listarIncidencias).toHaveBeenCalledTimes(2);
  });

  it("muestra errores de campo sin perder borradores de gestión ni copiar notas privadas a la respuesta al cliente", async () => {
    const usuario = userEvent.setup();
    vi.spyOn(api, 'modificarIncidencia').mockRejectedValue(new ErrorApi('Contenido inválido.', 422, { public_response: 'Revisa el texto de respuesta.' }));
    renderizarPagina('/admin/incidencias/4');
    await screen.findByRole('heading', { name: incidencia.title });
    await usuario.type(screen.getByLabelText('Notas internas'), 'Diagnóstico reservado.');
    await usuario.type(screen.getByLabelText('Respuesta visible al cliente'), 'Respuesta por revisar.');
    await usuario.click(screen.getByRole('button', { name: 'Guardar gestión' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Revisa los campos indicados.');
    expect(screen.getByLabelText('Respuesta visible al cliente')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Respuesta visible al cliente')).toHaveValue('Respuesta por revisar.');
    expect(screen.getByLabelText('Notas internas')).toHaveValue('Diagnóstico reservado.');
    expect(screen.getByLabelText('Resolución')).toHaveValue('');
  });

  it("oculta los resultados anteriores cuando falla un filtro nuevo sin afirmar que coinciden con el estado seleccionado", async () => {
    const usuario = userEvent.setup();
    vi.mocked(api.listarIncidencias).mockResolvedValueOnce([incidencia]).mockRejectedValueOnce(new ErrorApi('No se pudieron consultar las incidencias resueltas.', 503));
    renderizarPagina('/admin/incidencias');
    await screen.findByRole('link', { name: incidencia.title });
    await usuario.selectOptions(screen.getByLabelText('Estado'), 'resolved');
    await usuario.click(screen.getByRole('button', { name: 'Aplicar filtros' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudieron consultar las incidencias resueltas.');
    expect(screen.getByLabelText('Estado')).toHaveValue('resolved');
    expect(screen.queryByRole('link', { name: incidencia.title })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Listado de incidencias' })).not.toBeInTheDocument();
    expect(api.listarIncidencias).toHaveBeenLastCalledWith({ status: 'resolved' });
  });
});
