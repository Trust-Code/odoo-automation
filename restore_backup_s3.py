"""Usage: restore_backup_s3.py (<dbname> <dbuser> <dbpasswd>) [options]
          restore_backup_s3.py -h | --help

Options:
  -h --help
  -a KEY         acess key to amazon server
  -s SKEY        secret key to amazon server
  -d             download files from s3
  -l             local backup (change the directory of 'filestore')
  -z --zip       use it if dump.sql and manifest.json are inside a .zip file
  -t             trial version (changes nfse enviroment to 'homologacao')
  -e --exclude   exclude files after completed process
  -p PATH        path to files, if they are already downloaded
  -f FILE        name of the '.zip' archive
  --bucket NAME  name of the amazon bucket (default dbname_bkp_pelikan)
  -o             download from old backups (filestore + dump in a sigle .zip)

"""
from docopt import docopt
import subprocess
from psycopg2 import connect
import os
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from boto.s3.connection import S3Connection
from zipfile import ZipFile


def check_args(args):
    if (not args['<dbname>'] or not ['<dbuser>'] or not
            ['<dbpasswd>']):
        exit("(<dbname> <dbuser> <dbpasswd>) are required!\
                \n Use '-h' for help")

    if args['-o'] and not args['-d']:
        exit("Invalid parameters, '-o' cannot be True if '-d' is False\
                \n Use '-h' for help")

    if args['-d']:
        if (args['-p'] or args['-f']):
            exit("Invalid parameters, you can't use -p or -f when you're\
downloading the files \n Use '-h' for help")
        if not (args['-a'] and args['-s']):
            exit("To download the files you need to provide the acess key\
and secret key to the amazon server, using '-a' and '-s'\
\n Use '-h' for help")

    if args['-p']:
        if (args['-p'][-1] != '/'):
            exit("Path to file must end with /")
        if not os.path.exists(args['-p']):
            exit("Path to file doesn't exist!")

    if args['-f'] and (args['-f'][-4:] != '/'):
        exit("Name of the . zip file must end with '.zip'")


def get_last_filestore(string):
    files_list = string.split('/\n')
    files_list = [i.strip('PRE ') for i in files_list]
    dates = []
    for item in files_list:
        try:
            dates.append(int(item[0:8]))
        except ValueError:
            dates.append(0)
    latest = max(dates)
    return files_list[dates.index(latest)]


def get_filestore_from_amazon(bucket):
    path = 's3://' + bucket + '/filestores/'
    filestore_list = subprocess.check_output([
        'aws', 's3', 'ls', path])

    date = get_last_filestore(filestore_list)

    path = path + date + '/'

    subprocess.call('aws s3 cp ' + path + ' . --recursive', shell=True)


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
                         cmp=lambda x, y: cmp(x[0], y[0]))
    key_to_download = False
    for index in range(-1, -len(sorted_list), -1):
        if '.zip' in str(sorted_list[index][1]):
            key_to_download = sorted_list[index][1]

    if key_to_download:
        key_to_download.get_contents_to_filename(dbname + '.zip')
    else:
        raise Exception('Arquivo nao encontrado')


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


def restore_database(
        dbname, dbuser, dbpasswd, access_key, secret_key, local=False,
        remove=False, base_teste=False, download=False, old=False,
        path_to_files=False, zipped=False, zipname=False, bucket=False):

    if not path_to_files:
        path_to_files = ''

    if not bucket:
        bucket = '%s_bkp_pelican' % dbname

    if download:
        try:
            if not old:
                get_filestore_from_amazon(bucket)
            get_db_from_amazon(dbname, bucket, access_key, secret_key)
            path_to_files = ''
        except Exception as e:
            print (e)
            exit("Download from amazon failed!\
                    \n Do you have 'awscli' installed and configured?\
                    \n 'pip install awscli'\n 'aws configure'")

    if not zipname:
        zipname = dbname + '.zip'

    files = []
    if zipped or download:
        try:
            archive = ZipFile(path_to_files + zipname)
            files = archive.namelist()
            archive.extractall()
        except Exception as e:
            print (e)
            raise Exception('.zip file not found!')

    create_new_db(dbname, dbuser, dbpasswd)

    if zipped or download:
        subprocess.call('cat dump.sql | psql -h localhost -U '
                        + dbuser + ' ' + dbname, shell=True)
    else:
        subprocess.call('cat ' + path_to_files + 'dump.sql | psql -h localhost\
             -U ' + dbuser + ' ' + dbname, shell=True)

    if old:
        move_filestore(dbname, local, '')
    else:
        move_filestore(dbname, local, path_to_files)

    if remove:

        if zipped or download:
            os.remove(path_to_files + dbname + '.zip')
            for name in files:
                os.remove(name)
        else:
            os.remove(path_to_files + 'dump.sql')
            os.remove(path_to_files + 'manifest.json')

        files = os.listdir(path_to_files + 'filestore')
        for name in files:
            os.remove(name)

    if base_teste:
        change_to_homologacao(dbname, dbuser, dbpasswd)


if __name__ == '__main__':
    args = docopt(__doc__)
    check_args(args)

    restore_database(
        args['<dbname>'],
        args['<dbuser>'],
        args['<dbpasswd>'],
        args['-a'],
        args['-s'],
        args['-l'],
        args['--exclude'],
        args['-t'],
        args['-d'],
        args['-o'],
        args['-p'],
        args['--zip'],
        args['-f'],
        args['--bucket']
    )
