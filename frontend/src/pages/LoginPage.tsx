import { useEffect, useRef, useState, type FormEvent, type InputHTMLAttributes } from 'react';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import { Field, Notice } from '../components/ui';
import { useAuth } from '../auth/context';
import { useFormFeedback } from '../hooks/useFormFeedback';
import { allowedDestination, postLoginDestination } from '../auth/destinations';
import BrandMark from '../components/BrandMark';

function PasswordInput(props: InputHTMLAttributes<HTMLInputElement>) {
  const [visible, setVisible] = useState(false);
  return <div className="password-input">
    <input {...props} type={visible ? 'text' : 'password'} />
    <button className="password-toggle" type="button" aria-label={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'} aria-controls={props.id} aria-pressed={visible} onClick={() => setVisible(!visible)}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
        {visible ? <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></> : <><path d="M3 9s3 6 9 6 9-6 9-6M5 12l-2 3m6-1-1 4m7-4 1 4m3-6 2 3" /></>}
      </svg>
    </button>
  </div>;
}

export default function LoginPage() {
  const { login, session, checking, checkError, checkSession, expired } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const next = allowedDestination(search.get('next'));
  const registering = location.pathname === '/registro';
  const registered = typeof location.state === 'object' && location.state !== null && 'registered' in location.state && location.state.registered === true;
  const registeredEmail = typeof location.state === 'object' && location.state !== null && 'email' in location.state && typeof location.state.email === 'string' ? location.state.email : '';
  const [username, setUsername] = useState(registeredEmail);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const heading = useRef<HTMLHeadingElement>(null);
  const feedback = useFormFeedback();
  useEffect(() => {
    document.title = `RentaLab · ${registering ? 'Crear cuenta' : 'Acceso'}`;
    heading.current?.focus();
  }, [registering, checking, checkError]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (feedback.pending) return;
    feedback.clear();
    const errors: Record<string, string> = {};
    if (registering) {
      const emailControl = event.currentTarget.elements.namedItem('email');
      if (!name.trim()) errors.name = 'Introduce tu nombre.';
      if (!email.trim()) errors.email = 'Introduce tu correo electrónico.';
      else if (emailControl instanceof HTMLInputElement && emailControl.validity.typeMismatch) errors.email = 'Introduce un correo electrónico válido.';
      if (password.length < 8) errors.password = 'Usa al menos 8 caracteres para la contraseña.';
    } else {
      if (!username.trim()) errors.username = 'Introduce tu correo o usuario.';
      if (!password) errors.password = 'Introduce tu contraseña.';
    }
    if (Object.keys(errors).length) {
      feedback.setValidation(errors);
      feedback.setMessage('Revisa los campos indicados.');
      return;
    }
    feedback.setPending(true);
    try {
      if (registering) {
        const user = await api.register({ name: name.trim(), email: email.trim(), password });
        void navigate('/acceso' + (next ? `?next=${encodeURIComponent(next)}` : ''), { replace: true, state: { registered: true, email: user.email } });
      } else await login({ username, password });
      setPassword('');
    }
    catch (error) {
      if (registering && error instanceof ApiError && error.status === 409) {
        feedback.setValidation({ email: error.message });
        feedback.setMessage('Revisa el correo electrónico.');
      } else feedback.setFailure(error);
    }
    finally { feedback.setPending(false); }
  }

  if (checking) return <section className="auth-layout"><p role="status">Comprobando la sesión…</p></section>;
  if (checkError) return <section className="auth-layout"><div className="auth-card"><h1>Comprobar el acceso</h1><Notice tone="error">{checkError}</Notice><button className="button" onClick={() => { void checkSession(); }}>Volver a comprobar</button></div></section>;
  if (session) return <Navigate to={postLoginDestination(session.role, next)} replace />;

  return <section className="auth-layout">
    <div className="auth-card">
      <div className="brand auth-brand"><BrandMark /><span>RentaLab<span className="brand-subtitle">Alquiler audiovisual</span></span></div>
      <h1 ref={heading} tabIndex={-1}>{registering ? 'Crear cuenta' : 'Acceder a RentaLab'}</h1>
      <p className="text-muted">{registering ? 'Crea tu cuenta para reservar y consultar tu historial.' : 'Accede a tu cuenta para continuar.'}</p>
      {next?.startsWith('/equipos/') && <p className="auth-return-note">Conservamos tu equipo y las fechas. Al volver podrás revisar y confirmar la reserva.</p>}
      {expired && <Notice>La sesión ha caducado. Inicia sesión para continuar.</Notice>}
      {registered && <Notice tone="success">Cuenta creada. Ya puedes iniciar sesión.</Notice>}
      {feedback.message && <Notice tone="error" errors={feedback.errors}>{feedback.message}</Notice>}
      <form className="stack" noValidate onSubmit={(event) => { void submit(event); }} aria-busy={feedback.pending}>
        {registering ? <>
          <Field name="name" label="Nombre" error={feedback.errors.name}><input name="name" required maxLength={120} autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} /></Field>
          <Field name="email" label="Correo electrónico" error={feedback.errors.email}><input name="email" required type="email" maxLength={254} autoComplete="email" autoCapitalize="none" spellCheck={false} value={email} onChange={(event) => setEmail(event.target.value)} /></Field>
        </> : <Field name="username" label="Usuario" hint="Correo de tu cuenta o usuario administrador anterior." error={feedback.errors.username}><input name="username" required maxLength={254} autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} onChange={(event) => setUsername(event.target.value)} /></Field>}
        <Field name="password" label="Contraseña" hint={registering ? 'Usa al menos 8 caracteres.' : ''} error={feedback.errors.password}><PasswordInput name="password" required minLength={registering ? 8 : undefined} maxLength={1024} autoComplete={registering ? 'new-password' : 'current-password'} value={password} onChange={(event) => setPassword(event.target.value)} /></Field>
        <button className="button" type="submit" disabled={feedback.pending}>{registering ? feedback.pending ? 'Creando cuenta…' : 'Crear mi cuenta' : feedback.pending ? 'Accediendo…' : 'Iniciar sesión'}</button>
      </form>
      {!feedback.pending && <Link className="button button-secondary auth-switch" to={(registering ? '/acceso' : '/registro') + (next ? `?next=${encodeURIComponent(next)}` : '')}>{registering ? 'Ya tengo una cuenta' : 'Crear cuenta'}</Link>}
      <p className="auth-note">Proyecto demostrativo · Empresa y datos ficticios</p>
    </div>
  </section>;
}
