"""Usage: odoo_restore.py (<dbname> <dbuser> <dbpasswd>) [options]
          odoo_restore.py -h | --help

Options:
  -h --help
  -s KEY         acess key to amazon server
  -k SKEY        secret key to amazon server
  -d             download files from s3
  -l             local backup (change the directory of 'filestore')
  -z --zip       use it if dump.sql and manifest.json are inside a .zip file
  -t             trial version (changes nfse enviroment to 'homologacao')
  -e --exclude   exclude files after completed process
  -p PATH        path to files, if they are already downloaded
  -f FILE        name of the '.zip' archive
  --bucket NAME  name of the amazon bucket (default dbname_bkp_pelikan)
  -o             use it if filestore and dump in a sigle .zip

"""
from docopt import docopt
import subprocess
from psycopg2 import connect
import os
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from boto.s3.connection import S3Connection
from zipfile import ZipFile
from common import exec_pg_command


def check_args(args):
    if (not args['<dbname>'] or not ['<dbuser>'] or not
            ['<dbpasswd>']):
        exit("(<dbname> <dbuser> <dbpasswd>) are required!\
                \n Use '-h' for help")

    if args['-d']:
        if (args['-p'] or args['-f']):
            exit("Invalid parameters, you can't use -p or -f when you're\
downloading the files \n Use '-h' for help")
        if not (args['-s'] and args['-k']):
            exit("To download the files you need to provide the acess key\
and secret key to the amazon server, using '-a' and '-s'\
\n Use '-h' for help")

    if args['-p']:
        if (args['-p'][-1] != '/'):
            exit("Path to file must end with /")
        if not os.path.exists(args['-p']):
            exit("Path to file doesn't exist!")

    if args['-f'] and (args['-f'][-4:] != '.zip'):
        exit("Name of the . zip file must end with '.zip'")


def get_filestore_from_amazon(bucket, args):
    path = 's3://' + bucket + '/filestore/'
    env = os.environ.copy()
    env['AWS_ACCESS_KEY_ID'] = args['-s']
    env['AWS_SECRET_ACCESS_KEY'] = args['-k']
    subprocess.call(
        'aws s3 cp ' + path + ' . --recursive', shell=True, env=env)


def move_filestore(dbname, local, path_to_files):
    if local:
        path = '~/.local/share/Odoo/filestore/' + dbname + '/'
    else:
        path = '/opt/dados/' + dbname + '/'
    if subprocess.check_output('ls ' + path_to_files + 'filestore',
                               shell=True):
        try:
            subprocess.call('rm -rf ' + path, shell=True)
        except Exception:
            pass

        subprocess.call('mkdir ' + path, shell=True)

        subprocess.check_call('mv ' + path_to_files + 'filestore/* ' +
                              path, shell=True)


def get_db_from_amazon(dbname, bucket, access_key, secret_key):
    conexao = S3Connection(access_key, secret_key)
    bucket = conexao.lookup(bucket)
    sorted_list = sorted([(k.last_modified, k) for k in bucket],
                         key=lambda x: x[0].last_modified)
    key_to_download = False
    for index in range(-1, -(len(sorted_list) + 1), -1):
        if '.zip' in str(sorted_list[index][1]):
            key_to_download = sorted_list[index][1]

    if key_to_download:
        key_to_download.get_contents_to_filename(dbname + '.zip')
    else:
        raise Exception('Arquivo nao encontrado.\
        \nVerifique se a acess  key e a secret key fornecidas estao corretas!')


def create_new_db(dbname, dbuser, dbpasswd):
    con = connect(
        dbname='postgres', user=dbuser, host='localhost', password=dbpasswd)
    con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = con.cursor()
    try:
        cur.execute('drop database ' + dbname)
    except Exception:
        pass

    try:
        cur.execute('CREATE DATABASE ' + dbname + ' with owner ' + dbuser)
    except Exception as e:
        print (e)
        exit("Can't replace a database that is being used by other users")

    cur.close()
    con.close()


def change_to_homologacao(dbname, dbuser, dbpasswd):
    con = connect(dbname=dbname, user=dbuser, host='localhost',
                  password=dbpasswd)
    con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = con.cursor()
    try:
        cur.execute(
            'UPDATE res_company SET tipo_ambiente=2 WHERE tipo_ambiente=1')
    except Exception:
        pass
    try:
        cur.execute(
            'UPDATE res_company SET tipo_ambiente_nfse=2\
WHERE tipo_ambiente_nfse=1')
    except Exception:
        pass

    cur.execute('delete from fetchmail_server')
    cur.execute('delete from ir_mail_server')


def restore_database(args):
    path_to_dump = args['-p']
    path_to_filestore = args['-p']

    if not args['-p']:
        path_to_dump = ''
        path_to_filestore = ''

    if not args['--bucket']:
        args['--bucket'] = '%s_bkp_pelican' % args['<dbname>']

    if args['-d']:
        if not args['-o']:
            try:
                get_filestore_from_amazon(args['--bucket'], args)
            except Exception:
                exit("Download from amazon failed!\
                    \n Do you have 'awscli' installed and configured?\
                    \n 'pip install awscli'\n 'aws configure'")
        get_db_from_amazon(
            args['<dbname>'], args['--bucket'], args['-s'], args['-k'])
        args['-p'] = ''

    if not args['-f']:
        args['-f'] = args['<dbname>'] + '.zip'

    if args['--zip'] or args['-d']:
        try:
            archive = ZipFile(args['-p'] + args['-f'])
            archive.extractall()
            if not args['-o']:
                path_to_filestore = args['-p']
            else:
                path_to_filestore = ''
            path_to_dump = ''

        except Exception as e:
            print (e)
            raise Exception('.zip file not found!')

    create_new_db(args['<dbname>'], args['<dbuser>'], args['<dbpasswd>'])

    pg_cmd = 'psql'
    pg_args = [
        '-q',
        '-f',
        os.path.join(path_to_dump, 'dump.sql'),
        '--dbname=' + args['<dbname>']]

    exec_pg_command(pg_cmd, *pg_args, **args)

    move_filestore(args['<dbname>'], args['-l'], path_to_filestore)

    if args['--exclude']:

        if args['--zip'] or args['-d']:
            os.remove(args['-p'] + args['-f'])

        os.remove(path_to_dump + 'dump.sql')
        os.remove(path_to_dump + 'manifest.json')
        os.rmdir(os.path.join(path_to_filestore, 'filestore'))

    if args['-t']:
        change_to_homologacao(
            args['<dbname>'], args['<dbuser>'], args['<dbpasswd>'])


if __name__ == '__main__':
    args = docopt(__doc__)
    check_args(args)

    restore_database(args)
