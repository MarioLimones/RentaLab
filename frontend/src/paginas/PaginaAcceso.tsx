import { useEffect, useRef, useState, type FormEvent, type InputHTMLAttributes } from 'react';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { api, ErrorApi } from '../api/cliente';
import { Campo, Aviso } from '../componentes/interfaz';
import { useAutenticacion } from '../autenticacion/contexto';
import { useRetroalimentacionFormulario } from '../hooks/useRetroalimentacionFormulario';
import { destinoPermitido, destinoTrasAcceso } from '../autenticacion/destinos';
import MarcaIdentidad from '../componentes/Marca';

function EntradaContrasena(propiedades: InputHTMLAttributes<HTMLInputElement>) {
  const [visible, establecerVisible] = useState(false);
  return <div className="password-input">
    <input {...propiedades} type={visible ? 'text' : 'password'} />
    <button className="password-toggle" type="button" aria-label={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'} aria-controls={propiedades.id} aria-pressed={visible} onClick={() => establecerVisible(!visible)}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
        {visible ? <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></> : <><path d="M3 9s3 6 9 6 9-6 9-6M5 12l-2 3m6-1-1 4m7-4 1 4m3-6 2 3" /></>}
      </svg>
    </button>
  </div>;
}

export default function PaginaAcceso() {
  const { iniciarSesion, sesion, comprobando, errorComprobacion, comprobarSesion, caducado } = useAutenticacion();
  const ubicacion = useLocation();
  const navegar = useNavigate();
  const [busqueda] = useSearchParams();
  const siguiente = destinoPermitido(busqueda.get('next'));
  const registrando = ubicacion.pathname === '/registro';
  const registrado = typeof ubicacion.state === 'object' && ubicacion.state !== null && 'registered' in ubicacion.state && ubicacion.state.registered === true;
  const correoRegistrado = typeof ubicacion.state === 'object' && ubicacion.state !== null && 'email' in ubicacion.state && typeof ubicacion.state.email === 'string' ? ubicacion.state.email : '';
  const [nombreUsuario, establecerNombreUsuario] = useState(correoRegistrado);
  const [nombre, establecerNombre] = useState('');
  const [correo, establecerCorreo] = useState('');
  const [contrasena, establecerContrasena] = useState('');
  const encabezado = useRef<HTMLHeadingElement>(null);
  const retroalimentacionFormulario = useRetroalimentacionFormulario();
  useEffect(() => {
    document.title = `RentaLab · ${registrando ? 'Crear cuenta' : 'Acceso'}`;
    encabezado.current?.focus();
  }, [registrando, comprobando, errorComprobacion]);

  async function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (retroalimentacionFormulario.pendiente) return;
    retroalimentacionFormulario.limpiar();
    const errores: Record<string, string> = {};
    if (registrando) {
      const controlCorreo = evento.currentTarget.elements.namedItem('email');
      if (!nombre.trim()) errores.name = 'Introduce tu nombre.';
      if (!correo.trim()) errores.email = 'Introduce tu correo electrónico.';
      else if (controlCorreo instanceof HTMLInputElement && controlCorreo.validity.typeMismatch) errores.email = 'Introduce un correo electrónico válido.';
      if (contrasena.length < 8) errores.password = 'Usa al menos 8 caracteres para la contraseña.';
    } else {
      if (!nombreUsuario.trim()) errores.username = 'Introduce tu correo o usuario.';
      if (!contrasena) errores.password = 'Introduce tu contraseña.';
    }
    if (Object.keys(errores).length) {
      retroalimentacionFormulario.establecerValidacion(errores);
      retroalimentacionFormulario.establecerMensaje('Revisa los campos indicados.');
      return;
    }
    retroalimentacionFormulario.establecerPendiente(true);
    try {
      if (registrando) {
        const usuario = await api.registrar({ name: nombre.trim(), email: correo.trim(), password: contrasena });
        void navegar('/acceso' + (siguiente ? `?next=${encodeURIComponent(siguiente)}` : ''), { replace: true, state: { registered: true, email: usuario.email } });
      } else await iniciarSesion({ username: nombreUsuario, password: contrasena });
      establecerContrasena('');
    }
    catch (error) {
      if (registrando && error instanceof ErrorApi && error.estado === 409) {
        retroalimentacionFormulario.establecerValidacion({ email: error.message });
        retroalimentacionFormulario.establecerMensaje('Revisa el correo electrónico.');
      } else retroalimentacionFormulario.establecerFallo(error);
    }
    finally { retroalimentacionFormulario.establecerPendiente(false); }
  }

  if (comprobando) return <section className="auth-layout"><p role="status">Comprobando la sesión…</p></section>;
  if (errorComprobacion) return <section className="auth-layout"><div className="auth-card"><h1>Comprobar el acceso</h1><Aviso tono="error">{errorComprobacion}</Aviso><button className="button" onClick={() => { void comprobarSesion(); }}>Volver a comprobar</button></div></section>;
  if (sesion) return <Navigate to={destinoTrasAcceso(sesion.role, siguiente)} replace />;

  return <section className="auth-layout">
    <div className="auth-card">
      <div className="brand auth-brand"><MarcaIdentidad /><span>RentaLab<span className="brand-subtitle">Alquiler audiovisual</span></span></div>
      <h1 ref={encabezado} tabIndex={-1}>{registrando ? 'Crear cuenta' : 'Acceder a RentaLab'}</h1>
      <p className="text-muted">{registrando ? 'Crea tu cuenta para reservar y consultar tu historial.' : 'Accede a tu cuenta para continuar.'}</p>
      {siguiente?.startsWith('/equipos/') && <p className="auth-return-note">Conservamos tu equipo y las fechas. Al volver podrás revisar y confirmar la reserva.</p>}
      {caducado && <Aviso>La sesión ha caducado. Inicia sesión para continuar.</Aviso>}
      {registrado && <Aviso tono="success">Cuenta creada. Ya puedes iniciar sesión.</Aviso>}
      {retroalimentacionFormulario.mensaje && <Aviso tono="error" errores={retroalimentacionFormulario.errores}>{retroalimentacionFormulario.mensaje}</Aviso>}
      <form className="stack" noValidate onSubmit={(evento) => { void enviar(evento); }} aria-busy={retroalimentacionFormulario.pendiente}>
        {registrando ? <>
          <Campo nombre="name" etiqueta="Nombre" error={retroalimentacionFormulario.errores.name}><input name="name" required maxLength={120} autoComplete="name" value={nombre} onChange={(evento) => establecerNombre(evento.target.value)} /></Campo>
          <Campo nombre="email" etiqueta="Correo electrónico" error={retroalimentacionFormulario.errores.email}><input name="email" required type="email" maxLength={254} autoComplete="email" autoCapitalize="none" spellCheck={false} value={correo} onChange={(evento) => establecerCorreo(evento.target.value)} /></Campo>
        </> : <Campo nombre="username" etiqueta="Usuario" ayuda="Correo de tu cuenta o usuario administrador anterior." error={retroalimentacionFormulario.errores.username}><input name="username" required maxLength={254} autoComplete="username" autoCapitalize="none" spellCheck={false} value={nombreUsuario} onChange={(evento) => establecerNombreUsuario(evento.target.value)} /></Campo>}
        <Campo nombre="password" etiqueta="Contraseña" ayuda={registrando ? 'Usa al menos 8 caracteres.' : ''} error={retroalimentacionFormulario.errores.password}><EntradaContrasena name="password" required minLength={registrando ? 8 : undefined} maxLength={1024} autoComplete={registrando ? 'new-password' : 'current-password'} value={contrasena} onChange={(evento) => establecerContrasena(evento.target.value)} /></Campo>
        <button className="button" type="submit" disabled={retroalimentacionFormulario.pendiente}>{registrando ? retroalimentacionFormulario.pendiente ? 'Creando cuenta…' : 'Crear mi cuenta' : retroalimentacionFormulario.pendiente ? 'Accediendo…' : 'Iniciar sesión'}</button>
      </form>
      {!retroalimentacionFormulario.pendiente && <Link className="button button-secondary auth-switch" to={(registrando ? '/acceso' : '/registro') + (siguiente ? `?next=${encodeURIComponent(siguiente)}` : '')}>{registrando ? 'Ya tengo una cuenta' : 'Crear cuenta'}</Link>}
      <p className="auth-note">Proyecto demostrativo · Empresa y datos ficticios</p>
    </div>
  </section>;
}
