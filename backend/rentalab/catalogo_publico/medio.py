from pathlib import Path

RECURSOS_DIRECTORIO = Path(__file__).with_name("assets")
PUBLICO_RECURSOS = {
    "equipment-placeholder.svg": "image/svg+xml",
    "demo-camera.jpg": "image/jpeg",
    "demo-microphone.jpg": "image/jpeg",
    "demo-light.jpg": "image/jpeg",
    **{f"catalogue-{numero:02d}.jpg": "image/jpeg" for numero in range(1, 21) if numero != 2},
    "catalogue-02.png": "image/png",
    "photo-credits.txt": "text/plain",
}
PUBLICO_RECURSO_RUTAS = frozenset(f"/api/public/images/{nombre}" for nombre in PUBLICO_RECURSOS)
