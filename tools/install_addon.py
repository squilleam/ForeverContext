"""Deploy only ForeverContext, refusing to replace any differing existing folder."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys


class InstallError(ValueError):
    pass


def manifest(folder):
    if folder.is_symlink():
        raise InstallError('Symlink addon folders are not accepted')
    files = {}
    for path in sorted(folder.rglob('*')):
        if path.is_symlink():
            raise InstallError('Symlink addon contents are not accepted')
        if path.is_file():
            files[path.relative_to(folder).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def install_addon(source, addons):
    source, addons = Path(source), Path(addons)
    if source.name != 'ForeverContext' or not (source/'ForeverContext.toc').is_file():
        raise InstallError('Source must contain ForeverContext/ForeverContext.toc')
    hashes = manifest(source)
    if not hashes or any(Path(name).suffix.lower() not in {'.lua','.toc'} for name in hashes):
        raise InstallError('Only addon .toc and .lua files may be deployed')
    if not any(name.endswith('.lua') for name in hashes):
        raise InstallError('No addon Lua implementation found')
    destination = addons/'ForeverContext'
    if destination.exists():
        if manifest(destination) != hashes:
            raise InstallError('A different ForeverContext folder already exists. Back it up explicitly before replacing it; nothing was changed.')
        return {'status':'already-current','destination':str(destination),'verifiedFiles':len(hashes),'sha256':hashes}
    addons.mkdir(parents=True,exist_ok=True)
    # Copy into a new directory only. Never replace an existing addon.
    shutil.copytree(source,destination)
    actual = manifest(destination)
    if actual != hashes:
        raise InstallError('Deployed files differ from source; installation verification failed')
    return {'status':'installed','destination':str(destination),'verifiedFiles':len(hashes),'sha256':actual}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]/'addon'/'ForeverContext')
    parser.add_argument('--addons',type=Path,default=Path('C:/Program Files (x86)/World of Warcraft/_forever_/Interface/AddOns'))
    args=parser.parse_args(argv)
    try:
        print(json.dumps(install_addon(args.source,args.addons),indent=2))
        return 0
    except (InstallError,OSError) as exc:
        print('ForeverContext install: '+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
