"""Usage: odoo-backup.py (<dbuser> <dbpasswd>) [options]
          odoo-backup.py -h | --help

Options:
  -h --help
  -k KEY         acess key to amazon server
  -s SKEY        secret key to amazon server
  -d --database  database to execute backup
  -a --all       execut
  --upload       upload files do S3
  -f FILE        name of the '.zip' archive
  --bucket NAME  name of the amazon bucket (default dbname_bkp)
"""
import os
import tempfile
from docopt import docopt
from psycopg2 import connect
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from boto.s3.connection import S3Connection
from zipfile import ZipFile

from common import exec_pg_command


def check_args(args):
    if (not ['<dbuser>'] or not ['<dbpasswd>']):
        exit("(<dbuser> <dbpasswd>) are required!\
                \n Use '-h' for help")


def _databases_to_execute(args):
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

    dump_dir = tempfile.mkdtemp()
    cmd = ['pg_dump', '--no-owner']
    cmd.insert(-1, '--file=' + os.path.join(dump_dir, 'dump.sql'))

    for database in databases:
        exec_pg_command(*cmd)


if __name__ == '__main__':
    args = docopt(__doc__)
    check_args(args)

    run_backup(args)
