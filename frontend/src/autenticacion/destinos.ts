import type { RolUsuario } from '../tipos/api';

function esFechaCalendario(valor: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(valor)) return false;
  const [ano, mes, dia] = valor.split('-').map(Number);
  if (!ano) return false;
  const fecha = new Date(0);
  fecha.setUTCFullYear(ano!, mes! - 1, dia!);
  return fecha.getUTCFullYear() === ano && fecha.getUTCMonth() + 1 === mes && fecha.getUTCDate() === dia;
}

/** Sólo se admiten destinos de la lista permitida recibidos en la consulta de acceso. */
export function destinoPermitido(sinProcesar: string | null): string | null {
  if (!sinProcesar || !sinProcesar.startsWith('/') || sinProcesar.startsWith('//') || sinProcesar.includes('\\') || Array.from(sinProcesar).some((caracter) => caracter.charCodeAt(0) < 32 || caracter.charCodeAt(0) === 127)) return null;
  const url = new URL(sinProcesar, 'https://rentalab.invalid');
  if (url.origin !== 'https://rentalab.invalid') return null;
  const ruta = url.pathname.replace(/\/$/, '') || '/';
  const administracion = /^\/admin(?:\/(?:equipos(?:\/(?:nuevo|[1-9]\d*(?:\/editar)?))?|reservas(?:\/(?:nueva|[1-9]\d*))?|incidencias(?:\/(?:nueva|[1-9]\d*))?|importaciones))?$/.test(ruta);
  const cliente = /^\/(?:catalogo|mi-lista|mi-cuenta|mis-incidencias|mis-reservas(?:\/[1-9]\d*)?|equipos\/[1-9]\d*)$/.test(ruta);
  if (!administracion && !cliente) return null;
  const consulta = new URLSearchParams();
  if (['/admin/reservas/nueva', '/admin/incidencias/nueva'].includes(ruta)) {
    const idEquipo = url.searchParams.get('equipment_id');
    if (idEquipo && /^[1-9]\d*$/.test(idEquipo)) consulta.set('equipment_id', idEquipo);
  }
  if (ruta === '/catalogo' || ruta === '/mi-lista' || /^\/equipos\/[1-9]\d*$/.test(ruta)) {
    for (const campo of ['start_date', 'end_date']) {
      const valor = url.searchParams.get(campo);
      if (valor && esFechaCalendario(valor)) consulta.set(campo, valor);
    }
    if (ruta === '/catalogo') {
      for (const campo of ['q', 'category']) {
        const valor = url.searchParams.get(campo);
        if (valor) consulta.set(campo, valor.slice(0, campo === 'q' ? 120 : 80));
      }
      if (url.searchParams.get('available') === '1') consulta.set('available', '1');
    } else if (/^\/equipos\/[1-9]\d*$/.test(ruta)) {
      const catalogo = destinoCatalogoPermitido(url.searchParams.get('catalogue'));
      if (catalogo) consulta.set('catalogue', catalogo);
    }
  }
  return ruta + (consulta.size ? `?${consulta}` : '');
}

/** Los enlaces de vuelta al catálogo pueden llevar filtros, pero nunca otra pantalla ni otro origen. */
export function destinoCatalogoPermitido(sinProcesar: string | null): string | null {
  if (!sinProcesar || !/^\/catalogo(?:\?|$)/.test(sinProcesar)) return null;
  return destinoPermitido(sinProcesar);
}

export function destinoTrasAcceso(rol: RolUsuario, sinProcesar: string | null): string {
  const destino = destinoPermitido(sinProcesar);
  const administrativo = destino === '/admin' || destino?.startsWith('/admin/');
  if (rol === 'admin') return administrativo && destino ? destino : '/admin';
  return destino && !administrativo ? destino : '/mi-cuenta';
}

export function urlAcceso(destino: string): string {
  const permitido = destinoPermitido(destino);
  return '/acceso' + (permitido ? `?next=${encodeURIComponent(permitido)}` : '');
}
