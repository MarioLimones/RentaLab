import { Children, cloneElement, isValidElement, useEffect, useRef } from 'react';
import type { ReactNode } from 'react';

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <header className="page-header"><div><h1>{title}</h1>{description && <p className="page-description">{description}</p>}</div>{action && <div className="page-actions">{action}</div>}</header>;
}

const fieldNames: Record<string, string> = { username: 'Usuario', email: 'Correo electrónico', password: 'Contraseña', code: 'Código', name: 'Nombre', category: 'Categoría', description: 'Descripción', equipment_id: 'Equipo', customer_name: 'Nombre del cliente', customer_email: 'Correo del cliente', start_date: 'Fecha de inicio', end_date: 'Fecha de fin', external_reference: 'Referencia externa', title: 'Título', priority: 'Prioridad', resolution: 'Resolución', file: 'Archivo CSV' };
Object.assign(fieldNames, { public_description: 'Descripción pública', technical_specs: 'Características técnicas', image_url: 'Imagen', internal_notes: 'Notas internas', public_response: 'Respuesta visible al cliente', blocking: 'Bloqueo', customer: 'Cliente', customer_user_id: 'ID de cuenta', origin: 'Origen' });

export function Notice({ children, tone = 'info', errors = {} }: { children: ReactNode; tone?: 'error' | 'success' | 'info' | 'warning'; errors?: Record<string, string> }) {
  const ref = useRef<HTMLDivElement>(null);
  const message = Children.toArray(children).filter((child) => typeof child === 'string' || typeof child === 'number').join('');
  useEffect(() => { if (tone === 'error') ref.current?.focus(); }, [tone, message]);
  return <div ref={ref} className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : tone === 'success' ? 'status' : undefined} tabIndex={tone === 'error' ? -1 : undefined}>{children}{Object.keys(errors).length > 0 && <ul className="error-links">{Object.entries(errors).map(([field, error]) => <li key={field}><a href={`#${field}`}>{fieldNames[field] ?? (field.startsWith('technical_specs-') ? 'Característica técnica' : 'Campo')}: {error}</a></li>)}</ul>}</div>;
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-mark" aria-hidden="true">—</span><h2>{title}</h2>{description && <p>{description}</p>}{action}</div>;
}

const labels: Record<string, string> = {
  active: 'Activo', inactive: 'Inactivo', confirmed: 'Confirmada', cancelled: 'Cancelada',
  open: 'Abierta', in_progress: 'En curso', resolved: 'Resuelta', low: 'Baja', medium: 'Media', high: 'Alta',
  blocking: 'Bloqueante', accepted: 'Aceptada', already_imported: 'Ya importada', rejected: 'Rechazada',
};
export function StatusBadge({ kind }: { kind: string }) {
  return <span className={`badge badge-${kind}`}><span aria-hidden="true" className="badge-dot" />{labels[kind] ?? kind}</span>;
}

interface FieldControl { id?: string | undefined; 'aria-describedby'?: string | undefined; 'aria-invalid'?: boolean; }
export function Field({ name, label, hint, error, children }: { name: string; label: string; hint?: string; error?: string | undefined; children: ReactNode }) {
  const describedBy = [hint && `${name}-hint`, error && `${name}-error`].filter(Boolean).join(' ') || undefined;
  return <div className="field"><label htmlFor={name}>{label}</label>{Children.map(children, (child) => isValidElement<FieldControl>(child) ? cloneElement(child, { id: name, 'aria-describedby': describedBy, 'aria-invalid': !!error }) : child)}{hint && <p className="field-hint" id={`${name}-hint`}>{hint}</p>}{error && <p className="field-error" id={`${name}-error`}>{error}</p>}</div>;
}
