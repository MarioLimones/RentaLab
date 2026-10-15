import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it } from 'vitest';
import { Notice } from './ui';

it('focuses a new error once and lets users keep typing while it remains visible', async () => {
  function Filters() {
    const [query, setQuery] = useState('');
    return <><label>Buscar<input value={query} onChange={(event) => setQuery(event.target.value)} /></label><Notice tone="error">No se pudieron cargar los datos. <button type="button">Reintentar</button></Notice></>;
  }
  const user = userEvent.setup();
  render(<Filters />);
  expect(screen.getByRole('alert')).toHaveFocus();
  const input = screen.getByRole('textbox', { name: 'Buscar' });
  await user.type(input, 'cámara');
  expect(input).toHaveValue('cámara');
  expect(input).toHaveFocus();
});

it('links the error summary to each invalid field using Spanish labels', () => {
  render(<Notice tone="error" errors={{ customer_email: 'Revisa el correo.', end_date: 'Indica el fin.' }}>Revisa los campos indicados.</Notice>);
  expect(screen.getByRole('link', { name: 'Correo del cliente: Revisa el correo.' })).toHaveAttribute('href', '#customer_email');
  expect(screen.getByRole('link', { name: 'Fecha de fin: Indica el fin.' })).toHaveAttribute('href', '#end_date');
});
