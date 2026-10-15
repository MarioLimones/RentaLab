import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, type Equipment } from '../api/client';
import { EquipmentPage } from './EquipmentPage';
import { EquipmentFormPage } from './EquipmentFormPage';
import { EquipmentDetailPage } from './EquipmentDetailPage';

const camera: Equipment = { id: 1, code: 'CAM-001', name: 'Cámara Aurora', category: 'Cámaras', description: 'Unidad ficticia', active: true };
const microphone: Equipment = { id: 2, code: 'AUD-001', name: 'Micrófono Brisa', category: 'Audio', description: '', active: false };

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, 'listEquipment').mockResolvedValue([camera, microphone]);
  vi.spyOn(api, 'getEquipment').mockResolvedValue(camera);
  vi.spyOn(api, 'listReservations').mockResolvedValue([]);
  vi.spyOn(api, 'listIncidents').mockResolvedValue([]);
});

function renderPage(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/admin/equipos" element={<EquipmentPage />} />
    <Route path="/admin/equipos/nuevo" element={<EquipmentFormPage />} />
    <Route path="/admin/equipos/:id" element={<EquipmentDetailPage />} />
    <Route path="/admin/equipos/:id/editar" element={<EquipmentFormPage />} />
  </Routes></MemoryRouter>);
}

function fillEquipment() {
  fireEvent.change(screen.getByLabelText('Código'), { target: { value: 'CAM-003' } });
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Cámara Nube' } });
  fireEvent.change(screen.getByLabelText('Categoría'), { target: { value: 'Cámaras' } });
  fireEvent.change(screen.getByLabelText('Descripción interna (opcional)'), { target: { value: 'Tercera unidad ficticia' } });
}

