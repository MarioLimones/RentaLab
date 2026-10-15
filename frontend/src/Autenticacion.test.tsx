import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import Aplicacion from './Aplicacion';
import { api, ErrorApi } from './api/cliente';

const sesion = { authenticated: true as const, username: 'operador', expires_at: '2026-10-15T18:00:00Z', role: 'admin' as const, user: null };
const cliente = { id: 7, name: 'Cliente de prueba', email: 'cliente@example.test', role: 'customer' as const, active: true };
const sesionCliente = { ...sesion, username: cliente.email, role: 'customer' as const, user: cliente };
const fechas = { start_date: '2099-11-10', end_date: '2099-11-12' };
const equipo = {
  id: 1, name: 'Cámara Aurora', category: 'Cámaras', public_description: 'Cámara ficticia para entrevistas.',
  technical_specs: { Resolución: '4K' }, image_url: null, image_fallback_url: '/api/public/images/equipment-placeholder.svg', active_reservations_count: 0,
};
const destinoProducto = `/equipos/1?start_date=${fechas.start_date}&end_date=${fechas.end_date}`;

function Ubicacion() { const ubicacion = useLocation(); return <span data-testid="location">{ubicacion.pathname}{ubicacion.search}</span>; }
function renderizarAplicacion(ruta = '/admin/importaciones') { return render(<MemoryRouter initialEntries={[ruta]}><Aplicacion /><Ubicacion /></MemoryRouter>); }
function rellenarAcceso() {
  fireEvent.change(screen.getByLabelText('Usuario'), { target: { value: 'operador' } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
}

beforeEach(() => {
  sessionStorage.clear();
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.spyOn(api, 'saludServicio').mockResolvedValue({ status: 'ok' });
  vi.spyOn(api, 'sesion').mockRejectedValue(new ErrorApi('Se requiere iniciar sesión.', 401));
  vi.spyOn(api, 'listarEquipos').mockResolvedValue([]);
  vi.spyOn(api, 'listarEquiposPublicos').mockResolvedValue([]);
  vi.spyOn(api, 'listarReservas').mockResolvedValue([]);
  vi.spyOn(api, 'listarIncidencias').mockResolvedValue([]);
});

it("evita mostrar páginas privadas o cargar sus datos mientras comprueba la sesión", async () => {
  let resolverSesion: ((valor: typeof sesion) => void) | undefined;
  vi.mocked(api.sesion).mockImplementation(() => new Promise((resolver) => { resolverSesion = resolver; }));
  renderizarAplicacion('/admin/equipos');
  expect(screen.getByRole('status')).toHaveTextContent('Comprobando la sesión');
  expect(screen.queryByRole('navigation', { name: 'Principal' })).not.toBeInTheDocument();
  expect(api.listarEquipos).not.toHaveBeenCalled();
  await waitFor(() => expect(api.sesion).toHaveBeenCalledTimes(1));
  await act(async () => { resolverSesion?.(sesion); });
  expect(await screen.findByRole('heading', { name: 'Equipos', level: 1 })).toBeInTheDocument();
});

it("inicia sesión mediante el servidor y conserva la ruta completa solicitada", async () => {
  vi.spyOn(api, 'iniciarSesion').mockResolvedValue(sesion);
  renderizarAplicacion();
  await screen.findByRole('heading', { name: 'Acceder a RentaLab', level: 1 });
  rellenarAcceso();
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));
  expect(await screen.findByRole('heading', { name: 'Importaciones', level: 1 })).toBeInTheDocument();
  expect(api.iniciarSesion).toHaveBeenCalledWith({ username: 'operador', password: 'contraseña ficticia' });
  expect(screen.getByTestId('location')).toHaveTextContent('/admin/importaciones');
  expect(screen.queryByLabelText('Contraseña')).not.toBeInTheDocument();
  expect(screen.getByText('operador')).toBeInTheDocument();
});

it("conserva los valores tras credenciales incorrectas y enfoca el error accesible", async () => {
  vi.spyOn(api, 'iniciarSesion').mockRejectedValue(new ErrorApi('Usuario o contraseña incorrectos.', 401));
  renderizarAplicacion();
  await screen.findByLabelText('Usuario');
  rellenarAcceso();
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));
  const alerta = await screen.findByRole('alert');
  expect(alerta).toHaveTextContent('Usuario o contraseña incorrectos.');
  await waitFor(() => expect(alerta).toHaveFocus());
  expect(screen.getByLabelText('Usuario')).toHaveValue('operador');
  expect(screen.getByLabelText('Contraseña')).toHaveValue('contraseña ficticia');
});

