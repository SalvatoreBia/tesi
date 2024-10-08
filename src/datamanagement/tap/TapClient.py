import requests
import csv
import io
import src.datamanagement.database.DbManager as db

BASE_URL = 'https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query='
FIELDS_PATH = 'resources/config/fields.txt'
ps_fields = ''
pscomppars_fields = ''


def load_fields():
    global ps_fields
    global pscomppars_fields
    with open(FIELDS_PATH, 'r') as file:
        for line in file:
            temp = line.strip()
            ps_fields += temp.split(':')[0] + ','
            if not temp.endswith('~'):
                pscomppars_fields += temp.split(':')[0] + ','
        ps_fields = ps_fields[:-1]
        pscomppars_fields = pscomppars_fields[:-1]


def cast(value):
    try:
        if '.' in value:
            return float(value)
        elif value == '':
            return None
        else:
            return int(value)
    except ValueError:
        return value


def form_rows(csv_string):
    f = io.StringIO(csv_string)
    reader = csv.reader(f)
    next(reader)
    matrix = []
    for row in list(reader):
        matrix.append([cast(value) for value in row])
    return matrix


def form_list(csv_string):
    f = io.StringIO(csv_string)
    reader = csv.reader(f)
    next(reader)
    return [row[0] for row in list(reader)]


def _check_names_list(tap_list, db_list):
    temp = set(tap_list)
    to_delete = list(db_list - temp)
    missing = list(temp - db_list)
    return missing, to_delete


def update():
    pscomppars_count = db.count('pscomppars')
    count_query = 'select+count%28*%29+from+pscomppars&format=csv'
    count_response = requests.get(BASE_URL + count_query)
    tap_count = int(count_response.text.split('\n')[1])
    ps_count = db.count('ps')
    actually_updated = False

    # get all table if it's empty
    if pscomppars_count == 0:
        query = f'select+{pscomppars_fields}+from+pscomppars&format=csv'
        response = requests.get(BASE_URL + query)
        for row in form_rows(response.text):
            db.insert('pscomppars', [None] + row + [None, None])
            actually_updated = True

    # if the counts don't match, the table only needs an update
    elif pscomppars_count != tap_count:
        query = 'select+pl_name+from+pscomppars&format=csv'
        response = requests.get(BASE_URL + query)
        names_list = form_list(response.text)
        db_names_list = db.get_names_set()
        to_get, to_delete = _check_names_list(names_list, db_names_list)
        if len(to_get) > 0:
            fmt_list = ','.join(f"'{name}'" for name in to_get)
            query = f'select+{pscomppars_fields}+from+pscomppars+where+pl_name+in+%28{fmt_list}%29&format=csv'
            response = requests.get(BASE_URL + query)
            for row in form_rows(response.text):
                db.insert('pscomppars', [None] + row + [None, None])
                actually_updated = True
        if len(to_delete) > 0:
            for pl in to_delete:
                db.delete_planet(pl)
                actually_updated = True

    # get all table if it's empty
    if ps_count == 0:
        query = f'select+{ps_fields}+from+ps&format=csv'
        response = requests.get(BASE_URL + query)
        for row in form_rows(response.text):
            db.insert('ps', [None] + row)
            actually_updated = True

    # or update the table
    # TODO ha eliminato tuple???
    else:
        last_write = db.get_last_date()
        query = f'select+distinct+pl_name+from+ps+where+releasedate%3E=\'{last_write}\'+or+rowupdate%3E=\'{last_write}\'&format=csv'
        response = requests.get(BASE_URL + query)
        to_delete = form_list(response.text)
        fmt_list = ','.join(f"'{elem}'" for elem in to_delete)
        query = f'select+{ps_fields}+from+ps+where+pl_name+in+%28{fmt_list}%29&format=csv'
        if len(to_delete) > 0:
            response = requests.get(BASE_URL + query)
            rows = form_rows(response.text)
            for planet in to_delete:
                db.delete_planet(planet, ps_only=True)

            for row in rows:
                db.insert('ps', [None] + row)
            actually_updated = True

    if actually_updated:
        db.set_current_date()
        print('updated')
