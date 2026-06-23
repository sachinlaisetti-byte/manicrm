import sqlite3
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import mysql.connector
except ImportError:
    mysql = None

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

# Database Selection Settings — reads from .env file
# Options: 'mongodb', 'mysql', 'sqlite'
DB_ENGINE = os.environ.get("DB_ENGINE", "sqlite").lower()


def scalar_from_row(row):
    """Return the first scalar value from a DB row regardless of type.

    Supports mappings (dict, sqlite3.Row), sequences (tuple/list), or None.
    """
    if row is None:
        return None
    try:
        from collections.abc import Mapping
        if isinstance(row, Mapping):
            for v in row.values():
                return v
    except Exception:
        pass
    # Sequence-like
    try:
        return row[0]
    except Exception:
        return row

class CRMDatabaseProxy:
    def __init__(self, db_conn, engine_type):
        self.conn = db_conn
        self.engine_type = engine_type
        
    def cursor(self):
        if self.engine_type == "mongodb":
            return MongoCursorProxy(self.conn)
        return SQLCursorProxy(self.conn.cursor(), self.engine_type == "mysql")

    def commit(self):
        if self.engine_type == "mongodb":
            return
        self.conn.commit()
        
    def rollback(self):
        if self.engine_type == "mongodb":
            return
        self.conn.rollback()
        
    def close(self):
        if self.engine_type == "mongodb":
            return
        self.conn.close()

class SQLCursorProxy:
    def __init__(self, cursor, is_mysql=False):
        self.cursor = cursor
        self.is_mysql = is_mysql

    def execute(self, query, params=None):
        if self.is_mysql and query:
            query = query.replace("?", "%s")
        if params is not None:
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)

    def executemany(self, query, params_list=None):
        if self.is_mysql and query:
            query = query.replace("?", "%s")
        if params_list is not None:
            self.cursor.executemany(query, params_list)
        else:
            self.cursor.executemany(query)

    def fetchone(self):
        result = self.cursor.fetchone()
        if result is None:
            return None

        if hasattr(result, "keys"):
            try:
                return {key: result[key] for key in result.keys()}
            except Exception:
                pass

        try:
            from collections.abc import Mapping
            if isinstance(result, Mapping):
                return result
        except Exception:
            pass

        if isinstance(result, tuple):
            cols = getattr(self.cursor, 'column_names', None)
            if not cols:
                desc = getattr(self.cursor, 'description', None)
                if desc:
                    cols = [d[0] for d in desc]
            if cols:
                try:
                    return dict(zip(cols, result))
                except Exception:
                    pass

        return result

    def fetchall(self):
        rows = self.cursor.fetchall()
        if not rows:
            return rows

        processed = []
        for r in rows:
            if hasattr(r, "keys"):
                try:
                    processed.append({key: r[key] for key in r.keys()})
                    continue
                except Exception:
                    pass

            try:
                from collections.abc import Mapping
                if isinstance(r, Mapping):
                    processed.append(r)
                    continue
            except Exception:
                pass

            if isinstance(r, tuple):
                cols = getattr(self.cursor, 'column_names', None)
                if not cols:
                    desc = getattr(self.cursor, 'description', None)
                    if desc:
                        cols = [d[0] for d in desc]
                if cols:
                    try:
                        processed.append(dict(zip(cols, r)))
                        continue
                    except Exception:
                        pass

            processed.append(r)

        return processed

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    def __getattr__(self, name):
        return getattr(self.cursor, name)

class MongoCursorProxy:
    def __init__(self, db):
        self.db = db
        self.last_results = []
        self.lastrowid = None
        
    def execute(self, query, params=None):
        query_str = query.lower().strip()
        if "select * from users" in query_str or "select id from users" in query_str:
            username = params[0] if params else "operations@manikanta.in"
            password = params[1] if params and len(params) > 1 else None
            
            criteria = {"username": username}
            if password:
                criteria["password"] = password
                
            user = self.db.users.find_one(criteria)
            if user:
                user["id"] = 1
                self.last_results = [user]
            else:
                self.last_results = []
        elif "insert into users" in query_str:
            self.db.users.insert_one({
                "full_name": params[0],
                "username": params[1],
                "password": params[2]
            })
            self.lastrowid = 1
        elif "select count(*)" in query_str:
            self.last_results = [(0,)]
            
    def fetchone(self):
        if self.last_results:
            return self.last_results[0]
        return None
        
    def fetchall(self):
        return self.last_results

DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crm.db')