it("ofrece etiquetas, autocompletado, envío con teclado y control de visibilidad de contraseña", async () => {
  vi.spyOn(api, 'iniciarSesion').mockResolvedValue(sesion);
  const usuario = userEvent.setup();
  renderizarAplicacion();
  const nombreUsuario = await screen.findByLabelText('Usuario');
  const contrasena = screen.getByLabelText('Contraseña');
  expect(nombreUsuario).toHaveAttribute('autocomplete', 'username');
  expect(contrasena).toHaveAttribute('autocomplete', 'current-password');
  expect(contrasena).toHaveAttribute('type', 'password');
  await usuario.click(screen.getByRole('button', { name: 'Mostrar contraseña' }));
  expect(contrasena).toHaveAttribute('type', 'text');
  expect(screen.getByRole('button', { name: 'Ocultar contraseña' })).toHaveAttribute('aria-pressed', 'true');
  await usuario.type(nombreUsuario, 'operador');
  await usuario.type(contrasena, 'ficticia{Enter}');
  expect(await screen.findByRole('heading', { name: 'Importaciones', level: 1 })).toBeInTheDocument();
});

it("muestra errores de campo sin enviar credenciales vacías", async () => {
  const iniciarSesion = vi.spyOn(api, 'iniciarSesion');
  renderizarAplicacion();
  await screen.findByLabelText('Usuario');
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Revisa los campos indicados.');
  expect(screen.getByLabelText('Usuario')).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByLabelText('Contraseña')).toHaveAttribute('aria-invalid', 'true');
  expect(iniciarSesion).not.toHaveBeenCalled();
});

it("espera al cierre correcto de sesión para retirar datos privados y conserva la ruta completa", async () => {
  vi.mocked(api.sesion).mockResolvedValue(sesion);
  vi.spyOn(api, 'cerrarSesionUsuario').mockResolvedValue({ authenticated: false });
  renderizarAplicacion();
  await screen.findByRole('heading', { name: 'Importaciones', level: 1 });
  fireEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }));
  expect(await screen.findByRole('heading', { name: 'Acceder a RentaLab', level: 1 })).toBeInTheDocument();
  expect(api.cerrarSesionUsuario).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('navigation', { name: 'Principal' })).not.toBeInTheDocument();
  expect(screen.getByTestId('location')).toHaveTextContent('/acceso?next=%2Fadmin%2Fimportaciones');
});

it("conserva la pantalla autenticada cuando el servidor no puede cerrar la sesión", async () => {
  vi.mocked(api.sesion).mockResolvedValue(sesion);
  vi.spyOn(api, 'cerrarSesionUsuario').mockRejectedValue(new ErrorApi('No se pudo conectar con el servidor.', 0));
  renderizarAplicacion();
  await screen.findByRole('heading', { name: 'Importaciones', level: 1 });
  fireEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo conectar');
  expect(screen.getByRole('heading', { name: 'Importaciones', level: 1 })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeEnabled();
});

it("gestiona un 401 operativo real retirando las pantallas privadas y mostrando el acceso", async () => {
  vi.mocked(api.sesion).mockResolvedValue(sesion);
  vi.mocked(api.listarEquipos).mockRestore();
  vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(Response.json({ detail: 'Sesión caducada.' }, { status: 401 })));
  renderizarAplicacion('/admin/equipos');
  await screen.findByRole('heading', { name: 'Acceder a RentaLab', level: 1 });
  expect(screen.queryByRole('heading', { name: 'Equipos', level: 1 })).not.toBeInTheDocument();
  expect(screen.queryByRole('navigation', { name: 'Principal' })).not.toBeInTheDocument();
  expect(screen.getByText('La sesión ha caducado. Inicia sesión para continuar.')).toBeInTheDocument();
});

