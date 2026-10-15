import { useState } from 'react';
import { ErrorApi } from '../api/cliente';

export function useRetroalimentacionFormulario() {
  const [errores, establecerErrores] = useState<Record<string, string>>({});
  const [mensaje, establecerMensaje] = useState<string | null>(null);
  const [pendiente, establecerPendiente] = useState(false);
  function limpiar() { establecerErrores({}); establecerMensaje(null); }
  function establecerFallo(error: unknown) {
    const campos = error instanceof ErrorApi ? error.campos : {};
    establecerErrores(campos);
    establecerMensaje(Object.keys(campos).length ? 'Revisa los campos indicados.'
      : error instanceof Error ? error.message : 'No se pudo completar la operación. Inténtalo de nuevo.');
  }
  function establecerValidacion(campos: Record<string, string>) {
    establecerErrores(campos);
    establecerMensaje(Object.values(campos).join(' '));
  }
  return { errores, mensaje, pendiente, establecerMensaje, establecerPendiente, limpiar, establecerFallo, establecerValidacion };
}
