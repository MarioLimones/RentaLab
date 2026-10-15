import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ErrorApi, type Equipo } from '../api/cliente';
import { PaginaEquipos } from './PaginaEquipos';
import { PaginaFormularioEquipo } from './PaginaFormularioEquipo';
import { PaginaDetalleEquipo } from './PaginaDetalleEquipo';

const camara: Equipo = { id: 1, code: 'CAM-001', name: 'Cámara Aurora', category: 'Cámaras', description: 'Unidad ficticia', active: true };
const microfono: Equipo = { id: 2, code: 'AUD-001', name: 'Micrófono Brisa', category: 'Audio', description: '', active: false };

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, 'listarEquipos').mockResolvedValue([camara, microfono]);
  vi.spyOn(api, 'obtenerEquipo').mockResolvedValue(camara);
  vi.spyOn(api, 'listarReservas').mockResolvedValue([]);
  vi.spyOn(api, 'listarIncidencias').mockResolvedValue([]);
});

function renderizarPagina(ruta: string) {
  return render(<MemoryRouter initialEntries={[ruta]}><Routes>
    <Route path="/admin/equipos" element={<PaginaEquipos />} />
    <Route path="/admin/equipos/nuevo" element={<PaginaFormularioEquipo />} />
    <Route path="/admin/equipos/:id" element={<PaginaDetalleEquipo />} />
    <Route path="/admin/equipos/:id/editar" element={<PaginaFormularioEquipo />} />
  </Routes></MemoryRouter>);
}

function rellenarEquipo() {
  fireEvent.change(screen.getByLabelText('Código'), { target: { value: 'CAM-003' } });
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Cámara Nube' } });
  fireEvent.change(screen.getByLabelText('Categoría'), { target: { value: 'Cámaras' } });
  fireEvent.change(screen.getByLabelText('Descripción interna (opcional)'), { target: { value: 'Tercera unidad ficticia' } });
}

