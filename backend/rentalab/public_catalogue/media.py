from pathlib import Path

ASSETS_DIRECTORY = Path(__file__).with_name("assets")
PUBLIC_ASSETS = {
    "equipment-placeholder.svg": "image/svg+xml",
    "demo-camera.jpg": "image/jpeg",
    "demo-microphone.jpg": "image/jpeg",
    "demo-light.jpg": "image/jpeg",
    **{f"catalogue-{number:02d}.jpg": "image/jpeg" for number in range(1, 21) if number != 2},
    "catalogue-02.png": "image/png",
    "photo-credits.txt": "text/plain",
}
PUBLIC_ASSET_PATHS = frozenset(f"/api/public/images/{name}" for name in PUBLIC_ASSETS)
