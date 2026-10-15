/** Las fechas de alquiler se conservan como cadenas de calendario, sin convertirlas mediante UTC. */
export function formatearFecha(valor: string): string {
  const [ano, mes, dia] = valor.split('-');
  return `${dia}/${mes}/${ano}`;
}

export function hoyIso(): string {
  const ahora = new Date();
  return `${ahora.getFullYear()}-${String(ahora.getMonth() + 1).padStart(2, '0')}-${String(ahora.getDate()).padStart(2, '0')}`;
}