it("ofrece un reintento explícito cuando no se puede comprobar la sesión", async () => {
  vi.mocked(api.sesion).mockRejectedValueOnce(new ErrorApi('No se pudo conectar.', 0)).mockResolvedValueOnce(sesion);
  renderizarAplicacion();
  expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo conectar.');
  expect(screen.queryByLabelText('Contraseña')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Volver a comprobar' }));
  expect(await screen.findByRole('heading', { name: 'Importaciones', level: 1 })).toBeInTheDocument();
  await waitFor(() => expect(api.sesion).toHaveBeenCalledTimes(2));
});

it("registra un cliente, confirma el resultado y vuelve al acceso con su correo", async () => {
  vi.spyOn(api, 'registrar').mockResolvedValue(cliente);
  const iniciarSesion = vi.spyOn(api, 'iniciarSesion');
  renderizarAplicacion();
  fireEvent.click(await within(await screen.findByRole('main')).findByRole('link', { name: 'Crear cuenta' }));
  expect(screen.getByRole('heading', { name: 'Crear cuenta', level: 1 })).toBeInTheDocument();
  expect(screen.getByLabelText('Correo electrónico')).toHaveAttribute('type', 'email');
  expect(screen.getByLabelText('Contraseña')).toHaveAttribute('autocomplete', 'new-password');
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: cliente.name } });
  fireEvent.change(screen.getByLabelText('Correo electrónico'), { target: { value: cliente.email } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
  expect(screen.queryByLabelText(/rol/i)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Crear mi cuenta' }));
  expect(await screen.findByRole('heading', { name: 'Acceder a RentaLab', level: 1 })).toBeInTheDocument();
  expect(screen.getByText('Cuenta creada. Ya puedes iniciar sesión.')).toHaveAttribute('role', 'status');
  expect(screen.getByLabelText('Usuario')).toHaveValue(cliente.email);
  expect(screen.getByLabelText('Contraseña')).toHaveValue('');
  expect(api.registrar).toHaveBeenCalledWith({ name: cliente.name, email: cliente.email, password: 'contraseña ficticia' });
  expect(iniciarSesion).not.toHaveBeenCalled();
});

it("conserva los datos de registro tras un correo duplicado y enfoca el error", async () => {
  vi.spyOn(api, 'registrar').mockRejectedValue(new ErrorApi('Ya existe una cuenta con ese correo.', 409));
  renderizarAplicacion();
  fireEvent.click(await within(await screen.findByRole('main')).findByRole('link', { name: 'Crear cuenta' }));
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: cliente.name } });
  fireEvent.change(screen.getByLabelText('Correo electrónico'), { target: { value: cliente.email } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
  fireEvent.click(screen.getByRole('button', { name: 'Crear mi cuenta' }));
  const alerta = await screen.findByRole('alert');
  expect(alerta).toHaveTextContent('Ya existe una cuenta con ese correo.');
  await waitFor(() => expect(alerta).toHaveFocus());
  expect(screen.getByLabelText('Nombre')).toHaveValue(cliente.name);
  expect(screen.getByLabelText('Correo electrónico')).toHaveValue(cliente.email);
  expect(screen.getByLabelText('Contraseña')).toHaveValue('contraseña ficticia');
});

it("explica los errores de registro sin enviar un formulario incompleto", async () => {
  const registrar = vi.spyOn(api, 'registrar');
  renderizarAplicacion();
  fireEvent.click(await within(await screen.findByRole('main')).findByRole('link', { name: 'Crear cuenta' }));
  fireEvent.click(screen.getByRole('button', { name: 'Crear mi cuenta' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Revisa los campos indicados.');
  expect(screen.getByLabelText('Nombre')).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByLabelText('Correo electrónico')).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByLabelText('Contraseña')).toHaveAttribute('aria-invalid', 'true');
  expect(registrar).not.toHaveBeenCalled();
});

it("deniega enlaces administrativos directos a clientes sin cargar datos privados de gestión", async () => {
  vi.mocked(api.sesion).mockResolvedValue({ ...sesion, username: cliente.email, role: 'customer', user: cliente });
  const reservas = vi.mocked(api.listarReservas);
  const incidencias = vi.mocked(api.listarIncidencias);
  renderizarAplicacion('/admin/reservas');
  expect(await screen.findByRole('heading', { name: 'Acceso restringido', level: 1 })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Volver a mi zona' })).toHaveAttribute('href', '/mi-cuenta');
  expect(api.listarEquipos).not.toHaveBeenCalled();
  expect(reservas).not.toHaveBeenCalled();
  expect(incidencias).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('link', { name: 'Volver a mi zona' }));
  expect(await screen.findByRole('heading', { name: 'Mi cuenta', level: 1 })).toBeInTheDocument();
  expect(screen.getByText(cliente.name)).toBeInTheDocument();
  expect(screen.getByText(cliente.email)).toBeInTheDocument();
  expect(screen.getByTestId('location')).toHaveTextContent('/mi-cuenta');
  expect(screen.queryByRole('link', { name: 'Panel de administración' })).not.toBeInTheDocument();
  expect(screen.queryByRole('navigation', { name: 'Principal' })).not.toBeInTheDocument();
  expect(api.listarEquipos).not.toHaveBeenCalled();
  expect(reservas).not.toHaveBeenCalled();
  expect(incidencias).not.toHaveBeenCalled();
});

it("permite al cliente acceder con su correo y cerrar la sesión", async () => {
  vi.spyOn(api, 'iniciarSesion').mockResolvedValue({ ...sesion, username: cliente.email, role: 'customer', user: cliente });
  vi.spyOn(api, 'cerrarSesionUsuario').mockResolvedValue({ authenticated: false });
  renderizarAplicacion('/acceso');
  fireEvent.change(await screen.findByLabelText('Usuario'), { target: { value: cliente.email } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));
  await screen.findByRole('heading', { name: 'Mi cuenta', level: 1 });
  expect(api.iniciarSesion).toHaveBeenCalledWith({ username: cliente.email, password: 'contraseña ficticia' });
  fireEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }));
  expect(await screen.findByRole('heading', { name: 'Acceder a RentaLab', level: 1 })).toBeInTheDocument();
});

