"""Exécutions locales isolées : refus fermé, réseau coupé et ressources bornées."""
from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from pathlib import Path

MAX_OUTPUT = 1_000_000


def available() -> bool:
    from tontolo.agent.mcp_client import bwrap_usable

    return bwrap_usable() is not None


def unavailable_message(language: str = 'fr') -> str:
    return {
        'fr': 'Exécution indisponible : bubblewrap est nécessaire pour le bac à sable.',
        'en': 'Execution unavailable: bubblewrap is required for the sandbox.',
        'mg': 'Tsy azo atao: mila bubblewrap ny fefy.',
    }.get(language, 'Execution unavailable: bubblewrap is required for the sandbox.')


class SandboxUnavailable(RuntimeError):
    pass


def argv(command: list[str], work: Path, *, hidden: list[Path] | None = None,
         read_only: list[Path] | None = None) -> list[str]:
    from tontolo.agent.mcp_client import bwrap_usable

    exe = bwrap_usable()
    if not exe:
        raise SandboxUnavailable(unavailable_message())
    # Racine vide : aucun dossier personnel, donnée Tontolo, /run ou /etc entier exposé.
    args = [exe, '--unshare-all', '--die-with-parent', '--new-session',
            '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp']
    for name in ('/usr', '/bin', '/sbin', '/lib', '/lib64', '/etc/ld.so.cache',
                 '/etc/fonts', '/etc/texmf', '/var/lib/texmf', '/var/cache/fontconfig'):
        if Path(name).exists():
            args += ['--ro-bind', name, name]
    for path in read_only or []:
        args += ['--ro-bind', str(path), str(path)]
    args += ['--bind', str(work), str(work)]
    for path in hidden or []:
        if path.is_dir():
            args += ['--tmpfs', str(path)]
        else:
            args += ['--ro-bind', '/dev/null', str(path)]
    return [*args, '--chdir', str(work), '--', *command]


def limits() -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024**2,) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))


async def run(command: list[str], work: Path, *, time_limit: float,
              hidden: list[Path] | None = None) -> tuple[int, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *argv(command, work, hidden=hidden), cwd=work,
        env={'PATH': '/usr/bin:/bin', 'HOME': '/tmp', 'TMPDIR': '/tmp', 'LANG': 'C.UTF-8'},
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT, start_new_session=True, preexec_fn=limits)
    output = bytearray()
    try:
        async with asyncio.timeout(time_limit):
            assert proc.stdout is not None
            while chunk := await proc.stdout.read(65536):
                output.extend(chunk)
                if len(output) > MAX_OUTPUT:
                    raise RuntimeError('Sortie du processus trop volumineuse')
            code = await proc.wait()
        return code, bytes(output)
    finally:
        # Le groupe inclut le superviseur bubblewrap ; son espace PID emporte les descendants.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        await proc.wait()
