import os
import subprocess

import sys
import zipfile
from os import access, defpath, pathsep, environ, F_OK, X_OK
from os.path import exists, split, join

__all__ = 'which which_files pathsep defpath defpathext F_OK R_OK W_OK X_OK'.split()

ENOENT = 2

windows = sys.platform.startswith('win')

defpath = environ.get('PATH', defpath).split(pathsep)

if windows:
    defpath.insert(0, '.')
    seen = set()
    defpath = [dir for dir in defpath if dir.lower()
               not in seen and not seen.add(dir.lower())]
    del seen

    defpathext = [''] + environ.get(
        'PATHEXT',
        '.COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC'
        ).lower().split(pathsep)
else:
    defpathext = ['']


def which_files(file, mode=F_OK | X_OK, path=None, pathext=None):
    filepath, file = split(file)

    if filepath:
        path = (filepath,)
    elif path is None:
        path = defpath
    elif isinstance(path, str):
        path = path.split(pathsep)

    if pathext is None:
        pathext = defpathext
    elif isinstance(pathext, str):
        pathext = pathext.split(pathsep)

    if '' not in pathext:
        pathext.insert(0, '')

    for dir in path:
        basepath = join(dir, file)
        for ext in pathext:
            fullpath = basepath + ext
            if exists(fullpath) and access(fullpath, mode):
                yield fullpath


def which(file, mode=F_OK | X_OK, path=None, pathext=None):
    path = next(which_files(file, mode, path, pathext), None)
    if path is None:
        raise IOError(ENOENT, '%s not found' % (
            mode & X_OK and 'command' or 'file'), file)
    return path


def find_pg_tool(name):
    path = None
    try:
        return which(name, path=path)
    except IOError:
        raise Exception('Command `%s` not found.' % name)


def exec_pg_environ(**kwargs):
    env = os.environ.copy()
    env['PGHOST'] = 'localhost'
    env['PGPORT'] = '5432'
    env['PGUSER'] = kwargs['<dbuser>']
    env['PGPASSWORD'] = kwargs['<dbpasswd>']
    return env


def exec_pg_command(name, *args, **kwargs):
    prog = find_pg_tool(name)
    env = exec_pg_environ(**kwargs)
    with open(os.devnull) as dn:
        args2 = (prog,) + args
        rc = subprocess.call(args2, env=env, stdout=dn,
                             stderr=subprocess.STDOUT)
        if rc:
            raise Exception('Postgres subprocess %s error %s' % (args2, rc))


def zip_dir(path, stream, include_dir=True):
    path = os.path.normpath(path)
    len_prefix = len(os.path.dirname(path)) if include_dir else len(path)
    if len_prefix:
        len_prefix += 1

    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED,
                         allowZip64=True) as zipf:
        for dirpath, dirnames, filenames in os.walk(path):
            for fname in filenames:
                bname, ext = os.path.splitext(fname)
                ext = ext or bname
                if ext not in ['.pyc', '.pyo', '.swp', '.DS_Store']:
                    path = os.path.normpath(os.path.join(dirpath, fname))
                    if os.path.isfile(path):
                        zipf.write(path, path[len_prefix:])
