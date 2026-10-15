import type { DateRange } from '../api/client';
import { Field } from '../components/ui';

export function DateRangeFields({ value, onChange, errors = {}, disabled = false }: {
  value: DateRange;
  onChange: (name: keyof DateRange, value: string) => void;
  errors?: Record<string, string>;
  disabled?: boolean;
}) {
  return <fieldset className="catalogue-dates" disabled={disabled}>
    <legend className="sr-only">Fechas del alquiler</legend>
    <Field name="start_date" label="Fecha de inicio" error={errors.start_date}>
      <input type="date" name="start_date" value={value.start_date} onChange={(event) => onChange('start_date', event.target.value)} />
    </Field>
    <Field name="end_date" label="Fecha de fin" hint="Día de devolución, no incluido en el alquiler." error={errors.end_date}>
      <input type="date" name="end_date" value={value.end_date} onChange={(event) => onChange('end_date', event.target.value)} />
    </Field>
  </fieldset>;
}
