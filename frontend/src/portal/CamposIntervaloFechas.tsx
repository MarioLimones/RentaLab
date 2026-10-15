import type { IntervaloFechas } from '../api/cliente';
import { Campo } from '../componentes/interfaz';

export function CamposIntervaloFechas({ valor, onChange: alCambiar, errores = {}, deshabilitado = false }: {
  valor: IntervaloFechas;
  onChange: (nombre: keyof IntervaloFechas, valor: string) => void;
  errores?: Record<string, string>;
  deshabilitado?: boolean;
}) {
  return <fieldset className="catalogue-dates" disabled={deshabilitado}>
    <legend className="sr-only">Fechas del alquiler</legend>
    <Campo nombre="start_date" etiqueta="Fecha de inicio" error={errores.start_date}>
      <input type="date" name="start_date" value={valor.start_date} onChange={(evento) => alCambiar('start_date', evento.target.value)} />
    </Campo>
    <Campo nombre="end_date" etiqueta="Fecha de fin" ayuda="Día de devolución, no incluido en el alquiler." error={errores.end_date}>
      <input type="date" name="end_date" value={valor.end_date} onChange={(evento) => alCambiar('end_date', evento.target.value)} />
    </Campo>
  </fieldset>;
}
