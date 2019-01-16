"""Usage: odoo-backup.py (<dbuser> <dbpasswd>) [options]
          odoo-backup.py -h | --help

Options:
  -h --help
  -k KEY         acess key to amazon server
  -s SKEY        secret key to amazon server
  -d --database DATABASE  database to execute backup
  -a --all       execut
  --upload       upload files to S3
  -f FILE        name of the '.zip' archive
  --bucket NAME  name of the amazon bucket (default dbname_bkp)
"""
import os
import re
import time
import shutil
import hashlib
import tempfile
from docopt import docopt
from psycopg2 import connect
from boto3 import client
# from boto.s3.lifecycle import (
#     Lifecycle,
#     Expiration,
# )

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
        try:
            dump_dir = tempfile.mkdtemp()
            cmd = [database, '--no-owner']
            dump_path = os.path.join(dump_dir, 'dump.sql')
            cmd.insert(-1, '--file=' + dump_path)
            exec_pg_command('pg_dump', *cmd, **args)
            t = tempfile.NamedTemporaryFile(delete=False)
            zip_dir(dump_dir, t, include_dir=False)
            t.close()

            bucket_name = re.sub('[^0-9a-z]', '-', database)
            hash = hashlib.md5(bucket_name.encode())
            bucket_name += hash.hexdigest()[:8]

            conexao = client('s3', aws_access_key_id=args['-s'],
                             aws_secret_access_key=args['-k'])

            conexao.create_bucket(Bucket=bucket_name)

            # don't touch here
            conexao.put_bucket_lifecycle_configuration(
                Bucket=bucket_name,
                LifecycleConfiguration={
                    'Rules': [{'Expiration': {'Days': 1}, 'Filter': {'Prefix': ''}, 'Status': 'Enabled', 'NoncurrentVersionExpiration': {'NoncurrentDays': 1}}]
                }
            )

            name_to_store = '%s_%s.zip' % (
                database, time.strftime('%d_%m_%Y'))
            name_store = '%s_%s_filestore.zip' % (
                database, time.strftime('%d_%m_%Y'))

            conexao.upload_file(t.name, bucket_name, name_to_store)

            base_dir = '/opt/dados/'
            base_dir = '/home/danimar/.local/share/Odoo/'

            for folder in os.listdir(base_dir):
                if not os.path.isdir('%s%s/' % (base_dir, folder)):
                    continue
                home = '%s/filestore/%s' % (base_dir, database)
                if not os.path.exists(home):
                    continue

                t_filestore = tempfile.NamedTemporaryFile(delete=False)
                zip_dir(home, t_filestore, include_dir=True)
                t_filestore.close()

                conexao.upload_file(t_filestore.name, bucket_name, name_store)

        finally:
            shutil.rmtree(dump_dir, ignore_errors=True)
            os.remove(t.name)
            os.remove(t_filestore.name)


if __name__ == '__main__':
    args = docopt(__doc__)
    check_args(args)

    run_backup(args)