it.each(['https://other.example.test/collect', '//other.example.test/collect', '/admin/importaciones'])(
  "ignora un destino de acceso externo o administrativo para un cliente: %s", async (siguiente) => {
    vi.spyOn(api, 'iniciarSesion').mockResolvedValue(sesionCliente);
    renderizarAplicacion(`/acceso?next=${encodeURIComponent(siguiente)}`);
    await screen.findByRole('heading', { name: 'Acceder a RentaLab' });
    fireEvent.change(screen.getByLabelText('Usuario'), { target: { value: cliente.email } });
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
    fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));
    await screen.findByRole('heading', { name: 'Mi cuenta', level: 1 });
    expect(screen.getByTestId('location')).toHaveTextContent('/mi-cuenta');
    expect(api.listarEquipos).not.toHaveBeenCalled();
  },
);

it("envía a los administradores a /admin si el destino de acceso es un producto de cliente", async () => {
  vi.spyOn(api, 'iniciarSesion').mockResolvedValue(sesion);
  renderizarAplicacion(`/acceso?next=${encodeURIComponent(destinoProducto)}`);
  await screen.findByRole('heading', { name: 'Acceder a RentaLab' });
  rellenarAcceso();
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));
  expect(await screen.findByRole('heading', { name: 'Resumen', level: 1 })).toBeInTheDocument();
  expect(screen.getByTestId('location')).toHaveTextContent('/admin');
});

it("conserva las fechas del equipo durante el registro sin iniciar sesión ni reservar automáticamente", async () => {
  vi.spyOn(api, 'registrar').mockResolvedValue(cliente);
  const iniciarSesion = vi.spyOn(api, 'iniciarSesion');
  const crear = vi.spyOn(api, 'crearMiReserva');
  renderizarAplicacion(`/acceso?next=${encodeURIComponent(destinoProducto)}`);
  fireEvent.click(await within(await screen.findByRole('main')).findByRole('link', { name: 'Crear cuenta' }));
  expect(screen.getByTestId('location')).toHaveTextContent(`/registro?next=${encodeURIComponent(destinoProducto)}`);
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: cliente.name } });
  fireEvent.change(screen.getByLabelText('Correo electrónico'), { target: { value: cliente.email } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
  fireEvent.click(screen.getByRole('button', { name: 'Crear mi cuenta' }));
  await screen.findByRole('heading', { name: 'Acceder a RentaLab' });
  expect(screen.getByTestId('location')).toHaveTextContent(`/acceso?next=${encodeURIComponent(destinoProducto)}`);
  expect(screen.getByLabelText('Usuario')).toHaveValue(cliente.email);
  expect(screen.getByLabelText('Contraseña')).toHaveValue('');
  expect(iniciarSesion).not.toHaveBeenCalled();
  expect(crear).not.toHaveBeenCalled();
});

it("muestra los errores de validación del servidor junto a los campos de registro correspondientes", async () => {
  vi.spyOn(api, 'registrar').mockRejectedValue(new ErrorApi('Revisa el correo.', 422, { email: 'Introduce otro correo válido.' }));
  renderizarAplicacion('/registro');
  await screen.findByRole('heading', { name: 'Crear cuenta' });
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: cliente.name } });
  fireEvent.change(screen.getByLabelText('Correo electrónico'), { target: { value: cliente.email } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
  fireEvent.click(screen.getByRole('button', { name: 'Crear mi cuenta' }));
  expect(await screen.findByText('Introduce otro correo válido.')).toBeInTheDocument();
  expect(screen.getByLabelText('Correo electrónico')).toHaveAttribute('aria-invalid', 'true');
});

