"""Espace de travail du bureau (Linux) : l'agent manipule les fichiers d'UN dossier choisi par
l'utilisateur, avec garde-fous.

- Tout chemin est confiné au dossier choisi (liens symboliques résolus) ; les dossiers et
  fichiers sensibles (.ssh, .gnupg, clés, .env, mots de passe…) sont refusés.
- Lire, lister et chercher sont libres ; créer, modifier et lancer une commande demandent la
  confirmation de l'utilisateur (outil « à effet de bord »), avec la différence affichée.
- Chaque écriture est sauvegardée d'abord : « annuler » restaure l'état précédent.
- Les commandes du terminal (bureau seulement) partent du dossier choisi, une à la fois,
  avec délai maximal et sortie limitée ; les commandes destructrices évidentes sont refusées.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from tontolo import sandbox
from tontolo.agent.tools import Tool

MAX_READ = 60_000
MAX_WRITE = 2_000_000
MAX_OUTPUT = 12_000
COMMAND_TIMEOUT = 120.0
JOURNAL_KEEP = 50

SENSITIVE_DIRS = {".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".password-store",
                  ".mozilla", ".thunderbird", "keyrings", ".pki", ".gcloud", ".vault-token"}
SENSITIVE_FILES = re.compile(
    r"^(id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|\.env(\..*)?|\.netrc|\.pgpass|\.git-credentials|"
    r"credentials(\.json)?|secrets?\.(json|ya?ml|toml)|.*\.(pem|key|p12|pfx|kdbx|keystore|jks))$",
    re.I)
FORBIDDEN_ROOTS = [Path(p) for p in ("/", "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64",
                                     "/boot", "/proc", "/sys", "/dev", "/var", "/root", "/opt",
                                     "/run", "/srv")]
DANGEROUS = re.compile(
    r"(\bsudo\b|\bsu\b\s|\bdoas\b|\bmkfs|\bdd\b\s+.*of=|\bshutdown\b|\breboot\b|\bpoweroff\b|"
    r":\(\)\s*\{|\brm\s+(-\w*\s+)*(/|~|\$HOME)(\s|$)|\bchmod\s+-R\s+777\s+/|"
    r"(curl|wget)[^|]*\|\s*(ba|z)?sh\b|>\s*/dev/sd|\bchown\s+-R\b.*\s/(\s|$))")


_SECRET = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|sk-ant-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|"
    r"xox[abpr]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----)")
_ASSIGN = re.compile(r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD)[A-Z0-9_]*"
                     r"\s*[=:]\s*)(['\"]?)[^\s'\"]{4,}\2")


def redact(text: str) -> str:
    """Masque les secrets (clés d'API, jetons, mots de passe, clés privées) avant que le
    texte parte vers un modèle en ligne."""
    text = _SECRET.sub("[secret masqué]", text)
    return _ASSIGN.sub(lambda m: f"{m.group(1)}[secret masqué]", text)


def is_desktop() -> bool:
    """Bureau Linux (pas Android, qui se présente aussi comme « linux »)."""
    return (sys.platform == "linux" and "ANDROID_ROOT" not in os.environ
            and not hasattr(sys, "getandroidapilevel"))


def check_workdir(path: str) -> Path:
    """Dossier de travail acceptable : existe, n'est ni le dossier personnel entier, ni un
    dossier système, ni un dossier sensible."""
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise ValueError("dossier introuvable")
    home = Path.home().resolve()
    system = p == Path("/") or any(p.is_relative_to(r) for r in FORBIDDEN_ROOTS[1:])
    if p == home or (system and not p.is_relative_to(home)):
        raise ValueError("choisissez un sous-dossier précis (pas le dossier personnel entier "
                         "ni un dossier système)")
    if _sensitive(p) or (p.is_relative_to(home) and any(
            part.startswith(".") for part in p.relative_to(home).parts)):
        raise ValueError("dossier sensible ou caché refusé (ex. .config, .local)")
    return p


def _sensitive(p: Path) -> bool:
    return any(part in SENSITIVE_DIRS for part in p.parts) or bool(SENSITIVE_FILES.match(p.name))


class Workspace:
    def __init__(self, root: Path, backups: Path) -> None:
        self.root = root.resolve()
        self.backups = backups
        self.journal_path = backups / "journal.json"

    # --- chemins ---------------------------------------------------------------
    def path(self, rel: str) -> Path:
        rel = (rel or ".").strip()
        target = (self.root / rel).resolve()
        if not target.is_relative_to(self.root):
            raise PermissionError("chemin hors du dossier de travail")
        if _sensitive(target.relative_to(self.root)) or _sensitive(target):
            raise PermissionError("fichier ou dossier sensible : accès refusé")
        return target

    def rel(self, p: Path) -> str:
        return str(p.relative_to(self.root)) or "."

    # --- journal (sauvegardes) --------------------------------------------------
    def journal(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.journal_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save_journal(self, entries: list[dict[str, Any]]) -> None:
        self.backups.mkdir(parents=True, exist_ok=True)
        for old in entries[:-JOURNAL_KEEP]:
            if old.get("backup"):
                Path(old["backup"]).unlink(missing_ok=True)
        self.journal_path.write_text(json.dumps(entries[-JOURNAL_KEEP:], ensure_ascii=False),
                                     encoding="utf-8")

    def _backup(self, target: Path, action: str) -> None:
        entries = self.journal()
        entry: dict[str, Any] = {"path": str(target), "rel": self.rel(target), "action": action,
                                 "at": time.time(), "backup": None}
        if target.exists():
            self.backups.mkdir(parents=True, exist_ok=True)
            dest = self.backups / f"{time.time_ns()}-{target.name}"
            shutil.copy2(target, dest)
            entry["backup"] = str(dest)
        entries.append(entry)
        self._save_journal(entries)

    def undo(self) -> str:
        entries = self.journal()
        if not entries:
            return "Rien à annuler."
        entry = entries.pop()
        target = Path(entry["path"])
        if not target.resolve().is_relative_to(self.root):
            self._save_journal(entries)
            return "Annulation impossible : fichier hors du dossier de travail actuel."
        if entry.get("backup") and Path(entry["backup"]).exists():
            shutil.copy2(entry["backup"], target)
            Path(entry["backup"]).unlink(missing_ok=True)
            msg = f"Restauré : {entry['rel']} (état avant « {entry['action']} »)"
        else:
            target.unlink(missing_ok=True)
            msg = f"Supprimé : {entry['rel']} (il n'existait pas avant)"
        self._save_journal(entries)
        return msg

    # --- aperçu (affiché dans la demande de confirmation) -----------------------
    def preview(self, name: str, args: dict[str, Any]) -> str:
        try:
            if name == "run_command":
                return f"$ {args.get('command', '')}"
            if name == "undo_last_change":
                entries = self.journal()
                return (f"Annuler : {entries[-1]['action']} de {entries[-1]['rel']}"
                        if entries else "Rien à annuler.")
            target = self.path(str(args.get("path", "")))
            before = target.read_text(encoding="utf-8", errors="replace") if target.is_file() \
                else ""
            after = self._new_content(name, target, args)
            diff = difflib.unified_diff(before.splitlines(), after.splitlines(),
                                        f"a/{self.rel(target)}", f"b/{self.rel(target)}",
                                        lineterm="", n=2)
            return "\n".join(diff)[:6000] or "(aucun changement)"
        except Exception as exc:  # l'aperçu ne bloque jamais : l'erreur sera redonnée
            return f"Aperçu indisponible : {exc}"

    def _new_content(self, name: str, target: Path, args: dict[str, Any]) -> str:
        if name == "write_file":
            return str(args.get("content", ""))
        old, new = str(args.get("old_text", "")), str(args.get("new_text", ""))
        text = target.read_text(encoding="utf-8")
        count = text.count(old) if old else 0
        if count != 1:
            raise ValueError("le texte à remplacer doit apparaître exactement une fois "
                             f"(trouvé {count} fois) : relis le fichier et précise-le")
        return text.replace(old, new, 1)

    # --- outils ---------------------------------------------------------------
    async def list_dir(self, args: dict[str, Any]) -> str:
        p = self.path(str(args.get("path", ".")))
        if not p.is_dir():
            return "Ce n'est pas un dossier."
        items = []
        for x in sorted(p.iterdir())[:500]:
            if _sensitive(x):
                continue
            items.append(x.name + "/" if x.is_dir() else f"{x.name} ({x.stat().st_size} o)")
        return "\n".join(items) or "(dossier vide)"

    async def read_file(self, args: dict[str, Any]) -> str:
        p = self.path(str(args.get("path", "")))
        if p.is_dir():
            return await self.list_dir(args)
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, int(args.get("start_line") or 1))
        end = int(args.get("end_line") or len(lines))
        out = redact("\n".join(f"{i}\t{line}" for i, line in
                               enumerate(lines[start - 1:end], start)))
        return out[:MAX_READ] + ("\n… (tronqué : lis la suite avec start_line)"
                                 if len(out) > MAX_READ else "")

    async def search_files(self, args: dict[str, Any]) -> str:
        query = str(args.get("query", ""))
        if not query:
            return "Indique un texte à chercher."
        glob = str(args.get("glob") or "**/*")
        hits: list[str] = []
        if ".." in glob or glob.startswith("/"):
            return "Motif refusé : reste dans le dossier de travail."
        for f in self.root.glob(glob):
            if len(hits) >= 80:
                break
            try:
                rel = f.relative_to(self.root)
                inside = f.resolve().is_relative_to(self.root)
            except (ValueError, OSError):
                continue
            if f.is_symlink() or not inside or not f.is_file() or _sensitive(rel) or any(
                    part.startswith(".") or part in ("node_modules", "build", "dist")
                    for part in rel.parts[:-1]) or f.stat().st_size > 2_000_000:
                continue
            if query.lower() in f.name.lower():
                hits.append(f"{rel} (nom)")
            try:
                for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                    if query.lower() in line.lower():
                        hits.append(f"{rel}:{n}: {redact(line.strip()[:200])}")
                        if len(hits) >= 80:
                            break
            except (UnicodeDecodeError, OSError):
                continue
        return "\n".join(hits) or "Aucun résultat."

    async def write_file(self, args: dict[str, Any]) -> str:
        p = self.path(str(args.get("path", "")))
        content = str(args.get("content", ""))
        if len(content) > MAX_WRITE:
            return "Contenu trop long."
        existed = p.exists()
        self._backup(p, "écriture" if existed else "création")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"{'Modifié' if existed else 'Créé'} : {self.rel(p)} ({len(content)} caractères)"

    async def edit_file(self, args: dict[str, Any]) -> str:
        p = self.path(str(args.get("path", "")))
        if not p.is_file():
            return "Fichier introuvable : utilise write_file pour le créer."
        try:
            new = self._new_content("edit_file", p, args)
        except ValueError as exc:
            return f"Modification refusée : {exc}"
        self._backup(p, "modification")
        p.write_text(new, encoding="utf-8")
        return f"Modifié : {self.rel(p)}"

    async def undo_last_change(self, args: dict[str, Any]) -> str:
        return self.undo()

    async def run_command(self, args: dict[str, Any]) -> str:
        cmd = str(args.get("command", "")).strip()
        if not cmd:
            return "Commande vide."
        if DANGEROUS.search(cmd) or any(d in cmd for d in SENSITIVE_DIRS):
            return "Commande refusée par les garde-fous de Tontolo (destructrice ou sensible)."
        if not sandbox.available():
            return sandbox.unavailable_message()
        hidden: list[Path] = []
        for directory, dirs, files in os.walk(self.root, followlinks=False):
            for name in [*dirs, *files]:
                path = Path(directory) / name
                if not path.is_symlink() and (_sensitive(path) or name == ".git"):
                    hidden.append(path)
                    if name in dirs:
                        dirs.remove(name)
        try:
            code, out = await sandbox.run(["/bin/bash", "-c", cmd], self.root,
                                          time_limit=COMMAND_TIMEOUT, hidden=hidden)
        except TimeoutError:
            return f"Délai dépassé ({int(COMMAND_TIMEOUT)} s) : commande arrêtée."
        except (RuntimeError, OSError) as exc:
            return f"Commande refusée : {exc}"
        text = out.decode("utf-8", errors="replace")
        if len(text) > MAX_OUTPUT:
            text = text[:MAX_OUTPUT // 2] + "\n… (sortie tronquée) …\n" + text[-MAX_OUTPUT // 2:]
        return f"Code de sortie : {code}\n{redact(text)}"

    def tools(self, commands: bool) -> list[Tool]:
        path = {"type": "string", "description": "chemin relatif au dossier de travail"}
        out = [
            Tool("list_dir", "Liste un dossier du dossier de travail de l'utilisateur.",
                 {"type": "object", "properties": {"path": path}}, self.list_dir),
            Tool("read_file", "Lit un fichier du dossier de travail (lignes numérotées ; "
                 "start_line/end_line pour une partie).",
                 {"type": "object", "properties": {"path": path,
                                                   "start_line": {"type": "integer"},
                                                   "end_line": {"type": "integer"}},
                  "required": ["path"]}, self.read_file),
            Tool("search_files", "Cherche un texte dans les fichiers du dossier de travail "
                 "(glob optionnel, ex. « **/*.py »).",
                 {"type": "object", "properties": {"query": {"type": "string"},
                                                   "glob": {"type": "string"}},
                  "required": ["query"]}, self.search_files),
            Tool("write_file", "Crée ou remplace un fichier texte (confirmation de "
                 "l'utilisateur, sauvegarde automatique).",
                 {"type": "object", "properties": {"path": path, "content": {"type": "string"}},
                  "required": ["path", "content"]}, self.write_file, side_effect=True),
            Tool("edit_file", "Remplace un passage exact (old_text, présent une seule fois) par "
                 "new_text dans un fichier (confirmation, sauvegarde automatique). Lis le "
                 "fichier avant.",
                 {"type": "object", "properties": {"path": path,
                                                   "old_text": {"type": "string"},
                                                   "new_text": {"type": "string"}},
                  "required": ["path", "old_text", "new_text"]}, self.edit_file,
                 side_effect=True),
            Tool("undo_last_change", "Annule la dernière création ou modification de fichier.",
                 {"type": "object", "properties": {}}, self.undo_last_change, side_effect=True),
        ]
        if commands and sandbox.available():
            out.append(Tool(
                "run_command", "Lance UNE commande bash dans le dossier de travail (après "
                "confirmation de l'utilisateur ; 120 s maximum ; pas de sudo).",
                {"type": "object", "properties": {"command": {"type": "string"}},
                 "required": ["command"]}, self.run_command, side_effect=True))
        for t in out:
            if t.side_effect:
                t.preview = (lambda a, n=t.name: self.preview(n, a))
        return out
