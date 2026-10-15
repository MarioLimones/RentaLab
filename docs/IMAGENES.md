# Fotografías de ejemplo

El catálogo y las fichas usan tres fotos reales descargadas de Wikimedia Commons,
servidas desde `/api/public/images/` bajo el mismo origen. No hay peticiones a
servidores de imágenes externos durante el uso de la demo. Las dos cámaras
comparten fotografía porque son dos unidades del mismo modelo ficticio.

| Archivo | Fotografía y fuente | Autor | Licencia |
| --- | --- | --- | --- |
| `demo-camera.jpg` | [Sony Alpha A700](https://commons.wikimedia.org/wiki/File:Sony-Alpha-A700-Front.jpg) | Evan-Amos | Dominio público |
| `demo-microphone.jpg` | [USB Microphone](https://commons.wikimedia.org/wiki/File:USB-Microphone.jpg) | Evan-Amos | Dominio público |
| `demo-light.jpg` | [Aputure HR672C sobre trípode](https://commons.wikimedia.org/wiki/File:Aputure_HR672C_LED_light_on_a_stand.jpg) | [Sam Wilson](https://commons.wikimedia.org/wiki/User:Samwilson) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |

Se usan miniaturas de 1280 px suministradas por Commons, sin recortes ni retoques.
La copia de la fotografía de Sam Wilson conserva CC BY-SA 4.0. Los créditos
completos están en `backend/rentalab/public_catalogue/assets/photo-credits.txt`,
accesibles públicamente y enlazados desde el pie del portal.

La etiqueta «Fotografía de ejemplo» distingue estas imágenes de fotografías del
inventario. Los modelos y características de RentaLab siguen siendo ficticios:
la fotografía de cámara muestra un cuerpo Sony, la de micrófono un modelo USB y
la de iluminación un panel Aputure con trípode. No se afirma que correspondan a
las especificaciones ficticias ni que los accesorios estén incluidos.

`seed` asigna imágenes sólo a equipos nuevos y conserva cualquier equipo ya
existente, incluidas sus imágenes editadas. No hay migración, descarga en el
arranque ni actualización automática de las bases existentes. En la instancia
de demostración abierta se actualizaron únicamente las imágenes de sus cuatro
equipos mediante la API administrativa, conservando el resto de sus campos.

El servidor sólo expone los nombres incluidos en `public_catalogue/media.py`;
no sirve directorios arbitrarios. Las imágenes son de lectura pública y las
operaciones administrativas mantienen sus permisos y CSRF. El SVG local sigue
actuando como alternativa cuando no hay foto o falla la carga.
