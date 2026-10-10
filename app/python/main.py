"""Point d'entrée du cœur Tontolo embarqué dans l'application (serious_python).

L'application Flutter fournit par variables d'environnement :
- TONTOLO_PORT, TONTOLO_TOKEN (jeton aléatoire : aucune autre appli de
  l'appareil ne peut utiliser le serveur local) ;
- TONTOLO_HOME (dossier de données inscriptible) ;
- TONTOLO_PLATFORM (android | linux).
Les clés API ne transitent pas par ici : l'application les envoie en mémoire
via `PUT /tontolo/keys/{fournisseur}` (persist=false), depuis son stockage sécurisé.
"""

import os
import sys
import time
import traceback

os.environ.setdefault("TONTOLO_HOME", os.path.join(os.getcwd(), "tontolo"))
os.environ.setdefault("TONTOLO_NO_KEYRING", "1")
_t0 = time.monotonic()


def main() -> None:
    import uvicorn

    from tontolo.config import load_settings
    from tontolo.server.app import create_app

    settings = load_settings()
    settings.server.host = "127.0.0.1"
    settings.server.port = int(os.environ.get("TONTOLO_PORT", "8765"))
    settings.server.token = os.environ.get("TONTOLO_TOKEN") or None
    app = create_app(settings)
    print(f"[tontolo] imports en {time.monotonic() - _t0:.2f}s", flush=True)
    config = uvicorn.Config(app, host="127.0.0.1", port=settings.server.port,
                            log_level="warning", loop="asyncio", http="h11",
                            lifespan="on", access_log=False)
    uvicorn.Server(config).run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log = os.path.join(os.environ["TONTOLO_HOME"], "crash.log")
        os.makedirs(os.environ["TONTOLO_HOME"], exist_ok=True)
        with open(log, "w", encoding="utf-8") as fh:
            traceback.print_exc(file=fh)
        traceback.print_exc()
        sys.exit(1)
