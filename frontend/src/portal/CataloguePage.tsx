import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigationType, useSearchParams } from 'react-router-dom';
import { api, type PublicAvailability, type PublicEquipment } from '../api/client';
import { EmptyState, Field, Notice } from '../components/ui';
import { formatDate } from '../lib/dates';
import { CatalogueDatePicker } from './CatalogueDatePicker';
import { CatalogueReservations } from './CatalogueReservations';
import { completeDateRange, dateRangeErrors, todayInMadrid } from './dateRange';
import { catalogueProductPath, catalogueScrollTarget, rememberCataloguePosition } from './catalogueNavigation';
import { ProductImage } from './ProductImage';
import { SaveProductButton } from './SaveProductButton';
import './catalogue.css';

interface CatalogueResult {
  key: string;
  equipment: PublicEquipment[];
  availability: Record<number, PublicAvailability>;
  loading: boolean;
  error: string | null;
  range: { start_date: string; end_date: string };
  availableOnly: boolean;
}

function catalogueFilters(search: URLSearchParams) {
  return {
    q: search.get('q') ?? '', category: search.get('category') ?? '',
    start_date: search.get('start_date') ?? '', end_date: search.get('end_date') ?? '',
    available: search.get('available') === '1' ? '1' : '',
  };
}

export function CataloguePage() {
  const [search, setSearch] = useSearchParams();
  const location = useLocation();
  const navigationType = useNavigationType();
  const restoredLocation = useRef<string | null>(null);
  const [allEquipment, setAllEquipment] = useState<PublicEquipment[]>([]);
  const [result, setResult] = useState<CatalogueResult>({ key: '', equipment: [], availability: {}, loading: true, error: null, range: { start_date: '', end_date: '' }, availableOnly: false });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [retry, setRetry] = useState(0);
  const [today, setToday] = useState(todayInMadrid);
  const searchKey = search.toString();
  const [form, setForm] = useState(() => ({ source: searchKey, values: catalogueFilters(search), liveTarget: null as string | null }));
  const [composing, setComposing] = useState(false);
  const resultsRegion = useRef<HTMLElement>(null);
  // Live search preserves other drafts; browser navigation restores applied filters.
  if (form.source !== searchKey) {
    const liveSearch = form.liveTarget === searchKey;
    setForm({ source: searchKey, values: liveSearch ? form.values : catalogueFilters(search), liveTarget: null });
    if (!liveSearch) setErrors({});
  }
  const draft = form.values;
  const draftRange = { start_date: draft.start_date, end_date: draft.end_date };
  const validDraftRange = completeDateRange(draftRange);
  const query = search.get('q') ?? '';
  const category = search.get('category') ?? '';
  const range = { start_date: search.get('start_date') ?? '', end_date: search.get('end_date') ?? '' };
  const validRange = completeDateRange(range);
  const availableOnly = search.get('available') === '1';
  const key = JSON.stringify([query, category, range.start_date, range.end_date, availableOnly, retry, today]);

  useEffect(() => {
    const refreshDay = () => setToday(todayInMadrid());
    const timer = window.setInterval(refreshDay, 60_000);
    window.addEventListener('focus', refreshDay);
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refreshDay); };
  }, []);

  useEffect(() => {
    if (composing || draft.q === query) return;
    const timer = window.setTimeout(() => {
      const next = new URLSearchParams(search);
      if (draft.q) next.set('q', draft.q); else next.delete('q');
      setForm((previous) => ({ ...previous, liveTarget: next.toString() }));
      setSearch(next, { replace: true });
    }, 150);
    return () => window.clearTimeout(timer);
  }, [draft.q, query, composing, search, setSearch]);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    void api.listPublicEquipment({}, controller.signal).then((equipment) => { if (current) setAllEquipment(equipment); }, () => { /* The filtered request below provides a recoverable error. */ });
    return () => { current = false; controller.abort(); };
  }, [retry]);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    const dates = { start_date: range.start_date, end_date: range.end_date };
    const tomorrow = new Date(`${today}T12:00:00Z`);
    tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
    const availabilityDates = validRange ? dates : { start_date: today, end_date: tomorrow.toISOString().slice(0, 10) };
    void Promise.resolve().then(async () => {
      if (!current) return;
      setResult((previous) => ({ ...previous, loading: true, error: null }));
      const equipment = await api.listPublicEquipment({ q: query, category }, controller.signal);
      const availability: Record<number, PublicAvailability> = {};
      await Promise.all(equipment.map(async (item) => { availability[item.id] = await api.getPublicAvailability(item.id, availabilityDates, controller.signal); }));
      if (current) setResult({ key, equipment, availability, loading: false, error: null, range: dates, availableOnly });
    }).catch((failure: unknown) => {
      if (current) setResult({ key, equipment: [], availability: {}, loading: false, error: failure instanceof Error ? failure.message : 'No se pudo cargar el catálogo.', range: dates, availableOnly });
    });
    return () => { current = false; controller.abort(); };
  }, [query, category, range.start_date, range.end_date, validRange, availableOnly, key, today]);

  function preserveResultsHeight() {
    const region = resultsRegion.current;
    if (region) region.style.minHeight = `${region.getBoundingClientRect().height}px`;
  }

  function update(name: keyof typeof draft, value: string) {
    preserveResultsHeight();
    setErrors({});
    setForm((previous) => ({ ...previous, values: {
      ...previous.values, [name]: value,
    } }));
  }

  function toggleAvailable(checked: boolean) {
    preserveResultsHeight();
    const next = new URLSearchParams(search);
    if (checked) next.set('available', '1'); else next.delete('available');
    setForm((previous) => ({ ...previous, values: { ...previous.values, available: checked ? '1' : '' }, liveTarget: next.toString() }));
    setSearch(next);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (composing) return;
    preserveResultsHeight();
    const validation = dateRangeErrors(draftRange);
    setErrors(validation);
    if (Object.keys(validation).length > 0) return;
    const next = new URLSearchParams(search);
    for (const [name, value] of Object.entries(draft)) {
      if (value) next.set(name, value);
      else next.delete(name);
    }
    if (next.toString() === searchKey) setRetry((value) => value + 1);
    else setSearch(next);
  }

  function clearFilters() {
    preserveResultsHeight();
    setForm({ source: searchKey, values: catalogueFilters(new URLSearchParams()), liveTarget: null });
    setErrors({});
    if (!searchKey) setRetry((value) => value + 1);
    else setSearch({});
  }

  const categories = [...new Set([...allEquipment.map((item) => item.category), ...(draft.category ? [draft.category] : [])])].sort((a, b) => a.localeCompare(b, 'es'));
  const currentResult = result.key === key;
  const loading = !currentResult || result.loading || draft.q !== query;
  const initialLoading = !result.key && loading;
  const displayedRange = result.key ? result.range : range;
  const equipment = result.availableOnly ? result.equipment.filter((item) => result.availability[item.id]?.available === true) : result.equipment;
  const cataloguePath = `/catalogo${searchKey ? `?${searchKey}` : ''}`;

  useEffect(() => {
    if (loading || result.error || restoredLocation.current === location.key) return;
    const top = catalogueScrollTarget(cataloguePath, location.state, navigationType === 'POP');
    if (top === null) return;
    const frame = window.requestAnimationFrame(() => {
      window.scrollTo({ top, left: 0, behavior: 'instant' });
      restoredLocation.current = location.key;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [loading, result.error, cataloguePath, location.key, location.state, navigationType]);

  return <>
    <header className="catalogue-intro">
      <div><h1>El equipo para tu próxima idea.</h1><p>Cámaras, sonido e iluminación para tus proyectos. Elige tus fechas y encuentra el equipo que necesitas.</p></div>
      <div className="catalogue-intro-note"><strong>Alquiler por días</strong><span>Consulta las características y reserva desde tu cuenta.</span></div>
    </header>
    <form className="catalogue-filters" onSubmit={submit} noValidate aria-label="Buscar en el catálogo">
      <div className="catalogue-search-row">
        <Field name="catalogue-search" label="Buscar equipo"><input id="catalogue-search" type="search" name="q" placeholder="Cámara, micrófono…" maxLength={120} value={draft.q} onChange={(event) => update('q', event.target.value)} onCompositionStart={() => setComposing(true)} onCompositionEnd={() => setComposing(false)} /></Field>
        <Field name="catalogue-category" label="Categoría"><select id="catalogue-category" name="category" value={draft.category} onChange={(event) => update('category', event.target.value)}><option value="">Todas las categorías</option>{categories.map((item) => <option key={item} value={item}>{item}</option>)}</select></Field>
      </div>
      <div className="catalogue-dates-row">
        <CatalogueDatePicker value={draftRange} onChange={(dates) => {
          preserveResultsHeight();
          setErrors({});
          setForm((previous) => ({ ...previous, values: { ...previous.values, ...dates } }));
        }} errors={errors} />
        <div className="catalogue-filter-actions">
          <label className="catalogue-checkbox"><input type="checkbox" checked={draft.available === '1'} onChange={(event) => toggleAvailable(event.target.checked)} />Solo disponibles</label>
          <button type="submit" className="button">Consultar catálogo</button>
        </div>
      </div>
      <p className="catalogue-help">La búsqueda y el filtro Solo disponibles se actualizan automáticamente. Aplica categoría y fechas con Consultar catálogo.</p>
      {!validDraftRange && <p className="catalogue-help" id="catalogue-date-help">Sin fechas aplicadas, Solo disponibles muestra los equipos disponibles hoy.</p>}
      {Object.keys(errors).length > 0 && <Notice tone="error" errors={errors}>Revisa las fechas para consultar disponibilidad.</Notice>}
    </form>
    <section id="catalogue-results" ref={resultsRegion} aria-labelledby="catalogue-results-title" aria-busy={loading}>
      <div className="catalogue-results-header"><h2 id="catalogue-results-title">Explora el catálogo</h2><span className="catalogue-results-status" role="status">{loading ? 'Actualizando…' : !result.error ? `${equipment.length} ${equipment.length === 1 ? 'equipo' : 'equipos'}` : ''}</span></div>
      {completeDateRange(displayedRange) && <p className="catalogue-range">Disponibilidad del {formatDate(displayedRange.start_date)} al {formatDate(displayedRange.end_date)}. El día de devolución no se incluye.</p>}
      {initialLoading ? <p className="catalogue-loading">Cargando equipos{validRange ? ' y disponibilidad' : ''}…</p> : result.error ? <div className="notice notice-error" role="alert">{result.error} <button type="button" className="button button-secondary" onClick={() => setRetry((value) => value + 1)}>Volver a cargar</button></div> : equipment.length === 0 ? <EmptyState title="No encontramos equipos para esta búsqueda" description="Prueba otra palabra, categoría o rango de fechas." action={<button className="button button-secondary" type="button" onClick={clearFilters}>Ver todo el catálogo</button>} /> : <ul className="catalogue-grid">{equipment.map((item) => {
        const availability = currentResult ? result.availability[item.id] : undefined;
        const forToday = !completeDateRange(displayedRange);
        const availabilityLabel = availability?.available === true
          ? forToday ? 'Disponible hoy' : 'Disponible para tus fechas'
          : availability?.available === false ? forToday ? 'No disponible hoy' : 'No disponible para tus fechas'
          : 'Consultando disponibilidad…';
        return <li key={item.id} className="catalogue-card">
          <Link className="catalogue-card-image-link" to={catalogueProductPath(item.id, displayedRange, cataloguePath)} state={{ catalogueReturn: cataloguePath }} onClick={() => rememberCataloguePosition(cataloguePath)} aria-label={`Ver ${item.name}`}><ProductImage equipment={item} /></Link>
          <div className="catalogue-card-body"><p className="catalogue-category">{item.category}</p><h3><Link to={catalogueProductPath(item.id, displayedRange, cataloguePath)} state={{ catalogueReturn: cataloguePath }} onClick={() => rememberCataloguePosition(cataloguePath)}>{item.name}</Link></h3>
            <p className={`catalogue-availability catalogue-card-availability${availability?.available === true ? ' is-available' : availability?.available === false ? ' is-unavailable' : ''}`}>
              {availability?.available != null && <svg aria-hidden="true" viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="10" cy="10" r="7.5" />{availability.available ? <path d="m6.5 10 2.3 2.3 4.7-4.6" /> : <path d="m7.5 7.5 5 5m0-5-5 5" />}</svg>}
              <span>{availabilityLabel}</span>
            </p>
            <div className="catalogue-card-actions">
              <Link className="button button-secondary catalogue-card-action" to={catalogueProductPath(item.id, displayedRange, cataloguePath)} state={{ catalogueReturn: cataloguePath }} onClick={() => rememberCataloguePosition(cataloguePath)}>Ver equipo</Link>
              <CatalogueReservations id={item.id} name={item.name} count={item.active_reservations_count} today={today} />
            </div>
            <SaveProductButton id={item.id} name={item.name} />
          </div>
        </li>;
      })}</ul>}
    </section>
  </>;
}
