import { useState } from 'react';
import { ApiError } from '../api/client';

export function useFormFeedback() {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  function clear() { setErrors({}); setMessage(null); }
  function setFailure(error: unknown) {
    const fields = error instanceof ApiError ? error.fields : {};
    setErrors(fields);
    setMessage(Object.keys(fields).length ? 'Revisa los campos indicados.'
      : error instanceof Error ? error.message : 'No se pudo completar la operación. Inténtalo de nuevo.');
  }
  function setValidation(fields: Record<string, string>) {
    setErrors(fields);
    setMessage(Object.values(fields).join(' '));
  }
  return { errors, message, pending, setMessage, setPending, clear, setFailure, setValidation };
}
