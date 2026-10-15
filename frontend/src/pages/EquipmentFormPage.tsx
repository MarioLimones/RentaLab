import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, type Equipment, type EquipmentInput } from '../api/client';
import { Field, Notice, PageHeader } from '../components/ui';
import { useFormFeedback } from '../hooks/useFormFeedback';
import { useIsMounted } from '../hooks/useIsMounted';
import { useResource } from '../hooks/useResource';

const emptyEquipment: EquipmentInput = { code: '', name: '', category: '', description: '', public_description: '', technical_specs: {}, image_url: null, active: true };

interface TechnicalSpecRow { id: number; name: string; value: string; }

function validImageUrl(value: string): boolean {
  if ([...value].some((character) => character === '\\' || character.charCodeAt(0) <= 32 || character.charCodeAt(0) === 127)) return false;
  if (value.startsWith('/api/public/images/')) return /^\/api\/public\/images\/[A-Za-z0-9_-][A-Za-z0-9_.-]*(?:\/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*$/.test(value);
  if (!/^https:\/\//i.test(value)) return false;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && Boolean(url.hostname) && !url.username && !url.password && !url.search && !url.hash;
  } catch { return false; }
}

function EquipmentEditor({ initial, equipmentId }: { initial: EquipmentInput; equipmentId?: number }) {
  const [values, setValues] = useState<EquipmentInput>(initial);
  const [specs, setSpecs] = useState<TechnicalSpecRow[]>(() => Object.entries(initial.technical_specs ?? {}).map(([name, value], id) => ({ id, name, value })));
  const nextSpecId = useRef(specs.length);
  const focusTarget = useRef<string | null>(null);
  const submitting = useRef(false);
  const navigate = useNavigate();
  const isMounted = useIsMounted();
  const feedback = useFormFeedback();
  const editing = equipmentId !== undefined;

  useEffect(() => {
    if (focusTarget.current) {
      document.getElementById(focusTarget.current)?.focus();
      focusTarget.current = null;
    }
  }, [specs]);

  function addSpec() {
    if (specs.length >= 20 || feedback.pending) return;
    const id = nextSpecId.current++;
    focusTarget.current = `technical_specs-${id}-name`;
    setSpecs([...specs, { id, name: '', value: '' }]);
  }

  function removeSpec(id: number) {
    const index = specs.findIndex((spec) => spec.id === id);
    const next = specs[index + 1] ?? specs[index - 1];
    focusTarget.current = next ? `technical_specs-${next.id}-name` : 'add-technical-spec';
    setSpecs(specs.filter((spec) => spec.id !== id));
    feedback.clear();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    feedback.clear();
    const errors: Record<string, string> = {};
    if (!values.code.trim()) errors.code = 'Introduce el código de la unidad.';
    if (!values.name.trim()) errors.name = 'Introduce el nombre del equipo.';
    if (!values.category.trim()) errors.category = 'Introduce una categoría.';
    const names = new Set<string>();
    for (const spec of specs) {
      const name = spec.name.trim();
      if (!name) errors[`technical_specs-${spec.id}-name`] = 'Introduce el nombre o elimina esta característica.';
      else if (names.has(name)) errors[`technical_specs-${spec.id}-name`] = 'Cada característica debe tener un nombre diferente.';
      else names.add(name);
      if (!spec.value.trim()) errors[`technical_specs-${spec.id}-value`] = 'Introduce el valor de esta característica.';
    }
    const imageUrl = values.image_url?.trim() ?? '';
    if (imageUrl && !validImageUrl(imageUrl)) errors.image_url = 'Usa una URL HTTPS sin credenciales, consulta ni fragmento, o una ruta /api/public/images/... válida.';
    if (Object.keys(errors).length > 0) {
      feedback.setValidation(errors);
      return;
    }
    submitting.current = true;
    feedback.setPending(true);
    try {
      const input: EquipmentInput = { ...values, public_description: values.public_description ?? '', technical_specs: Object.fromEntries(specs.map((spec) => [spec.name.trim(), spec.value.trim()])), image_url: imageUrl || null };
      const saved = editing ? await api.patchEquipment(equipmentId, input) : await api.createEquipment(input);
      if (!isMounted()) return;
      navigate(`/admin/equipos/${saved.id}`, { state: { notice: editing ? 'Equipo actualizado correctamente.' : 'Equipo creado correctamente.' } });
    } catch (failure) {
      if (isMounted()) feedback.setFailure(failure);
    } finally {
      submitting.current = false;
      if (isMounted()) feedback.setPending(false);
    }
  }

  return <>
    <Link className="back-link" to={editing ? `/admin/equipos/${equipmentId}` : '/admin/equipos'}>← {editing ? 'Volver al equipo' : 'Volver a equipos'}</Link>
    <PageHeader title={editing ? 'Editar equipo' : 'Crear equipo'} description="Registra una unidad física. El servidor normaliza su código y comprueba que sea único." />
    {feedback.message && <Notice tone="error" errors={feedback.errors}>{feedback.message}</Notice>}
    <form className="panel" onSubmit={(event) => { void submit(event); }} noValidate aria-busy={feedback.pending}>
      <div className="form-grid">
        <fieldset className="full-width" disabled={feedback.pending}><legend>Datos de gestión</legend><div className="form-grid">
        <Field name="code" label="Código" error={feedback.errors.code} hint="Único por unidad. Letras, números, guion o guion bajo; hasta 40 caracteres.">
          <input id="code" name="code" required maxLength={40} autoComplete="off" value={values.code} onChange={(event) => setValues({ ...values, code: event.target.value })} aria-invalid={Boolean(feedback.errors.code)} />
        </Field>
        <Field name="name" label="Nombre" error={feedback.errors.name}><input id="name" name="name" required maxLength={120} value={values.name} onChange={(event) => setValues({ ...values, name: event.target.value })} aria-invalid={Boolean(feedback.errors.name)} /></Field>
        <Field name="category" label="Categoría" error={feedback.errors.category}><input id="category" name="category" required maxLength={80} placeholder="Por ejemplo, Cámaras" value={values.category} onChange={(event) => setValues({ ...values, category: event.target.value })} aria-invalid={Boolean(feedback.errors.category)} /></Field>
        <Field name="description" label="Descripción interna (opcional)" error={feedback.errors.description} hint="Solo administración. Hasta 2000 caracteres."><textarea id="description" name="description" rows={4} maxLength={2000} value={values.description} onChange={(event) => setValues({ ...values, description: event.target.value })} aria-invalid={Boolean(feedback.errors.description)} /></Field>
        </div></fieldset>
        <fieldset className="full-width" disabled={feedback.pending}><legend>Ficha pública del catálogo</legend><div className="form-grid">
          <Field name="public_description" label="Descripción pública (opcional)" error={feedback.errors.public_description} hint="Visible para visitantes y clientes. Hasta 2000 caracteres."><textarea name="public_description" rows={4} maxLength={2000} value={values.public_description ?? ''} onChange={(event) => setValues({ ...values, public_description: event.target.value })} /></Field>
          <Field name="image_url" label="Imagen (opcional)" error={feedback.errors.image_url} hint="URL HTTPS o ruta /api/public/images/... sin consulta ni fragmento. Al dejarla vacía se muestra la alternativa local."><input name="image_url" type="text" inputMode="url" maxLength={2048} autoComplete="off" value={values.image_url ?? ''} onChange={(event) => setValues({ ...values, image_url: event.target.value })} /></Field>
          <fieldset id="technical_specs" tabIndex={-1} className="full-width" aria-describedby={`technical-specs-hint${feedback.errors.technical_specs ? ' technical_specs-error' : ''}`}><legend>Características técnicas</legend>
            <p className="field-hint" id="technical-specs-hint">Hasta 20 características. Nombre único de hasta 80 caracteres y valor de hasta 300. No incluyas notas internas.</p>
            {feedback.errors.technical_specs && <p className="field-error" id="technical_specs-error">{feedback.errors.technical_specs}</p>}
            <div className="detail-grid">{specs.map((spec, index) => <fieldset key={spec.id}><legend>Característica {index + 1}</legend><div className="form-grid">
              <Field name={`technical_specs-${spec.id}-name`} label={`Nombre de característica ${index + 1}`} error={feedback.errors[`technical_specs-${spec.id}-name`]}><input required maxLength={80} value={spec.name} onChange={(event) => setSpecs(specs.map((row) => row.id === spec.id ? { ...row, name: event.target.value } : row))} /></Field>
              <Field name={`technical_specs-${spec.id}-value`} label={`Valor de característica ${index + 1}`} error={feedback.errors[`technical_specs-${spec.id}-value`]}><input required maxLength={300} value={spec.value} onChange={(event) => setSpecs(specs.map((row) => row.id === spec.id ? { ...row, value: event.target.value } : row))} /></Field>
              <div className="full-width"><button className="button button-secondary" type="button" onClick={() => removeSpec(spec.id)} aria-label={`Eliminar característica ${index + 1}`}>Eliminar característica</button></div>
            </div></fieldset>)}</div>
            <div className="form-actions"><button id="add-technical-spec" className="button button-secondary" type="button" disabled={specs.length >= 20} onClick={addSpec}>Añadir característica</button><span className="text-muted" role="status">{specs.length} de 20 características</span></div>
          </fieldset>
        </div></fieldset>
      </div>
      <label className="checkbox-label"><input type="checkbox" disabled={feedback.pending} checked={values.active} onChange={(event) => setValues({ ...values, active: event.target.checked })} />Equipo activo para nuevas reservas y catálogo público</label>
      <div className="form-actions"><button className="button" type="submit" disabled={feedback.pending}>{feedback.pending ? 'Guardando…' : editing ? 'Guardar cambios' : 'Crear equipo'}</button><Link className="button button-secondary" to={editing ? `/admin/equipos/${equipmentId}` : '/admin/equipos'}>Cancelar</Link></div>
    </form>
  </>;
}

function ExistingEquipmentEditor({ equipmentId }: { equipmentId: number }) {
  const load = useCallback(() => api.getEquipment(equipmentId), [equipmentId]);
  const { data, loading, error, reload } = useResource<Equipment>(load);
  if (loading) return <p role="status">Cargando equipo…</p>;
  if (error) return <><PageHeader title="Editar equipo" /><Notice tone="error">{error} <button type="button" className="button button-secondary" onClick={reload}>Volver a cargar</button></Notice><Link to="/admin/equipos">Volver a equipos</Link></>;
  if (!data) return null;
  const { code, name, category, description, public_description, technical_specs, image_url, active } = data;
  return <EquipmentEditor key={data.id} equipmentId={data.id} initial={{ code, name, category, description, public_description: public_description ?? '', technical_specs: technical_specs ?? {}, image_url: image_url ?? null, active }} />;
}

export function EquipmentFormPage() {
  const { id } = useParams();
  if (id === undefined) return <EquipmentEditor initial={emptyEquipment} />;
  const equipmentId = Number(id);
  if (!Number.isSafeInteger(equipmentId) || equipmentId <= 0) return <><PageHeader title="Equipo no válido" /><Notice tone="error">El identificador del equipo no es válido.</Notice><Link to="/admin/equipos">Volver a equipos</Link></>;
  return <ExistingEquipmentEditor key={equipmentId} equipmentId={equipmentId} />;
}