def get_mongodb_connection():
    if MongoClient is None:
        print("pymongo is not installed. Falling back to SQL engines.")
        return None

    try:
        mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
        client.server_info()
        return client["manikanta_crm"]
    except Exception as e:
        print(f"MongoDB connection failed: {e}. Falling back to SQL engines.")
        return None

def get_db_connection():
    if DB_ENGINE == "mongodb":
        db = get_mongodb_connection()
        if db is not None:
            return CRMDatabaseProxy(db, "mongodb")

    if DB_ENGINE == "mysql":
        try:
            if mysql is None:
                raise ImportError("mysql-connector-python is not installed")

            host = os.environ.get("MYSQL_HOST", "localhost")
            user = os.environ.get("MYSQL_USER", "root")
            password = os.environ.get("MYSQL_PASSWORD", "root123")
            dbname = os.environ.get("MYSQL_DATABASE", "CRM")

            conn = mysql.connector.connect(host=host, user=user, password=password)
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {dbname}")
            cursor.close()
            conn.close()

            conn = mysql.connector.connect(host=host, user=user, password=password, database=dbname)
            print(f"MySQL connection established to {host}/{dbname} as user '{user}'")
            return CRMDatabaseProxy(conn, "mysql")
        except Exception as e:
            print(f"MySQL connection failed: {e}. Falling back to SQLite.")

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return CRMDatabaseProxy(conn, "sqlite")

def run_migrations(conn):
    """Dynamically applies schema extensions to safely append workflow lifecycle columns."""
    if conn.engine_type == "mongodb":
        return

    cursor = conn.cursor()
    tables_to_migrate = ["sales_orders", "delivery_assignments", "vendor_purchases"]
    
    for table in tables_to_migrate:
        try:
            if conn.engine_type == "sqlite":
                cursor.execute(f"PRAGMA table_info({table});")
                columns = [col[1] for col in cursor.fetchall()]
            else:
                cursor.execute(f"SHOW COLUMNS FROM {table};")
                columns = [col[0] for col in cursor.fetchall()]

            if "lifecycle_status" not in columns:
                print(f"Migration: Appending 'lifecycle_status' field to {table} layout.")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN lifecycle_status VARCHAR(50) DEFAULT 'PENDING';")
                conn.commit()
        except Exception as e:
            print(f"Migration alert for table {table}: {e}")

def fetch_workflow_logs(conn, limit=50):
    """Safely retrieves workflow audit log rows from the workflow_logs table."""
    logs = []
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, event_type, entity_type, entity_id, status, timestamp "
            "FROM workflow_logs ORDER BY id DESC LIMIT ?;",
            (limit,)
        )
        rows = cursor.fetchall()
        for row in rows:
            try:
                # SQLCursorProxy.fetchall() already returns dicts for SQLite/MySQL rows.
                # For any edge-case where a raw sqlite3.Row or tuple slips through,
                # convert it here without depending on app.py's dict_from_row.
                if isinstance(row, dict):
                    logs.append(row)
                elif hasattr(row, 'keys'):
                    logs.append({k: row[k] for k in row.keys()})
                elif isinstance(row, (list, tuple)):
                    cols = ['id', 'event_type', 'entity_type', 'entity_id', 'status', 'timestamp']
                    logs.append(dict(zip(cols, row)))
                else:
                    logs.append(row)
            except Exception as row_err:
                print(f"Workflow log row parse failed: {row_err}")
    except Exception as e:
        print(f"fetch_workflow_logs failed: {e}")
    return logs