describe('catálogo de equipos', () => {
  it('combina búsqueda por texto y filtros de estado y categoría', async () => {
    renderPage('/admin/equipos');
    await screen.findByRole('link', { name: 'Cámara Aurora' });
    fireEvent.change(screen.getByLabelText('Buscar equipos'), { target: { value: 'brisa' } });
    expect(screen.queryByRole('link', { name: 'Cámara Aurora' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Micrófono Brisa' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'active' } });
    expect(screen.getByText('No hay equipos con estos filtros')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Buscar equipos'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('Categoría'), { target: { value: 'Cámaras' } });
    expect(screen.getByRole('link', { name: 'Cámara Aurora' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Micrófono Brisa' })).not.toBeInTheDocument();
  });

  it('crea el equipo mediante la API y abre el detalle persistido', async () => {
    const created: Equipment = { ...camera, id: 3, code: 'CAM-003', name: 'Cámara Nube', description: 'Tercera unidad ficticia' };
    vi.spyOn(api, 'createEquipment').mockResolvedValue(created);
    vi.mocked(api.getEquipment).mockResolvedValue(created);
    renderPage('/admin/equipos/nuevo');
    fillEquipment();
    fireEvent.click(screen.getByRole('button', { name: 'Crear equipo' }));
    await screen.findByRole('heading', { name: 'Cámara Nube', level: 1 });
    expect(api.createEquipment).toHaveBeenCalledWith({ code: 'CAM-003', name: 'Cámara Nube', category: 'Cámaras', description: 'Tercera unidad ficticia', public_description: '', technical_specs: {}, image_url: null, active: true });
    expect(api.getEquipment).toHaveBeenCalledWith(3);
    expect(screen.getByText('Equipo creado correctamente.')).toBeInTheDocument();
  });

  it('conserva los datos al rechazar un código duplicado y permite corregirlo', async () => {
    vi.spyOn(api, 'createEquipment').mockRejectedValue(new ApiError('Ya existe un equipo con ese código.', 409));
    renderPage('/admin/equipos/nuevo');
    fillEquipment();
    fireEvent.click(screen.getByRole('button', { name: 'Crear equipo' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Ya existe un equipo con ese código.');
    expect(screen.getByLabelText('Código')).toHaveValue('CAM-003');
    expect(screen.getByLabelText('Nombre')).toHaveValue('Cámara Nube');
    expect(screen.getByLabelText('Descripción interna (opcional)')).toHaveValue('Tercera unidad ficticia');
    expect(screen.getByRole('button', { name: 'Crear equipo' })).toBeEnabled();
  });

  it('precarga y conserva la ficha pública al editar con PATCH el nombre de gestión', async () => {
    const equipmentWithPublicData = { ...camera, public_description: 'Cámara para documentales', technical_specs: { Resolución: '4K' }, image_url: '/api/public/images/equipment-placeholder.svg' };
    vi.mocked(api.getEquipment).mockResolvedValue(equipmentWithPublicData);
    vi.spyOn(api, 'patchEquipment').mockResolvedValue({ ...equipmentWithPublicData, name: 'Cámara Aurora revisada' });
    vi.spyOn(api, 'updateEquipment').mockResolvedValue(equipmentWithPublicData);
    renderPage('/admin/equipos/1/editar');
    await screen.findByDisplayValue('Cámara Aurora');
    expect(screen.getByLabelText('Descripción pública (opcional)')).toHaveValue('Cámara para documentales');
    expect(screen.getByLabelText('Nombre de característica 1')).toHaveValue('Resolución');
    expect(screen.getByLabelText('Valor de característica 1')).toHaveValue('4K');
    expect(screen.getByLabelText('Imagen (opcional)')).toHaveValue('/api/public/images/equipment-placeholder.svg');
    fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Cámara Aurora revisada' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
    await screen.findByRole('heading', { name: 'Cámara Aurora', level: 1 });
    expect(api.patchEquipment).toHaveBeenCalledWith(1, { code: camera.code, name: 'Cámara Aurora revisada', category: camera.category, description: camera.description, public_description: 'Cámara para documentales', technical_specs: { Resolución: '4K' }, image_url: '/api/public/images/equipment-placeholder.svg', active: camera.active });
    expect(api.updateEquipment).not.toHaveBeenCalled();
  });

  it('acepta el esquema HTTPS en mayúsculas conservado por el servidor al editar', async () => {
    const current = { ...camera, image_url: 'HTTPS://images.example.test/camera.jpg' };
    vi.mocked(api.getEquipment).mockResolvedValue(current);
    vi.spyOn(api, 'patchEquipment').mockResolvedValue(current);
    renderPage('/admin/equipos/1/editar');
    expect(await screen.findByLabelText('Imagen (opcional)')).toHaveValue(current.image_url);
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
    await waitFor(() => expect(api.patchEquipment).toHaveBeenCalledWith(1, expect.objectContaining({ image_url: current.image_url })));
  });

  it('guarda cambios públicos, retira la imagen y muestra la ficha persistida al volver al detalle', async () => {
    const initial = { ...camera, public_description: 'Descripción anterior', technical_specs: { Resolución: 'HD', Peso: '1 kg' }, image_url: 'https://example.test/camera.jpg' };
    const saved = { ...initial, public_description: 'Para entrevistas y documentales', technical_specs: { Resolución: '4K', Autonomía: '3 horas' }, image_url: null };
    vi.mocked(api.getEquipment).mockResolvedValueOnce(initial).mockResolvedValue(saved);
    vi.spyOn(api, 'patchEquipment').mockResolvedValue(saved);
    renderPage('/admin/equipos/1/editar');
    await screen.findByDisplayValue('Descripción anterior');
    fireEvent.change(screen.getByLabelText('Descripción pública (opcional)'), { target: { value: saved.public_description } });
    fireEvent.change(screen.getByLabelText('Valor de característica 1'), { target: { value: '4K' } });
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar característica 2' }));
    expect(screen.getByLabelText('Nombre de característica 1')).toHaveFocus();
    fireEvent.click(screen.getByRole('button', { name: 'Añadir característica' }));
    expect(screen.getByLabelText('Nombre de característica 2')).toHaveFocus();
    fireEvent.change(screen.getByLabelText('Nombre de característica 2'), { target: { value: 'Autonomía' } });
    fireEvent.change(screen.getByLabelText('Valor de característica 2'), { target: { value: '3 horas' } });
    fireEvent.change(screen.getByLabelText('Imagen (opcional)'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
    await screen.findByRole('heading', { name: 'Cámara Aurora', level: 1 });
    expect(api.patchEquipment).toHaveBeenCalledWith(1, { code: camera.code, name: camera.name, category: camera.category, description: camera.description, public_description: saved.public_description, technical_specs: saved.technical_specs, image_url: null, active: true });
    const publicData = within(screen.getByRole('region', { name: 'Ficha pública del catálogo' }));
    expect(publicData.getByText(saved.public_description)).toBeInTheDocument();
    expect(publicData.getByText('4K')).toBeInTheDocument();
    expect(publicData.getByText('3 horas')).toBeInTheDocument();
    expect(publicData.getByText('Alternativa local de RentaLab.')).toBeInTheDocument();
    expect(publicData.queryByText(camera.description)).not.toBeInTheDocument();
    expect(publicData.getByRole('link', { name: 'Ver ficha pública' })).toHaveAttribute('href', '/equipos/1');
  });

  it('crea una ficha pública con características e imagen local sin exigir una imagen externa', async () => {
    vi.spyOn(api, 'createEquipment').mockResolvedValue({ ...camera, id: 3 });
    renderPage('/admin/equipos/nuevo');
    fillEquipment();
    fireEvent.change(screen.getByLabelText('Descripción pública (opcional)'), { target: { value: 'Equipo ligero para rodajes' } });
    fireEvent.change(screen.getByLabelText('Imagen (opcional)'), { target: { value: '/api/public/images/equipment-placeholder.svg' } });
    fireEvent.click(screen.getByRole('button', { name: 'Añadir característica' }));
    fireEvent.change(screen.getByLabelText('Nombre de característica 1'), { target: { value: ' Resolución ' } });
    fireEvent.change(screen.getByLabelText('Valor de característica 1'), { target: { value: ' 4K ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Crear equipo' }));
    await waitFor(() => expect(api.createEquipment).toHaveBeenCalledWith(expect.objectContaining({ public_description: 'Equipo ligero para rodajes', technical_specs: { Resolución: '4K' }, image_url: '/api/public/images/equipment-placeholder.svg' })));
  });

  it('explica los errores de características duplicadas y vacías conservando el formulario', async () => {
    vi.spyOn(api, 'createEquipment').mockResolvedValue(camera);
    renderPage('/admin/equipos/nuevo');
    fillEquipment();
    fireEvent.click(screen.getByRole('button', { name: 'Añadir característica' }));
    fireEvent.change(screen.getByLabelText('Nombre de característica 1'), { target: { value: ' Resolución ' } });
    fireEvent.change(screen.getByLabelText('Valor de característica 1'), { target: { value: '4K' } });
    fireEvent.click(screen.getByRole('button', { name: 'Añadir característica' }));
    fireEvent.change(screen.getByLabelText('Nombre de característica 2'), { target: { value: 'Resolución' } });
    fireEvent.click(screen.getByRole('button', { name: 'Crear equipo' }));
    expect(screen.getByRole('alert')).toHaveFocus();
    expect(screen.getByLabelText('Nombre de característica 2')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Valor de característica 2')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Nombre de característica 2')).toHaveAccessibleDescription('Cada característica debe tener un nombre diferente.');
    expect(api.createEquipment).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Nombre')).toHaveValue('Cámara Nube');
  });

  it.each(['http://example.test/camera.jpg', 'javascript:alert(1)', '//example.test/camera.jpg', '/api/public/images/../private.jpg', 'https://person:secret@example.test/camera.jpg', 'https://example.test/camera.jpg?private=1', 'https://example.test/camera.jpg#fragmento'])('rechaza imagen no pública o insegura: %s', async (url) => {
    vi.spyOn(api, 'createEquipment').mockResolvedValue(camera);
    renderPage('/admin/equipos/nuevo');
    fillEquipment();
    fireEvent.change(screen.getByLabelText('Imagen (opcional)'), { target: { value: url } });
    fireEvent.click(screen.getByRole('button', { name: 'Crear equipo' }));
    expect(screen.getByLabelText('Imagen (opcional)')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('Usa una URL HTTPS');
    expect(api.createEquipment).not.toHaveBeenCalled();
  });

  it('muestra los errores públicos devueltos por el servidor sin perder las características', async () => {
    vi.spyOn(api, 'createEquipment').mockRejectedValue(new ApiError('Revisa los campos.', 422, { public_description: 'Revisa el texto público.', technical_specs: 'Revisa las características.' }));
    renderPage('/admin/equipos/nuevo');
    fillEquipment();
    fireEvent.change(screen.getByLabelText('Descripción pública (opcional)'), { target: { value: 'Descripción pendiente de corregir' } });
    fireEvent.click(screen.getByRole('button', { name: 'Añadir característica' }));
    fireEvent.change(screen.getByLabelText('Nombre de característica 1'), { target: { value: 'Resolución' } });
    fireEvent.change(screen.getByLabelText('Valor de característica 1'), { target: { value: '4K' } });
    fireEvent.click(screen.getByRole('button', { name: 'Crear equipo' }));
    await screen.findByRole('alert');
    expect(screen.getByLabelText('Descripción pública (opcional)')).toHaveAccessibleDescription('Visible para visitantes y clientes. Hasta 2000 caracteres. Revisa el texto público.');
    expect(screen.getByRole('group', { name: 'Características técnicas' })).toHaveAccessibleDescription(expect.stringContaining('Revisa las características.'));
    expect(screen.getByLabelText('Valor de característica 1')).toHaveValue('4K');
    expect(screen.getByRole('button', { name: 'Crear equipo' })).toBeEnabled();
  });

  it('limita las características a veinte y devuelve el foco al botón al eliminar la última', () => {
    renderPage('/admin/equipos/nuevo');
    const add = screen.getByRole('button', { name: 'Añadir característica' });
    for (let count = 0; count < 20; count++) fireEvent.click(add);
    expect(add).toBeDisabled();
    expect(screen.getByLabelText('Nombre de característica 20')).toHaveAttribute('maxlength', '80');
    expect(screen.getByLabelText('Valor de característica 20')).toHaveAttribute('maxlength', '300');
    for (let count = 20; count > 0; count--) fireEvent.click(screen.getByRole('button', { name: `Eliminar característica ${count}` }));
    expect(add).toBeEnabled();
    expect(add).toHaveFocus();
  });

  it('impide un segundo envío y bloquea la edición mientras se guarda', async () => {
    let finish!: (value: Equipment) => void;
    vi.spyOn(api, 'createEquipment').mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    renderPage('/admin/equipos/nuevo');
    fillEquipment();
    const form = screen.getByRole('button', { name: 'Crear equipo' }).closest('form')!;
    fireEvent.submit(form);
    expect(screen.getByRole('button', { name: 'Guardando…' })).toBeDisabled();
    expect(screen.getByLabelText('Nombre')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Añadir característica' })).toBeDisabled();
    fireEvent.submit(form);
    expect(api.createEquipment).toHaveBeenCalledTimes(1);
    await act(async () => finish(camera));
    await screen.findByRole('heading', { name: camera.name, level: 1 });
  });

  it('desactiva desde el detalle y muestra el estado devuelto por el servidor', async () => {
    vi.spyOn(api, 'patchEquipment').mockResolvedValue({ ...camera, active: false });
    vi.mocked(api.getEquipment).mockResolvedValueOnce(camera).mockResolvedValue({ ...camera, active: false });
    renderPage('/admin/equipos/1');
    await screen.findByRole('heading', { name: 'Cámara Aurora' });
    fireEvent.click(screen.getByRole('button', { name: 'Desactivar equipo' }));
    expect(await screen.findByText('Equipo desactivado correctamente.')).toBeInTheDocument();
    expect(api.patchEquipment).toHaveBeenCalledWith(1, { active: false });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Activar equipo' })).toBeEnabled());
    expect(api.getEquipment).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('link', { name: 'Ver ficha pública' })).not.toBeInTheDocument();
  });

  it('conserva la activación persistida si falla recargar el detalle y adopta la siguiente respuesta', async () => {
    const inactiveCamera = { ...camera, active: false };
    vi.spyOn(api, 'patchEquipment').mockResolvedValue(inactiveCamera);
    vi.mocked(api.getEquipment).mockResolvedValueOnce(camera).mockRejectedValueOnce(new ApiError('No se pudo actualizar el equipo.', 503)).mockResolvedValue(inactiveCamera);
    renderPage('/admin/equipos/1');
    await screen.findByRole('heading', { name: camera.name, level: 1 });
    fireEvent.click(screen.getByRole('button', { name: 'Desactivar equipo' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo actualizar el equipo.');
    expect(screen.getByRole('button', { name: 'Activar equipo' })).toBeEnabled();
    expect(screen.getByText('El equipo inactivo queda fuera del catálogo público.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Volver a cargar' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Activar equipo' })).toBeEnabled();
    expect(api.patchEquipment).toHaveBeenCalledTimes(1);
  });

  it('consulta de nuevo al actualizar y al regresar del detalle al listado', async () => {
    vi.mocked(api.listEquipment).mockResolvedValueOnce([camera]).mockResolvedValue([{ ...camera, name: 'Nombre actualizado' }]);
    renderPage('/admin/equipos');
    await screen.findByRole('link', { name: camera.name });
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar datos' }));
    await screen.findByRole('link', { name: 'Nombre actualizado' });
    fireEvent.click(screen.getByRole('link', { name: 'Nombre actualizado' }));
    await screen.findByRole('heading', { name: camera.name, level: 1 });
    fireEvent.click(screen.getByRole('link', { name: /Volver a equipos/ }));
    await screen.findByRole('link', { name: 'Nombre actualizado' });
    expect(api.listEquipment).toHaveBeenCalledTimes(3);
  });

  it('conserva el estado persistido y los filtros si falla la recarga después de desactivar', async () => {
    const inactiveCamera = { ...camera, active: false };
    vi.mocked(api.listEquipment)
      .mockResolvedValueOnce([camera, microphone])
      .mockRejectedValueOnce(new ApiError('No se pudo actualizar el catálogo.', 503))
      .mockResolvedValueOnce([inactiveCamera, microphone]);
    vi.spyOn(api, 'patchEquipment').mockResolvedValue(inactiveCamera);
    renderPage('/admin/equipos');
    await screen.findByRole('link', { name: 'Cámara Aurora' });
    fireEvent.change(screen.getByLabelText('Buscar equipos'), { target: { value: 'aurora' } });
    fireEvent.change(screen.getByLabelText('Categoría'), { target: { value: 'Cámaras' } });
    fireEvent.click(screen.getByRole('button', { name: 'Desactivar Cámara Aurora' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo actualizar el catálogo.');
    const row = screen.getByRole('link', { name: 'Cámara Aurora' }).closest('tr')!;
    expect(within(row).getByText('Inactivo')).toBeInTheDocument();
    expect(within(row).queryByText('Activo')).not.toBeInTheDocument();
    expect(within(row).getByRole('button', { name: 'Activar Cámara Aurora' })).toBeEnabled();
    expect(screen.getByLabelText('Buscar equipos')).toHaveValue('aurora');
    expect(screen.getByLabelText('Categoría')).toHaveValue('Cámaras');
    fireEvent.click(screen.getByRole('button', { name: 'Volver a cargar' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Activar Cámara Aurora' })).toBeEnabled();
    expect(api.patchEquipment).toHaveBeenCalledTimes(1);
  });

  it('impide otro cambio mientras se recarga el catálogo tras guardar', async () => {
    const inactiveCamera = { ...camera, active: false };
    let finishReload!: (items: Equipment[]) => void;
    const pendingReload = new Promise<Equipment[]>((resolve) => { finishReload = resolve; });
    vi.mocked(api.listEquipment).mockResolvedValueOnce([camera, microphone]).mockReturnValueOnce(pendingReload);
    vi.spyOn(api, 'patchEquipment').mockResolvedValue(inactiveCamera);
    renderPage('/admin/equipos');
    await screen.findByRole('link', { name: 'Cámara Aurora' });
    fireEvent.click(screen.getByRole('button', { name: 'Desactivar Cámara Aurora' }));
    await screen.findByText('Cargando equipos…');
    const activateButton = screen.getByRole('button', { name: 'Activar Cámara Aurora' });
    expect(activateButton).toBeDisabled();
    fireEvent.click(activateButton);
    expect(api.patchEquipment).toHaveBeenCalledTimes(1);
    await act(async () => finishReload([inactiveCamera, microphone]));
    expect(screen.getByRole('button', { name: 'Activar Cámara Aurora' })).toBeEnabled();
  });

  it('consulta las reservas e incidencias del equipo y ofrece enlaces de alta preseleccionada', async () => {
    vi.mocked(api.listReservations).mockResolvedValue([{ id: 5, equipment_id: 1, customer_name: 'Cliente ficticio', customer_email: 'cliente@example.test', start_date: '2026-11-10', end_date: '2026-11-12', status: 'confirmed', external_reference: null }]);
    vi.mocked(api.listIncidents).mockResolvedValue([{ id: 9, equipment_id: 1, title: 'Visor roto', description: '', priority: 'high', blocking: true, status: 'open', resolution: '', confirmed_reservation_ids: [5], warning: 'Hay reservas confirmadas.' }]);
    renderPage('/admin/equipos/1');
    await screen.findByRole('heading', { name: 'Cámara Aurora' });
    expect(api.listReservations).toHaveBeenCalledWith({ equipment_id: 1 });
    expect(api.listIncidents).toHaveBeenCalledWith({ equipment_id: 1 });
    expect(screen.getByRole('link', { name: /Cliente ficticio/ })).toHaveAttribute('href', '/admin/reservas/5');
    expect(screen.getByRole('link', { name: /Visor roto/ })).toHaveAttribute('href', '/admin/incidencias/9');
    expect(screen.getByRole('link', { name: 'Crear reserva' })).toHaveAttribute('href', '/admin/reservas/nueva?equipment_id=1');
    expect(screen.getByRole('link', { name: 'Registrar incidencia' })).toHaveAttribute('href', '/admin/incidencias/nueva?equipment_id=1');
    expect(within(screen.getByRole('region', { name: 'Incidencias del equipo' })).getByText('Bloqueante')).toBeInTheDocument();
  });
});
