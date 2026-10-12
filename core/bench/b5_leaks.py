"""B5 : fuites après usage intensif (terminaux, tours, fichiers ouverts, processus fils)."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from tontolo.agent.terminal import MAX_SESSIONS, TerminalManager


def fds() -> int:
    return len(os.listdir("/proc/self/fd"))


def children() -> int:
    me = os.getpid()
    n = 0
    for p in Path("/proc").glob("[0-9]*/stat"):
        try:
            if int(p.read_text().rsplit(")", 1)[1].split()[1]) == me:
                n += 1
        except (OSError, ValueError, IndexError):
            pass
    return n


async def main() -> None:
    base_fd, base_ch = fds(), children()
    mgr = TerminalManager()
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(60):  # 60 discussions successives : au plus MAX_SESSIONS vivantes
            s = mgr.get(f"c{i}", Path(tmp))
            s.write(b"echo hi\n")
            assert len(mgr.sessions) <= MAX_SESSIONS
        await asyncio.sleep(0.5)
        mid_ch = children()
        mgr.close_all()
        await asyncio.sleep(6)  # récolte des fils
    print(f"fds {base_fd} → {fds()} ; fils vivants {base_ch} → {mid_ch} → {children()}")
    assert fds() <= base_fd + 2, "descripteurs non fermés"
    assert children() <= base_ch, "processus fils non récoltés (zombies)"
    print("OK")


asyncio.run(main())