def init_db():
    conn = get_db_connection()
    if conn.engine_type == "mongodb":
        print("MongoDB active. Initializing Mongo collection setups...")
        if conn.conn.users.count_documents({}) == 0:
            conn.conn.users.insert_one({
                "full_name": "Operations Admin",
                "username": "operations@manikanta.in",
                "password": "admin123"
            })
            print("MongoDB seeded default user credentials.")
        return

    cursor = conn.cursor()
    is_mysql = (conn.engine_type == "mysql")

    def run_ddl(ddl):
        if is_mysql:
            ddl = ddl.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "INT AUTO_INCREMENT PRIMARY KEY")
            ddl = ddl.replace("datetime('now', 'localtime')", "CURRENT_TIMESTAMP")
            ddl = ddl.replace("TEXT NOT NULL UNIQUE", "VARCHAR(191) NOT NULL UNIQUE")
            ddl = ddl.replace("TEXT UNIQUE", "VARCHAR(191) UNIQUE")
            ddl = ddl.replace("TEXT", "VARCHAR(255)")
        cursor.execute(ddl)

    # 1. Users Table
    run_ddl('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );
    ''')

    cursor.execute('SELECT COUNT(*) FROM users;')
    user_count = scalar_from_row(cursor.fetchone()) or 0
    if user_count == 0:
        cursor.execute("INSERT INTO users (full_name, username, password) VALUES (?, ?, ?)", 
                       ("Admin User", "admin@manikanta.in", "admin123"))
        cursor.execute("INSERT INTO users (full_name, username, password) VALUES (?, ?, ?)", 
                       ("Operations Team", "operations@manikanta.in", "admin123"))

    # 2. Customers Table
    run_ddl('''
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        company TEXT,
        phone TEXT NOT NULL,
        email TEXT,
        address TEXT,
        status TEXT DEFAULT 'Active',
        owner TEXT DEFAULT 'Unassigned',
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );
    ''')

    # 3. Dealers Table
    run_ddl('''
    CREATE TABLE IF NOT EXISTS dealers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT NOT NULL,
        address TEXT,
        type TEXT DEFAULT 'Dealer',
        credit_limit REAL DEFAULT 0.0,
        balance REAL DEFAULT 0.0,
        status TEXT DEFAULT 'Active',
        owner TEXT DEFAULT 'Unassigned',
        follow_up_date TEXT,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );
    ''')

    # 4. Products Table
    run_ddl('''
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku_id TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        unit_price REAL NOT NULL,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );
    ''')

    # 5. Warehouse Stock Table
    run_ddl('''
    CREATE TABLE IF NOT EXISTS warehouse_stock (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        quantity INTEGER DEFAULT 0,
        safety_threshold INTEGER DEFAULT 10,
        bin_location TEXT,
        last_updated TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY(product_id) REFERENCES products(id)
    );
    ''')

    # 6. Sales Orders Table
    run_ddl('''
    CREATE TABLE IF NOT EXISTS sales_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dealer_id INTEGER NOT NULL,
        order_date TEXT DEFAULT (datetime('now', 'localtime')),
        total_amount REAL NOT NULL,
        payment_status TEXT DEFAULT 'Pending',
        lifecycle_status VARCHAR(50) DEFAULT 'PENDING',
        FOREIGN KEY(dealer_id) REFERENCES dealers(id)
    );
    ''')

    # 7. Sales Order Items Table
    run_ddl('''
    CREATE TABLE IF NOT EXISTS sales_order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        FOREIGN KEY(order_id) REFERENCES sales_orders(id),
        FOREIGN KEY(product_id) REFERENCES products(id)
    );
    ''')

    # 8. Delivery Assignments Table
    run_ddl('''
    CREATE TABLE IF NOT EXISTS delivery_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        delivery_person TEXT NOT NULL,
        vehicle_no TEXT NOT NULL,
        route TEXT NOT NULL,
        status TEXT DEFAULT 'Pending',
        assignment_date TEXT DEFAULT (datetime('now', 'localtime')),
        lifecycle_status VARCHAR(50) DEFAULT 'PENDING'
    );
    ''')

    # 9. Vendor Purchases Table
    run_ddl('''
    CREATE TABLE IF NOT EXISTS vendor_purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_name TEXT NOT NULL,
        purchase_date TEXT DEFAULT (datetime('now', 'localtime')),
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_cost REAL NOT NULL,
        total_amount REAL NOT NULL,
        status TEXT DEFAULT 'Paid',
        lifecycle_status VARCHAR(50) DEFAULT 'PENDING'
    );
    ''')

    # 10. Followups Scheduler Table
    run_ddl('''
    CREATE TABLE IF NOT EXISTS follow_ups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        notes TEXT,
        scheduled_date TEXT NOT NULL,
        priority TEXT DEFAULT 'Medium',
        status TEXT DEFAULT 'Pending'
    );
    ''')

    # 11. Workflow Logs Table
    run_ddl('''
    CREATE TABLE IF NOT EXISTS workflow_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        timestamp TEXT DEFAULT (datetime('now', 'localtime'))
    );
    ''')

    # 12. Follow-up Notes Table
    run_ddl('''
    CREATE TABLE IF NOT EXISTS follow_up_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dealer_id INTEGER NOT NULL,
        note TEXT NOT NULL,
        contact_date TEXT DEFAULT (datetime('now', 'localtime')),
        next_follow_up TEXT,
        owner TEXT NOT NULL
    );
    ''')

    conn.commit()
    
    # Run structural migrations to repair live records
    run_migrations(conn)
    conn.close()

if __name__ == "__main__":
    init_db()