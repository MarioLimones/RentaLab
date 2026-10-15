import { Children, cloneElement, isValidElement, useEffect, useRef } from 'react';
import type { ReactNode } from 'react';

export function CabeceraPagina({ titulo, descripcion, accion }: { titulo: string; descripcion?: string; accion?: ReactNode }) {
  return <header className="page-header"><div><h1>{titulo}</h1>{descripcion && <p className="page-description">{descripcion}</p>}</div>{accion && <div className="page-actions">{accion}</div>}</header>;
}

const nombresCampos: Record<string, string> = { username: 'Usuario', email: 'Correo electrónico', password: 'Contraseña', code: 'Código', name: 'Nombre', category: 'Categoría', description: 'Descripción', equipment_id: 'Equipo', customer_name: 'Nombre del cliente', customer_email: 'Correo del cliente', start_date: 'Fecha de inicio', end_date: 'Fecha de fin', external_reference: 'Referencia externa', title: 'Título', priority: 'Prioridad', resolution: 'Resolución', file: 'Archivo CSV' };
Object.assign(nombresCampos, { public_description: 'Descripción pública', technical_specs: 'Características técnicas', image_url: 'Imagen', internal_notes: 'Notas internas', public_response: 'Respuesta visible al cliente', blocking: 'Bloqueo', customer: 'Cliente', customer_user_id: 'ID de cuenta', origin: 'Origen' });

export function Aviso({ children, tono = 'info', errores = {} }: { children: ReactNode; tono?: 'error' | 'success' | 'info' | 'warning'; errores?: Record<string, string> }) {
  const ref = useRef<HTMLDivElement>(null);
  const mensaje = Children.toArray(children).filter((hijo) => typeof hijo === 'string' || typeof hijo === 'number').join('');
  useEffect(() => { if (tono === 'error') ref.current?.focus(); }, [tono, mensaje]);
  return <div ref={ref} className={`notice notice-${tono}`} role={tono === 'error' ? 'alert' : tono === 'success' ? 'status' : undefined} tabIndex={tono === 'error' ? -1 : undefined}>{children}{Object.keys(errores).length > 0 && <ul className="error-links">{Object.entries(errores).map(([campo, error]) => <li key={campo}><a href={`#${campo}`}>{nombresCampos[campo] ?? (campo.startsWith('technical_specs-') ? 'Característica técnica' : 'Campo')}: {error}</a></li>)}</ul>}</div>;
}

export function EstadoVacio({ titulo, descripcion, accion }: { titulo: string; descripcion?: string; accion?: ReactNode }) {
  return <div className="empty-state"><span className="empty-mark" aria-hidden="true">—</span><h2>{titulo}</h2>{descripcion && <p>{descripcion}</p>}{accion}</div>;
}

const etiquetas: Record<string, string> = {
  active: 'Activo', inactive: 'Inactivo', confirmed: 'Confirmada', cancelled: 'Cancelada',
  open: 'Abierta', in_progress: 'En curso', resolved: 'Resuelta', low: 'Baja', medium: 'Media', high: 'Alta',
  blocking: 'Bloqueante', accepted: 'Aceptada', already_imported: 'Ya importada', rejected: 'Rechazada',
};
export function EtiquetaEstado({ clase }: { clase: string }) {
  return <span className={`badge badge-${clase}`}><span aria-hidden="true" className="badge-dot" />{etiquetas[clase] ?? clase}</span>;
}

interface ControlCampo { id?: string | undefined; 'aria-describedby'?: string | undefined; 'aria-invalid'?: boolean; }
export function Campo({ nombre, etiqueta, ayuda, error, children }: { nombre: string; etiqueta: string; ayuda?: string; error?: string | undefined; children: ReactNode }) {
  const descritoPor = [ayuda && `${nombre}-hint`, error && `${nombre}-error`].filter(Boolean).join(' ') || undefined;
  return <div className="field"><label htmlFor={nombre}>{etiqueta}</label>{Children.map(children, (hijo) => isValidElement<ControlCampo>(hijo) ? cloneElement(hijo, { id: nombre, 'aria-describedby': descritoPor, 'aria-invalid': !!error }) : hijo)}{ayuda && <p className="field-hint" id={`${nombre}-hint`}>{ayuda}</p>}{error && <p className="field-error" id={`${nombre}-error`}>{error}</p>}</div>;
}
