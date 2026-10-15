import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it } from 'vitest';
import { Aviso } from './interfaz';

it("enfoca una vez un error nuevo y permite seguir escribiendo mientras permanece visible", async () => {
  function Filtros() {
    const [consulta, establecerConsulta] = useState('');
    return <><label>Buscar<input value={consulta} onChange={(evento) => establecerConsulta(evento.target.value)} /></label><Aviso tono="error">No se pudieron cargar los datos. <button type="button">Reintentar</button></Aviso></>;
  }
  const usuario = userEvent.setup();
  render(<Filtros />);
  expect(screen.getByRole('alert')).toHaveFocus();
  const entrada = screen.getByRole('textbox', { name: 'Buscar' });
  await usuario.type(entrada, 'cámara');
  expect(entrada).toHaveValue('cámara');
  expect(entrada).toHaveFocus();
});

it("enlaza el resumen de errores con cada campo no válido mediante etiquetas en español", () => {
  render(<Aviso tono="error" errores={{ customer_email: 'Revisa el correo.', end_date: 'Indica el fin.' }}>Revisa los campos indicados.</Aviso>);
  expect(screen.getByRole('link', { name: 'Correo del cliente: Revisa el correo.' })).toHaveAttribute('href', '#customer_email');
  expect(screen.getByRole('link', { name: 'Fecha de fin: Indica el fin.' })).toHaveAttribute('href', '#end_date');
});
