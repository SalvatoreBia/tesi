import sqlite3
import datetime


class Database:
    _instance = None
    _LIMIT = 20

    def __new__(cls):
        if cls._instance is None:
            Database._instance = super(Database, cls).__new__(cls)
        return Database._instance

    def __init__(self):
        self.DUMP = 'resources/config/dump.txt'
        self.DB = 'resources/archive/db.json'
        self.PS_SIZE = 41
        self.PS_COMPPARS_SIZE = 34
        self.conn = None
        self.cursor = None
        self._setup()

    def _setup(self):
        self.conn = sqlite3.connect(self.DB, check_same_thread=False)
        self.cursor = self.conn.cursor()
        with open(self.DUMP, 'r') as file:
            statements = file.read().strip().split('~')
            for st in statements:
                self.cursor.execute(st)
        self.conn.commit()

    def execute_query(self, query, params=None):
        if params is None:
            params = []
        self.cursor.execute(query, params)
        self.conn.commit()
        return self.cursor

    @staticmethod
    def limit():
        return Database._LIMIT

    def close(self):
        self.conn.close()


db = Database()


def insert(table: str, row: list):
    try:
        query = (
            f'INSERT INTO {table} VALUES '
            f'({','.join(['?'] * (db.PS_SIZE if table == 'ps' else db.PS_COMPPARS_SIZE))})'
        )
        res = db.execute_query(query, row)
        return res
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return False


def set_current_date():
    date = datetime.datetime.now().strftime('%Y-%m-%d')
    try:
        query = 'UPDATE pscomppars SET last_write = ?'
        res = db.execute_query(query, [date])
        return True
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return False


def get_last_date():
    try:
        query = 'SELECT last_write FROM pscomppars LIMIT 1'
        res = db.execute_query(query)
        return res.fetchone()[0] if res else None
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return None


def delete_planet(name: str):
    try:
        query = f'SELECT id FROM pscomppars WHERE pl_name = ?'
        res = db.execute_query(query, [name])
        row_id = res.fetchone()[0] if res else -1
        if row_id == -1:
            return False

        query = f'DELETE FROM ps WHERE id = ?'
        res = db.execute_query(query, [row_id])
        query = f'DELETE FROM pscomppars WHERE id = ?'
        res = db.execute_query(query, [row_id])
        return True
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return False


def custom_query(fields: str, constraints):
    try:
        query = f'SELECT {fields} FROM ps'
        if constraints is not None:
            query += f' WHERE {constraints}'
        query += ' LIMIT 200'
        res = db.execute_query(query)
        return [row for row in res.fetchall()] if res else None
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return None


def count(table: str):
    try:
        query = f'SELECT COUNT(*) FROM {table}'
        res = db.execute_query(query)
        return res.fetchone()[0] if res else -1
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return -1


def disc_in(year: int):
    try:
        query = 'SELECT COUNT(DISTINCT pl_name) FROM ps WHERE disc_year = ?'
        res = db.execute_query(query, [year])
        return res.fetchone()[0] if res else -1
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return -1


def search_pl(start: int, end: int, keyword=None):
    try:
        query = 'SELECT pl_name FROM pscomppars'
        res = None
        if keyword is not None:
            query += ' WHERE LOWER(REPLACE(pl_name, " ", "")) LIKE ?'
            query += ' ORDER BY pl_name LIMIT ? OFFSET ?'
            res = db.execute_query(query, [f'%{keyword}%', end-start, start])
        else:
            query += ' ORDER BY pl_name LIMIT ? OFFSET ?'
            res = db.execute_query(query, [end-start, start])
        return [row[0] for row in res.fetchall()] if res else None
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return None


def count_like(keyword: str):
    try:
        if keyword is None:
            return count('pscomppars')
        else:
            query = 'SELECT COUNT(id) FROM pscomppars WHERE LOWER(REPLACE(pl_name, " ", "")) LIKE ?'
            res = db.execute_query(query, [f'%{keyword}%'])
            return res.fetchone()[0] if res else None
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return None


def count_rows_per_pl(keyword: str):
    try:
        if keyword is None:
            return count('ps')
        else:
            query = 'SELECT COUNT(id) FROM ps WHERE LOWER(REPLACE(pl_name, " ", "")) LIKE ?'
            res = db.execute_query(query, [f'%{keyword}%'])
            return res.fetchone()[0] if res else None
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return None


def get_pl_by_name(keyword: str):
    try:
        query = f'SELECT * FROM pscomppars WHERE LOWER(REPLACE(pl_name, " ", "")) LIKE ? LIMIT {Database.limit()}'
        cres = True if count_rows_per_pl(keyword) >= Database.limit() else False
        res = db.execute_query(query, [f'%{keyword}%'])
        rows = [row for row in res.fetchall()] if res else []
        return rows, cres
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return None, None


def get_field_values(keyword: str):
    try:
        query = f'SELECT {keyword} FROM pscomppars WHERE {keyword} != ""'
        res = db.execute_query(query)
        return [float(row[0]) for row in res.fetchall()] if res else None
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return None


def get_coordinates(planet: str):
    try:
        query = f'SELECT rastr, decstr FROM pscomppars WHERE LOWER(REPLACE(pl_name, " ", "")) = ?'
        res = db.execute_query(query, [planet])
        return res.fetchone()
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return None, None


def get_random_planet():
    try:
        query = (
            'SELECT pl_name, pl_eqt, pl_insol, pl_bmasse, pl_orbper, pl_orbeccen, st_teff, pl_refname '
            'FROM PS ORDER BY RANDOM() LIMIT 1'
        )
        res = db.execute_query(query)
        return res.fetchone() if res else None
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return None


def get_nearest_planets():
    try:
        query = (
            'SELECT pl_name, CAST(sy_dist AS REAL)'
            'FROM pscomppars '
            'WHERE sy_dist IS NOT NULL AND sy_dist != "" '
            'GROUP BY pl_name '
            'ORDER BY MIN(CAST(sy_dist AS REAL)) ASC '
            'LIMIT 3'
        )
        res = db.execute_query(query)
        return res.fetchall() if res else None
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return None


def get_farthest_planets():
    try:
        query = (
            'SELECT pl_name, CAST(sy_dist AS REAL)'
            'FROM pscomppars '
            'WHERE sy_dist IS NOT NULL AND sy_dist != "" '
            'GROUP BY pl_name '
            'ORDER BY MIN(CAST(sy_dist AS REAL)) DESC '
            'LIMIT 3'
        )
        res = db.execute_query(query)
        return res.fetchall() if res else None
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return None


def get_names_list():
    try:
        query = 'SELECT pl_name FROM pscomppars'
        res = db.execute_query(query)
        return [row[0] for row in res.fetchall()] if res else []
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return None
