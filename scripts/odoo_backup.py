"""Usage: odoo-backup.py (<dbuser> <dbpasswd>) [options]
          odoo-backup.py -h | --help

Options:
  -h --help
  -k KEY         acess key to amazon server
  -s SKEY        secret key to amazon server
  -d --database DATABASE  database to execute backup
  -a --all       execut
  --upload       upload files do S3
  -f FILE        name of the '.zip' archive
  --bucket NAME  name of the amazon bucket (default dbname_bkp)
"""
import os
import tempfile
from docopt import docopt
from psycopg2 import connect

from common import exec_pg_command, zip_dir


def check_args(args):
    if (not ['<dbuser>'] or not ['<dbpasswd>']):
        exit("(<dbuser> <dbpasswd>) are required!\
                \n Use '-h' for help")


def _databases_to_execute(args):
    if args['--database']:
        return [args['--database']]
    connection = connect(
        dbname='postgres', user=args['<dbuser>'],
        host='localhost', password=args['<dbpasswd>'])
    cursor = connection.cursor()
    cursor.execute(
        'SELECT datname FROM pg_database WHERE datistemplate = false')
    databases = cursor.fetchall()
    return [a[0] for a in databases]


def run_backup(args):
    databases = _databases_to_execute(args)

    for database in databases:
        if database == 'postgres':
            continue
        dump_dir = tempfile.mkdtemp()
        cmd = [database, '--no-owner']
        dump_path = os.path.join(dump_dir, 'dump.sql')
        cmd.insert(-1, '--file=' + dump_path)
        exec_pg_command('pg_dump', *cmd, **args)
        t = tempfile.NamedTemporaryFile(delete=False)
        zip_dir(dump_dir, t, include_dir=False)
        t.close()


if __name__ == '__main__':
    args = docopt(__doc__)
    check_args(args)

    run_backup(args)
