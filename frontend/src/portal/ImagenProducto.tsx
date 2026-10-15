import { useState } from 'react';
import type { EquipoPublico } from '../api/cliente';

const fotosEjemplo = new Set(['/api/public/images/demo-camera.jpg', '/api/public/images/demo-microphone.jpg', '/api/public/images/demo-light.jpg']);

function ImagenEquipo({ equipo, className: claseCss, inmediato }: { equipo: EquipoPublico; className: string; inmediato: boolean }) {
  const [fallido, establecerFallido] = useState(false);
  const alternativa = !equipo.image_url || fallido;
  const ejemplo = !alternativa && fotosEjemplo.has(equipo.image_url ?? '');
  return <div className={`catalogue-image ${claseCss}${alternativa ? ' catalogue-image-fallback' : ''}${ejemplo ? ' catalogue-image-example' : ''}`}>
    <img src={alternativa ? equipo.image_fallback_url : equipo.image_url ?? equipo.image_fallback_url}
      alt={alternativa ? `Imagen de referencia para ${equipo.name}` : ejemplo ? `Fotografía de ejemplo para ${equipo.name}` : equipo.name}
      loading={inmediato ? 'eager' : 'lazy'} width="640" height="480"
      onError={alternativa ? undefined : () => establecerFallido(true)} />
    {alternativa && <span className="catalogue-image-caption">Imagen de referencia</span>}
    {ejemplo && <span className="catalogue-image-caption">Fotografía de ejemplo</span>}
  </div>;
}

export function ImagenProducto({ equipo, className: claseCss = '', inmediato = false }: { equipo: EquipoPublico; className?: string; inmediato?: boolean }) {
  return <ImagenEquipo key={`${equipo.id}-${equipo.image_url ?? ''}`} equipo={equipo} className={claseCss} inmediato={inmediato} />;
}