it("conserva el equipo y las fechas sin hora durante el acceso y exige una confirmación aparte", async () => {
  vi.spyOn(api, 'obtenerEquipoPublico').mockResolvedValue(equipo);
  vi.spyOn(api, 'obtenerCalendarioDisponibilidadPublica').mockImplementation(async (id_equipo, intervalo) => ({ equipment_id: id_equipo, ...intervalo, occupied_ranges: [], can_book: true }));
  vi.spyOn(api, 'obtenerDisponibilidadPublica').mockResolvedValue({ equipment_id: 1, ...fechas, available: true, status: 'available' });
  vi.spyOn(api, 'iniciarSesion').mockResolvedValue(sesionCliente);
  const crear = vi.spyOn(api, 'crearMiReserva').mockResolvedValue({ id: 31, equipment_id: 1, ...fechas, status: 'confirmed' });
  renderizarAplicacion(destinoProducto);
  const reservar = await screen.findByRole('button', { name: 'Acceder para reservar' });
  await waitFor(() => expect(reservar).toBeEnabled());
  fireEvent.click(reservar);
  await screen.findByRole('heading', { name: 'Acceder a RentaLab' });
  expect(screen.getByTestId('location')).toHaveTextContent(`/acceso?next=${encodeURIComponent(destinoProducto)}`);
  fireEvent.change(screen.getByLabelText('Usuario'), { target: { value: cliente.email } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));
  expect(await screen.findByRole('heading', { name: equipo.name, level: 1 })).toBeInTheDocument();
  expect(screen.getByTestId('location')).toHaveTextContent(destinoProducto);
  const mostrarFecha = (valor: string) => valor.split('-').reverse().join('/');
  expect(screen.getByRole('button', { name: `Fecha de inicio: ${mostrarFecha(fechas.start_date)}` })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: `Fecha de devolución: ${mostrarFecha(fechas.end_date)}` })).toBeInTheDocument();
  expect(crear).not.toHaveBeenCalled();
  const confirmar = screen.getByRole('button', { name: 'Confirmar reserva' });
  await waitFor(() => expect(confirmar).toBeEnabled());
  fireEvent.click(confirmar);
  expect(await screen.findByRole('link', { name: 'Ver mi reserva' })).toHaveAttribute('href', '/mis-reservas/31');
  expect(crear).toHaveBeenCalledExactlyOnceWith({ equipment_id: 1, ...fechas }, expect.any(String));
});

it("conserva las fechas del equipo al alternar acceso y registro desde la cabecera", async () => {
  vi.spyOn(api, 'obtenerEquipoPublico').mockResolvedValue(equipo);
  vi.spyOn(api, 'obtenerCalendarioDisponibilidadPublica').mockImplementation(async (id_equipo, intervalo) => ({ equipment_id: id_equipo, ...intervalo, occupied_ranges: [], can_book: true }));
  vi.spyOn(api, 'obtenerDisponibilidadPublica').mockResolvedValue({ equipment_id: 1, ...fechas, available: true, status: 'available' });
  const crear = vi.spyOn(api, 'crearMiReserva');
  renderizarAplicacion(destinoProducto);
  const acceso = await screen.findByRole('link', { name: 'Acceder' });
  expect(acceso).toHaveAttribute('href', `/acceso?next=${encodeURIComponent(destinoProducto)}`);
  fireEvent.click(acceso);
  await screen.findByRole('heading', { name: 'Acceder a RentaLab' });
  const registro = within(screen.getByRole('banner')).getByRole('link', { name: 'Crear cuenta' });
  expect(registro).toHaveAttribute('href', `/registro?next=${encodeURIComponent(destinoProducto)}`);
  fireEvent.click(registro);
  await screen.findByRole('heading', { name: 'Crear cuenta' });
  const volverAcceso = screen.getByRole('link', { name: 'Acceder' });
  expect(volverAcceso).toHaveAttribute('href', `/acceso?next=${encodeURIComponent(destinoProducto)}`);
  fireEvent.click(volverAcceso);
  await screen.findByRole('heading', { name: 'Acceder a RentaLab' });
  expect(screen.getByTestId('location')).toHaveTextContent(`/acceso?next=${encodeURIComponent(destinoProducto)}`);
  expect(crear).not.toHaveBeenCalled();
});
