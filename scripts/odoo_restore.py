# -*- coding: utf-8 -*-
"""Usage: odoo_restore.py (<dbname> <dbuser> <dbpasswd>) [options]
          odoo_restore.py -h | --help

Options:
  -h --help
  -s KEY           acess key to amazon server
  -k SKEY          secret key to amazon server
  -l               local backup (change the directory of 'filestore')
  -d --docker-name name of the odoo docker
  --production     production database (don't change nfse env to 'homologacao')
  -e --exclude     exclude files after completed process
  -p PATH          path to files, if they are already downloaded
  -f FILE          name of the '.zip' archive

"""
from docopt import docopt
from datetime import datetime
import subprocess
from getpass import getuser
from psycopg2 import connect
import os
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from boto3 import resource
from zipfile import ZipFile
import uuid


def check_args(args):
    if (not args['<dbname>'] or not ['<dbuser>'] or not
            ['<dbpasswd>']):
        exit("(<dbname> <dbuser> <dbpasswd>) are required!\
                \n Use '-h' for help")

    if args['-p']:
        if (args['-p'][-1] != '/'):
            exit("Path to file must end with /")
        if not os.path.exists(args['-p']):
            exit("Path to file doesn't exist!")

    if args['-f'] and (args['-f'][-4:] != '.zip'):
        exit("Name of the . zip file must end with '.zip'")


def get_path_to_files(dbname):
    directory = '/opt/backups/dados/{}'.format(dbname)
    if not os.path.exists(os.path.join(directory, 'filestore')):
        os.makedirs(os.path.join(directory, 'filestore'))
    return directory


def get_filestore_from_amazon(dbname, dest):
    path = 's3://11.0/%s/filestore' % dbname

    method = 'aws s3 --region=us-east-1 --output=json --delete sync %s %s' % (
        path, dest
    )
    env = os.environ.copy()
    subprocess.check_call(method.split(), env=env)


def move_filestore(docker_name, dbname, local, path_to_files):
    if local:
        path = os.path.join('/home', getuser(), '.local/share/Odoo/filestore/',
                            dbname)
    else:
        path = os.path.join('/opt/dados/', docker_name, 'filestore', dbname)

    if not os.path.exists(path):
        os.makedirs(path)
    cmd = 'cp -r ' + os.path.join(
        path_to_files, 'filestore') + '/' + '. ' + path
    subprocess.check_call(cmd, shell=True)


def get_latest_aws_file(conn, dbname):
    bucket = conn.Bucket('11.0')
    objects = {}
    for obj in bucket.objects.filter(Prefix="{}/{}".format(dbname, dbname)):
        objects.update({obj.key: extract_data_from_name(obj.key)})
    return sorted(objects.items(), key=lambda x: x[1])[-1][0]


def extract_data_from_name(string):
    try:
        file_date = string[-14:-4]
    except Exception:
        return
    return datetime.strptime(file_date, '%d_%m_%Y')


def get_db_from_amazon(dbname, path, access_key, secret_key):
    conn = resource('s3', aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key)
    filename = get_latest_aws_file(conn, dbname)

    conn.Bucket('11.0').download_file(filename, os.path.join(
        path, dbname + '.zip'))


def get_new_database_cursor(dbname, dbuser, dbpasswd):
    con = connect(dbname=dbname, user=dbuser, host='127.0.0.1',
                  password=dbpasswd)
    con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return con, con.cursor()


def create_new_db(dbname, dbuser, dbpasswd):
    con, cur = get_new_database_cursor('postgres', dbuser, dbpasswd)
    try:
        cur.execute('drop database ' + dbname)
    except Exception:
        pass

    try:
        cur.execute('CREATE DATABASE ' + dbname + ' with owner ' + dbuser)
    except Exception as e:
        print(e)
        exit("Can't replace a database that is being used by other users")
    cur.close()
    con.close()


def change_to_homologacao(cur):

    try:
        cur.execute(
            "UPDATE res_company SET tipo_ambiente='2';")
    except Exception as e:
        print(u"ERROR while changing Ambiente NFe to Homologação")
        print(e)
    try:
        cur.execute(
            "UPDATE res_company SET tipo_ambiente_nfse='2' where \
tipo_ambiente_nfse='1';")
        cur.execute(
            "UPDATE res_company SET tipo_ambiente_nfse='homologacao' where \
tipo_ambiente_nfse='producao';")
    except Exception as e:
        print(u"ERROR while changing Ambiente NFSe to Homologação")
        print(e)

    cur.execute('delete from fetchmail_server')
    cur.execute('delete from ir_mail_server')


def change_database_uuid(cur):
    try:
        cur.execute("UPDATE ir_config_parameter SET value={} \
WHERE key='database.uuid';".format(str(uuid.uuid4())))
    except Exception as e:
        print(u"ERROR while changing database UUID")
        print(e)


def restore_database(args):
    path_to_files = args['-p']

    if not args['-p']:
        path_to_files = get_path_to_files(args['<dbname>'])
    else:
        path_to_files = os.path.join(path_to_files, args['<dbname>'])

    if not args['-f']:
        print("Downloading filestore from AWS")
        get_filestore_from_amazon(args['<dbname>'],
                                  os.path.join(path_to_files, 'filestore'))
        print("Download database from AWS")
        get_db_from_amazon(
            args['<dbname>'], path_to_files, args['-s'], args['-k'])
        args['-f'] = args['<dbname>'] + '.zip'

    try:
        print("Unziping database file")
        archive = ZipFile(os.path.join(path_to_files, args['-f']))
        archive.extractall(path_to_files)

    except Exception as e:
        print(e)
        raise Exception('.zip file not found!')

    print("Creating new database")
    dbname = args['<dbname>'] + datetime.now().strftime('%d_%m_%Y')

    create_new_db(dbname, args['<dbuser>'], args['<dbpasswd>'])

    db_connection, db_cursor = get_new_database_cursor(
        dbname, args['<dbuser>'], args['<dbpasswd>'])

    arguments = ['psql',
                 '-h127.0.0.1',
                 '-q',
                 '-d{}'.format(dbname),
                 '-f{}'.format(os.path.join(path_to_files, 'dump.sql')),
                 '-U{}'.format(args['<dbuser>']),
                 '-W']

    print("Restore the database file")
    subprocess.check_call(arguments)

    print("Moving filestore for the new database")
    move_filestore(args['--docker-name'], dbname, args['-l'], path_to_files)

    if args['--exclude']:

        try:
            os.remove(os.path.join(path_to_files, args['-f']))
            os.remove(os.path.join(path_to_files, 'dump.sql'))
        except Exception:
            pass

    if not args['--production']:

        print("Adjusting parameters for testing environment")
        change_to_homologacao(db_cursor)

        print("Changing database UUID")
        change_database_uuid(db_cursor)

    db_cursor.close()
    db_connection.close()


if __name__ == '__main__':
    args = docopt(__doc__)
    check_args(args)

    restore_database(args)