describe('catálogo de equipos', () => {
  it('combina búsqueda por texto y filtros de estado y categoría', async () => {
    renderizarPagina('/admin/equipos');
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
    const creado: Equipo = { ...camara, id: 3, code: 'CAM-003', name: 'Cámara Nube', description: 'Tercera unidad ficticia' };
    vi.spyOn(api, 'crearEquipo').mockResolvedValue(creado);
    vi.mocked(api.obtenerEquipo).mockResolvedValue(creado);
    renderizarPagina('/admin/equipos/nuevo');
    rellenarEquipo();
    fireEvent.click(screen.getByRole('button', { name: 'Crear equipo' }));
    await screen.findByRole('heading', { name: 'Cámara Nube', level: 1 });
    expect(api.crearEquipo).toHaveBeenCalledWith({ code: 'CAM-003', name: 'Cámara Nube', category: 'Cámaras', description: 'Tercera unidad ficticia', public_description: '', technical_specs: {}, image_url: null, active: true });
    expect(api.obtenerEquipo).toHaveBeenCalledWith(3);
    expect(screen.getByText('Equipo creado correctamente.')).toBeInTheDocument();
  });

  it('conserva los datos al rechazar un código duplicado y permite corregirlo', async () => {
    vi.spyOn(api, 'crearEquipo').mockRejectedValue(new ErrorApi('Ya existe un equipo con ese código.', 409));
    renderizarPagina('/admin/equipos/nuevo');
    rellenarEquipo();
    fireEvent.click(screen.getByRole('button', { name: 'Crear equipo' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Ya existe un equipo con ese código.');
    expect(screen.getByLabelText('Código')).toHaveValue('CAM-003');
    expect(screen.getByLabelText('Nombre')).toHaveValue('Cámara Nube');
    expect(screen.getByLabelText('Descripción interna (opcional)')).toHaveValue('Tercera unidad ficticia');
    expect(screen.getByRole('button', { name: 'Crear equipo' })).toBeEnabled();
  });

  it('precarga y conserva la ficha pública al editar con PATCH el nombre de gestión', async () => {
    const equipoConDatosPublicos = { ...camara, public_description: 'Cámara para documentales', technical_specs: { Resolución: '4K' }, image_url: '/api/public/images/equipment-placeholder.svg' };
    vi.mocked(api.obtenerEquipo).mockResolvedValue(equipoConDatosPublicos);
    vi.spyOn(api, 'modificarEquipo').mockResolvedValue({ ...equipoConDatosPublicos, name: 'Cámara Aurora revisada' });
    vi.spyOn(api, 'actualizarEquipo').mockResolvedValue(equipoConDatosPublicos);
    renderizarPagina('/admin/equipos/1/editar');
    await screen.findByDisplayValue('Cámara Aurora');
    expect(screen.getByLabelText('Descripción pública (opcional)')).toHaveValue('Cámara para documentales');
    expect(screen.getByLabelText('Nombre de característica 1')).toHaveValue('Resolución');
    expect(screen.getByLabelText('Valor de característica 1')).toHaveValue('4K');
    expect(screen.getByLabelText('Imagen (opcional)')).toHaveValue('/api/public/images/equipment-placeholder.svg');
    fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Cámara Aurora revisada' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
    await screen.findByRole('heading', { name: 'Cámara Aurora', level: 1 });
    expect(api.modificarEquipo).toHaveBeenCalledWith(1, { code: camara.code, name: 'Cámara Aurora revisada', category: camara.category, description: camara.description, public_description: 'Cámara para documentales', technical_specs: { Resolución: '4K' }, image_url: '/api/public/images/equipment-placeholder.svg', active: camara.active });
    expect(api.actualizarEquipo).not.toHaveBeenCalled();
  });

  it('acepta el esquema HTTPS en mayúsculas conservado por el servidor al editar', async () => {
    const actual = { ...camara, image_url: 'HTTPS://images.example.test/camera.jpg' };
    vi.mocked(api.obtenerEquipo).mockResolvedValue(actual);
    vi.spyOn(api, 'modificarEquipo').mockResolvedValue(actual);
    renderizarPagina('/admin/equipos/1/editar');
    expect(await screen.findByLabelText('Imagen (opcional)')).toHaveValue(actual.image_url);
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
    await waitFor(() => expect(api.modificarEquipo).toHaveBeenCalledWith(1, expect.objectContaining({ image_url: actual.image_url })));
  });

  it('guarda cambios públicos, retira la imagen y muestra la ficha persistida al volver al detalle', async () => {
    const inicial = { ...camara, public_description: 'Descripción anterior', technical_specs: { Resolución: 'HD', Peso: '1 kg' }, image_url: 'https://example.test/camera.jpg' };
    const guardado = { ...inicial, public_description: 'Para entrevistas y documentales', technical_specs: { Resolución: '4K', Autonomía: '3 horas' }, image_url: null };
    vi.mocked(api.obtenerEquipo).mockResolvedValueOnce(inicial).mockResolvedValue(guardado);
    vi.spyOn(api, 'modificarEquipo').mockResolvedValue(guardado);
    renderizarPagina('/admin/equipos/1/editar');
    await screen.findByDisplayValue('Descripción anterior');
    fireEvent.change(screen.getByLabelText('Descripción pública (opcional)'), { target: { value: guardado.public_description } });
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
    expect(api.modificarEquipo).toHaveBeenCalledWith(1, { code: camara.code, name: camara.name, category: camara.category, description: camara.description, public_description: guardado.public_description, technical_specs: guardado.technical_specs, image_url: null, active: true });
    const datosPublicos = within(screen.getByRole('region', { name: 'Ficha pública del catálogo' }));
    expect(datosPublicos.getByText(guardado.public_description)).toBeInTheDocument();
    expect(datosPublicos.getByText('4K')).toBeInTheDocument();
    expect(datosPublicos.getByText('3 horas')).toBeInTheDocument();
    expect(datosPublicos.getByText('Alternativa local de RentaLab.')).toBeInTheDocument();
    expect(datosPublicos.queryByText(camara.description)).not.toBeInTheDocument();
    expect(datosPublicos.getByRole('link', { name: 'Ver ficha pública' })).toHaveAttribute('href', '/equipos/1');
  });

  it('crea una ficha pública con características e imagen local sin exigir una imagen externa', async () => {
    vi.spyOn(api, 'crearEquipo').mockResolvedValue({ ...camara, id: 3 });
    renderizarPagina('/admin/equipos/nuevo');
    rellenarEquipo();
    fireEvent.change(screen.getByLabelText('Descripción pública (opcional)'), { target: { value: 'Equipo ligero para rodajes' } });
    fireEvent.change(screen.getByLabelText('Imagen (opcional)'), { target: { value: '/api/public/images/equipment-placeholder.svg' } });
    fireEvent.click(screen.getByRole('button', { name: 'Añadir característica' }));
    fireEvent.change(screen.getByLabelText('Nombre de característica 1'), { target: { value: ' Resolución ' } });
    fireEvent.change(screen.getByLabelText('Valor de característica 1'), { target: { value: ' 4K ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Crear equipo' }));
    await waitFor(() => expect(api.crearEquipo).toHaveBeenCalledWith(expect.objectContaining({ public_description: 'Equipo ligero para rodajes', technical_specs: { Resolución: '4K' }, image_url: '/api/public/images/equipment-placeholder.svg' })));
  });

  it('explica los errores de características duplicadas y vacías conservando el formulario', async () => {
    vi.spyOn(api, 'crearEquipo').mockResolvedValue(camara);
    renderizarPagina('/admin/equipos/nuevo');
    rellenarEquipo();
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
    expect(api.crearEquipo).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Nombre')).toHaveValue('Cámara Nube');
  });

  it.each(['http://example.test/camera.jpg', 'javascript:alert(1)', '//example.test/camera.jpg', '/api/public/images/../private.jpg', 'https://person:secret@example.test/camera.jpg', 'https://example.test/camera.jpg?private=1', 'https://example.test/camera.jpg#fragmento'])('rechaza imagen no pública o insegura: %s', async (url) => {
    vi.spyOn(api, 'crearEquipo').mockResolvedValue(camara);
    renderizarPagina('/admin/equipos/nuevo');
    rellenarEquipo();
    fireEvent.change(screen.getByLabelText('Imagen (opcional)'), { target: { value: url } });
    fireEvent.click(screen.getByRole('button', { name: 'Crear equipo' }));
    expect(screen.getByLabelText('Imagen (opcional)')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('Usa una URL HTTPS');
    expect(api.crearEquipo).not.toHaveBeenCalled();
  });

  it('muestra los errores públicos devueltos por el servidor sin perder las características', async () => {
    vi.spyOn(api, 'crearEquipo').mockRejectedValue(new ErrorApi('Revisa los campos.', 422, { public_description: 'Revisa el texto público.', technical_specs: 'Revisa las características.' }));
    renderizarPagina('/admin/equipos/nuevo');
    rellenarEquipo();
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
    renderizarPagina('/admin/equipos/nuevo');
    const anadir = screen.getByRole('button', { name: 'Añadir característica' });
    for (let cantidad = 0; cantidad < 20; cantidad++) fireEvent.click(anadir);
    expect(anadir).toBeDisabled();
    expect(screen.getByLabelText('Nombre de característica 20')).toHaveAttribute('maxlength', '80');
    expect(screen.getByLabelText('Valor de característica 20')).toHaveAttribute('maxlength', '300');
    for (let cantidad = 20; cantidad > 0; cantidad--) fireEvent.click(screen.getByRole('button', { name: `Eliminar característica ${cantidad}` }));
    expect(anadir).toBeEnabled();
    expect(anadir).toHaveFocus();
  });

  it('impide un segundo envío y bloquea la edición mientras se guarda', async () => {
    let finalizar!: (valor: Equipo) => void;
    vi.spyOn(api, 'crearEquipo').mockReturnValue(new Promise((resolver) => { finalizar = resolver; }));
    renderizarPagina('/admin/equipos/nuevo');
    rellenarEquipo();
    const formulario = screen.getByRole('button', { name: 'Crear equipo' }).closest('form')!;
    fireEvent.submit(formulario);
    expect(screen.getByRole('button', { name: 'Guardando…' })).toBeDisabled();
    expect(screen.getByLabelText('Nombre')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Añadir característica' })).toBeDisabled();
    fireEvent.submit(formulario);
    expect(api.crearEquipo).toHaveBeenCalledTimes(1);
    await act(async () => finalizar(camara));
    await screen.findByRole('heading', { name: camara.name, level: 1 });
  });

  it('desactiva desde el detalle y muestra el estado devuelto por el servidor', async () => {
    vi.spyOn(api, 'modificarEquipo').mockResolvedValue({ ...camara, active: false });
    vi.mocked(api.obtenerEquipo).mockResolvedValueOnce(camara).mockResolvedValue({ ...camara, active: false });
    renderizarPagina('/admin/equipos/1');
    await screen.findByRole('heading', { name: 'Cámara Aurora' });
    fireEvent.click(screen.getByRole('button', { name: 'Desactivar equipo' }));
    expect(await screen.findByText('Equipo desactivado correctamente.')).toBeInTheDocument();
    expect(api.modificarEquipo).toHaveBeenCalledWith(1, { active: false });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Activar equipo' })).toBeEnabled());
    expect(api.obtenerEquipo).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('link', { name: 'Ver ficha pública' })).not.toBeInTheDocument();
  });

  it('conserva la activación persistida si falla recargar el detalle y adopta la siguiente respuesta', async () => {
    const camaraInactiva = { ...camara, active: false };
    vi.spyOn(api, 'modificarEquipo').mockResolvedValue(camaraInactiva);
    vi.mocked(api.obtenerEquipo).mockResolvedValueOnce(camara).mockRejectedValueOnce(new ErrorApi('No se pudo actualizar el equipo.', 503)).mockResolvedValue(camaraInactiva);
    renderizarPagina('/admin/equipos/1');
    await screen.findByRole('heading', { name: camara.name, level: 1 });
    fireEvent.click(screen.getByRole('button', { name: 'Desactivar equipo' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo actualizar el equipo.');
    expect(screen.getByRole('button', { name: 'Activar equipo' })).toBeEnabled();
    expect(screen.getByText('El equipo inactivo queda fuera del catálogo público.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Volver a cargar' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Activar equipo' })).toBeEnabled();
    expect(api.modificarEquipo).toHaveBeenCalledTimes(1);
  });

  it('consulta de nuevo al actualizar y al regresar del detalle al listado', async () => {
    vi.mocked(api.listarEquipos).mockResolvedValueOnce([camara]).mockResolvedValue([{ ...camara, name: 'Nombre actualizado' }]);
    renderizarPagina('/admin/equipos');
    await screen.findByRole('link', { name: camara.name });
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar datos' }));
    await screen.findByRole('link', { name: 'Nombre actualizado' });
    fireEvent.click(screen.getByRole('link', { name: 'Nombre actualizado' }));
    await screen.findByRole('heading', { name: camara.name, level: 1 });
    fireEvent.click(screen.getByRole('link', { name: /Volver a equipos/ }));
    await screen.findByRole('link', { name: 'Nombre actualizado' });
    expect(api.listarEquipos).toHaveBeenCalledTimes(3);
  });

  it('conserva el estado persistido y los filtros si falla la recarga después de desactivar', async () => {
    const camaraInactiva = { ...camara, active: false };
    vi.mocked(api.listarEquipos)
      .mockResolvedValueOnce([camara, microfono])
      .mockRejectedValueOnce(new ErrorApi('No se pudo actualizar el catálogo.', 503))
      .mockResolvedValueOnce([camaraInactiva, microfono]);
    vi.spyOn(api, 'modificarEquipo').mockResolvedValue(camaraInactiva);
    renderizarPagina('/admin/equipos');
    await screen.findByRole('link', { name: 'Cámara Aurora' });
    fireEvent.change(screen.getByLabelText('Buscar equipos'), { target: { value: 'aurora' } });
    fireEvent.change(screen.getByLabelText('Categoría'), { target: { value: 'Cámaras' } });
    fireEvent.click(screen.getByRole('button', { name: 'Desactivar Cámara Aurora' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo actualizar el catálogo.');
    const fila = screen.getByRole('link', { name: 'Cámara Aurora' }).closest('tr')!;
    expect(within(fila).getByText('Inactivo')).toBeInTheDocument();
    expect(within(fila).queryByText('Activo')).not.toBeInTheDocument();
    expect(within(fila).getByRole('button', { name: 'Activar Cámara Aurora' })).toBeEnabled();
    expect(screen.getByLabelText('Buscar equipos')).toHaveValue('aurora');
    expect(screen.getByLabelText('Categoría')).toHaveValue('Cámaras');
    fireEvent.click(screen.getByRole('button', { name: 'Volver a cargar' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Activar Cámara Aurora' })).toBeEnabled();
    expect(api.modificarEquipo).toHaveBeenCalledTimes(1);
  });

  it('impide otro cambio mientras se recarga el catálogo tras guardar', async () => {
    const camaraInactiva = { ...camara, active: false };
    let finalizarRecarga!: (elementos: Equipo[]) => void;
    const recargaPendiente = new Promise<Equipo[]>((resolver) => { finalizarRecarga = resolver; });
    vi.mocked(api.listarEquipos).mockResolvedValueOnce([camara, microfono]).mockReturnValueOnce(recargaPendiente);
    vi.spyOn(api, 'modificarEquipo').mockResolvedValue(camaraInactiva);
    renderizarPagina('/admin/equipos');
    await screen.findByRole('link', { name: 'Cámara Aurora' });
    fireEvent.click(screen.getByRole('button', { name: 'Desactivar Cámara Aurora' }));
    await screen.findByText('Cargando equipos…');
    const botonActivar = screen.getByRole('button', { name: 'Activar Cámara Aurora' });
    expect(botonActivar).toBeDisabled();
    fireEvent.click(botonActivar);
    expect(api.modificarEquipo).toHaveBeenCalledTimes(1);
    await act(async () => finalizarRecarga([camaraInactiva, microfono]));
    expect(screen.getByRole('button', { name: 'Activar Cámara Aurora' })).toBeEnabled();
  });

  it('consulta las reservas e incidencias del equipo y ofrece enlaces de alta preseleccionada', async () => {
    vi.mocked(api.listarReservas).mockResolvedValue([{ id: 5, equipment_id: 1, customer_name: 'Cliente ficticio', customer_email: 'cliente@example.test', start_date: '2026-11-10', end_date: '2026-11-12', status: 'confirmed', external_reference: null }]);
    vi.mocked(api.listarIncidencias).mockResolvedValue([{ id: 9, equipment_id: 1, title: 'Visor roto', description: '', priority: 'high', blocking: true, status: 'open', resolution: '', confirmed_reservation_ids: [5], warning: 'Hay reservas confirmadas.' }]);
    renderizarPagina('/admin/equipos/1');
    await screen.findByRole('heading', { name: 'Cámara Aurora' });
    expect(api.listarReservas).toHaveBeenCalledWith({ equipment_id: 1 });
    expect(api.listarIncidencias).toHaveBeenCalledWith({ equipment_id: 1 });
    expect(screen.getByRole('link', { name: /Cliente ficticio/ })).toHaveAttribute('href', '/admin/reservas/5');
    expect(screen.getByRole('link', { name: /Visor roto/ })).toHaveAttribute('href', '/admin/incidencias/9');
    expect(screen.getByRole('link', { name: 'Crear reserva' })).toHaveAttribute('href', '/admin/reservas/nueva?equipment_id=1');
    expect(screen.getByRole('link', { name: 'Registrar incidencia' })).toHaveAttribute('href', '/admin/incidencias/nueva?equipment_id=1');
    expect(within(screen.getByRole('region', { name: 'Incidencias del equipo' })).getByText('Bloqueante')).toBeInTheDocument();
  });
});
