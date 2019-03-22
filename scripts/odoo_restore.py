# -*- coding: utf-8 -*-
"""Usage: odoo_restore.py (<dbname> <dbuser> <dbpasswd>) [options]
          odoo_restore.py -h | --help

Options:
  -h --help
  -d DBTEST        name database to create
  -t BACKUPDATE    backup date to restore (dd-MM-yyyy)
  -s KEY           acess key to amazon server
  -k SKEY          secret key to amazon server
  -l               local backup (change the directory of 'filestore')
  -c --docker-name name of the odoo docker
  --production     production database (don't change nfse env to 'homologacao')
  -p PATH          path to files, if they are already downloaded
"""

import re
import os
import uuid
import hashlib
import subprocess
from docopt import docopt
from datetime import datetime, date
from getpass import getuser
from psycopg2 import connect
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from boto3 import resource
from zipfile import ZipFile


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


def get_path_to_files(dbname, local):
    if local:
        directory = os.path.join('/home', getuser(), 'backup', dbname)
    else:
        directory = '/opt/backups/dados/{}/'.format(dbname)
    if not os.path.exists(os.path.join(directory, 'filestore')):
        os.makedirs(os.path.join(directory, 'filestore'))
    return directory


def get_backup_from_amazon(dbname, bkp_date, save_to, access_key, secret_key,
                           filestore=False):
    bucket_name = re.sub('[^0-9a-z]', '-', dbname)
    hash = hashlib.md5(bucket_name.encode())
    bucket_name += '-' + hash.hexdigest()[:8]

    conn = resource('s3', aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key)

    filename = '%s_%s.zip' % (dbname, bkp_date.strftime('%d_%m_%Y'))
    if filestore:
        filename = '%s_%s_filestore.zip' % (
            dbname, bkp_date.strftime('%d_%m_%Y'))
    conn.Bucket(bucket_name).download_file(filename, save_to)


def move_filestore(docker_name, dbname, local, path_to_files):
    complete_name = dbname + datetime.now().strftime('%d_%m_%Y')
    if local:
        path = os.path.join('/home', getuser(), '.local/share/Odoo/filestore/',
                            complete_name)
    else:
        path = os.path.join(
            '/opt/dados/', docker_name, 'filestore', complete_name)

    if not os.path.exists(path):
        os.makedirs(path)
    cmd = 'cp -r ' + os.path.join(
        path_to_files, 'filestore', dbname) + '/' + '. ' + path
    subprocess.check_call(cmd, shell=True)


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
        cur.execute("UPDATE ir_config_parameter SET value='{}' \
WHERE key='database.uuid';".format(str(uuid.uuid4())))
    except Exception as e:
        print(u"ERROR while changing database UUID")
        print(e)


def delete_enterprise_code(cur):
    try:
        cur.execute("DELETE from ir_config_parameter WHERE key='database.enterprise_code';")
    except Exception as e:
        print(u"ERROR while deleting enterprise code")
        print(e)


def restore_database(args):
    path_to_files = args['-p']
    bkp_date = date.today()
    if args['-t']:
        bkp_date = datetime.strptime(args['-t'], '%d-%m-%Y')

    # TODO Melhorar aqui
    if not args['-p']:
        path_to_files = get_path_to_files(args['<dbname>'], args['-l'])
    else:
        path_to_files = os.path.join(path_to_files, args['<dbname>'])

    print("Downloading filestore from AWS")
    filestore = os.path.join(path_to_files, 'filestore.zip')
    get_backup_from_amazon(
        args['<dbname>'], bkp_date, filestore, args['-s'], args['-k'],
        filestore=True)

    print("Download database from AWS")
    database = os.path.join(path_to_files, 'database.zip')
    get_backup_from_amazon(
        args['<dbname>'], bkp_date, database, args['-s'], args['-k'])
    args['-f'] = args['<dbname>'] + '.zip'
    print(args)
    try:
        print("Unziping database file")
        archive = ZipFile(database)
        archive.extractall(path_to_files)
        print("Unziping filestore file")
        archive = ZipFile(filestore)
        archive.extractall(path_to_files + 'filestore')

    except Exception as e:
        print(e)
        raise Exception('.zip file not found!')

    print("Creating new database")

    dbname = (
        args['<dbname>'].split('-')[0] +
        datetime.now().strftime('%d_%m_%Y'))

    create_new_db(dbname, args['<dbuser>'], args['<dbpasswd>'])

    db_connection, db_cursor = get_new_database_cursor(
        dbname, args['<dbuser>'], args['<dbpasswd>'])

    arguments = ['psql',
                 '-h', '127.0.0.1',
                 '-q',
                 '-d', '{}'.format(dbname),
                 '-f', '{}'.format(os.path.join(path_to_files, 'dump.sql')),
                 '-U', '{}'.format(args['<dbuser>']),
                 '-W']

    print("Restore the database file")
    subprocess.check_call(arguments)

    print("Moving filestore for the new database")
    move_filestore(args['--docker-name'], args['<dbname>'].split('-')[0], args['-l'], path_to_files)

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

        print("Deleting enterprise code")
        delete_enterprise_code(db_cursor)

    db_cursor.close()
    db_connection.close()


if __name__ == '__main__':
    args = docopt(__doc__)
    check_args(args)

    restore_database(args)
