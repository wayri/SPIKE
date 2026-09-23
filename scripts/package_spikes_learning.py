"""Build a separate reproducible-path help/examples archive for offline use."""
from pathlib import Path
import argparse
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for folder,prefix in [(ROOT/'standalone/spikes_project/studio/docs','help'),(ROOT/'examples/spikes','examples')]:
            for path in sorted(folder.rglob('*')):
                if path.is_file():archive.write(path,str(Path(prefix)/path.relative_to(folder)))


if __name__=='__main__':main()
