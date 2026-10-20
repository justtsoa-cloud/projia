"""Point d'entrée du cœur Projia embarqué dans l'application (serious_python).

L'application Flutter fournit par variables d'environnement :
- PROJIA_PORT, PROJIA_TOKEN (jeton aléatoire : aucune autre appli de
  l'appareil ne peut utiliser le serveur local) ;
- PROJIA_HOME (dossier de données inscriptible) ;
- PROJIA_PLATFORM (android | linux).
Les clés API ne transitent pas par ici : l'application les envoie en mémoire
via `PUT /projia/keys/{fournisseur}` (persist=false), depuis son stockage sécurisé.
"""

import os
import time
import traceback

os.environ.setdefault("PROJIA_HOME", os.path.join(os.getcwd(), "projia"))
os.environ.setdefault("PROJIA_NO_KEYRING", "1")
_t0 = time.monotonic()


def _log_crash() -> None:
    home = os.environ["PROJIA_HOME"]
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, "crash.log"), "a", encoding="utf-8") as fh:
        traceback.print_exc(file=fh)
    traceback.print_exc()


def main() -> None:
    import uvicorn

    from projia.config import load_settings
    from projia.server.app import create_app

    settings = load_settings()
    settings.server.host = "127.0.0.1"
    settings.server.port = int(os.environ.get("PROJIA_PORT", "8765"))
    settings.server.token = os.environ.get("PROJIA_TOKEN") or None
    app = create_app(settings)
    print(f"[projia] imports en {time.monotonic() - _t0:.2f}s", flush=True)
    config = uvicorn.Config(app, host="127.0.0.1", port=settings.server.port,
                            log_level="warning", loop="asyncio", http="h11",
                            lifespan="on", access_log=False)
    # Sous Android, la fin du fil Python ferait tomber toute l'application : le serveur
    # est donc relancé en cas d'erreur inattendue (3 essais), sans jamais quitter le fil.
    for attempt in range(3):
        try:
            uvicorn.Server(config).run()
            return
        except BaseException:
            _log_crash()
            time.sleep(1 + attempt)
            config = uvicorn.Config(app, host="127.0.0.1", port=settings.server.port,
                                    log_level="warning", loop="asyncio", http="h11",
                                    lifespan="on", access_log=False)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        _log_crash()
