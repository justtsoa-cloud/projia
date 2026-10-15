"""Aucune exécution de contenu non fiable sans isolation disponible."""
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tontolo.agent import mcp_client
from tontolo.agent.workspace import Workspace
from tontolo.creator import latex


async def test_latex_without_sandbox_skips_local_and_uses_online(monkeypatch):
    monkeypatch.setattr(mcp_client, 'bwrap_usable', lambda: None)
    local = AsyncMock(return_value=(b'%PDF-test', ''))
    remote = AsyncMock(return_value=(b'%PDF-online', ''))
    monkeypatch.setattr(latex, '_local', local)
    monkeypatch.setattr(latex, '_ytotech', remote)
    pdf, _, service = await latex.compile_pdf('\\documentclass{article}')
    assert pdf == b'%PDF-online' and service == 'latex.ytotech.com'
    local.assert_not_awaited()  # jamais de compilation locale sans isolation


async def test_commands_refused_and_hidden_without_sandbox(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mcp_client, 'bwrap_usable', lambda: None)
    ws = Workspace(tmp_path, tmp_path / 'backups')
    result = await ws.run_command({'command': 'touch should-not-exist'})
    assert 'bubblewrap' in result
    assert not (tmp_path / 'should-not-exist').exists()
    assert 'run_command' not in {t.name for t in ws.tools(commands=True)}


async def test_real_sandbox_hides_environment_files_and_network(tmp_path, monkeypatch):
    from tontolo import sandbox

    if not sandbox.available():
        pytest.skip('bubblewrap utilisable requis pour cet essai réel')
    work = tmp_path / 'work'
    work.mkdir()
    outside = tmp_path / 'outside'
    outside.write_text('FAUSSE_CLE_DISQUE')
    (work / '.env').write_text('FAUSSE_CLE_ENV')
    (work / 'link').symlink_to(outside)
    monkeypatch.setenv('CUSTOM_API_KEY', 'FAUSSE_CLE_PROCESSUS')
    ws = Workspace(work, tmp_path / 'backups')
    result = await ws.run_command({'command':
        'env; cat .env link; /usr/bin/python -c "import socket; '
        "s=socket.socket(); s.settimeout(0.1); print(s.connect_ex(('192.0.2.1',80)))\""})
    assert 'FAUSSE_CLE' not in result
    assert 'Code de sortie : 0' in result
    assert '\n0\n' not in result  # aucune connexion sortante réussie


async def test_real_latex_isolated(tmp_path):
    import shutil

    from tontolo import sandbox

    if not sandbox.available() or not shutil.which('pdflatex'):
        pytest.skip('bubblewrap et pdflatex requis pour cet essai réel')
    pdf, _, backend = await latex.compile_pdf(
        r'\documentclass{article}\begin{document}Bonjour\end{document}')
    assert pdf.startswith(b'%PDF') and backend == 'local'
