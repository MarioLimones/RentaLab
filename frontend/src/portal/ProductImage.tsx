import { useState } from 'react';
import type { PublicEquipment } from '../api/client';

const examplePhotos = new Set(['/api/public/images/demo-camera.jpg', '/api/public/images/demo-microphone.jpg', '/api/public/images/demo-light.jpg']);

function EquipmentImage({ equipment, className, eager }: { equipment: PublicEquipment; className: string; eager: boolean }) {
  const [failed, setFailed] = useState(false);
  const fallback = !equipment.image_url || failed;
  const example = !fallback && examplePhotos.has(equipment.image_url ?? '');
  return <div className={`catalogue-image ${className}${fallback ? ' catalogue-image-fallback' : ''}${example ? ' catalogue-image-example' : ''}`}>
    <img src={fallback ? equipment.image_fallback_url : equipment.image_url ?? equipment.image_fallback_url}
      alt={fallback ? `Imagen de referencia para ${equipment.name}` : example ? `Fotografía de ejemplo para ${equipment.name}` : equipment.name}
      loading={eager ? 'eager' : 'lazy'} width="640" height="480"
      onError={fallback ? undefined : () => setFailed(true)} />
    {fallback && <span className="catalogue-image-caption">Imagen de referencia</span>}
    {example && <span className="catalogue-image-caption">Fotografía de ejemplo</span>}
  </div>;
}

export function ProductImage({ equipment, className = '', eager = false }: { equipment: PublicEquipment; className?: string; eager?: boolean }) {
  return <EquipmentImage key={`${equipment.id}-${equipment.image_url ?? ''}`} equipment={equipment} className={className} eager={eager} />;
}
