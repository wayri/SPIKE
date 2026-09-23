"""Frozen Studio entry point; worker dispatch precedes all GUI imports."""
import multiprocessing
import os
from pathlib import Path
import sys


def main():
    multiprocessing.freeze_support()
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    library=root/'native'/('spikes_c_api.dll' if os.name=='nt' else 'libspikes_c_api.so')
    cache=Path(os.environ.get('LOCALAPPDATA',os.environ.get('XDG_CACHE_HOME',str(Path.home()/'.cache'))))/'SPIKES Studio'/'matplotlib'
    os.environ.setdefault('MPLCONFIGDIR',str(cache))
    if '--package-smoke' in sys.argv:
        from spikes_studio.package_smoke import run
        return run(library,Path(sys.argv[sys.argv.index('--package-smoke')+1]))
    from spikes_studio.desktop import main as studio
    arguments=sys.argv[1:]
    if '--library' not in arguments:arguments=['--library',str(library),*arguments]
    return studio(arguments)


if __name__=='__main__':raise SystemExit(main())
