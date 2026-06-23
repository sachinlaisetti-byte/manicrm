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
    """Dynamically applies schema extensions to safely append missing columns."""
    if conn.engine_type == "mongodb":
        return

    import sqlite3
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

    # Migrate products table — add missing columns if not present
    try:
        if conn.engine_type == "sqlite":
            cursor.execute("PRAGMA table_info(products);")
            prod_cols = {col[1] for col in cursor.fetchall()}
        else:
            cursor.execute("SHOW COLUMNS FROM products;")
            prod_cols = {col[0] for col in cursor.fetchall()}

        for col_name, col_def in [("sku", "TEXT"), ("price", "REAL"), ("cost", "REAL")]:
            if col_name not in prod_cols:
                print(f"Migration: Adding '{col_name}' column to products table.")
                cursor.execute(f"ALTER TABLE products ADD COLUMN {col_name} {col_def};")
                conn.commit()
    except Exception as e:
        print(f"Migration alert for products table: {e}")

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

def seed_demo_data(conn):
    if conn.engine_type == "mongodb":
        return
    cursor = conn.cursor()

    # Only seed if products table is empty
    cursor.execute("SELECT COUNT(*) AS cnt FROM products")
    if scalar_from_row(cursor.fetchone()) > 0:
        return

    print("Seeding demo data...")

    # ── Products ──
    products = [
        ("SKU-CMT-001", "SKU-CMT-001", "UltraTech Cement 53 Grade", "Cement", 380.0, 380.0, 320.0),
        ("SKU-CMT-002", "SKU-CMT-002", "ACC Cement 43 Grade", "Cement", 350.0, 350.0, 295.0),
        ("SKU-STL-001", "SKU-STL-001", "JSW Steel Rebar 12mm", "Steel", 720.0, 720.0, 610.0),
        ("SKU-STL-002", "SKU-STL-002", "Tata TMT Bar 16mm", "Steel", 750.0, 750.0, 640.0),
        ("SKU-FIN-001", "SKU-FIN-001", "Birla White Wall Putty", "Finishing", 280.0, 280.0, 220.0),
        ("SKU-PNT-001", "SKU-PNT-001", "Asian Paint Royale (10L)", "Paint", 450.0, 450.0, 380.0),
        ("SKU-PNT-002", "SKU-PNT-002", "Nippon Paint Weatherproof (20L)", "Paint", 520.0, 520.0, 440.0),
        ("SKU-TLE-001", "SKU-TLE-001", "Kajaria Vitrified Tiles 2x2", "Tiles", 680.0, 680.0, 560.0),
        ("SKU-TLE-002", "SKU-TLE-002", "Somany Floor Tiles 1x1", "Tiles", 420.0, 420.0, 350.0),
        ("SKU-PLM-001", "SKU-PLM-001", "Jaquar CPVC Pipe 1inch", "Plumbing", 180.0, 180.0, 130.0),
        ("SKU-BTH-001", "SKU-BTH-001", "Hindware Sanitaryware Set", "Bathroom", 1200.0, 1200.0, 980.0),
        ("SKU-ELC-001", "SKU-ELC-001", "Polycab Wire 1.5sqmm (90m)", "Electrical", 95.0, 95.0, 72.0),
    ]
    for sku_id, sku, name, cat, up, price, cost in products:
        cursor.execute(
            "INSERT INTO products (sku_id, sku, name, category, unit_price, price, cost) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sku_id, sku, name, cat, up, price, cost)
        )

    # ── Warehouse Stock ──
    stock = [(1, 500, 50, "A1"), (2, 300, 40, "A2"), (3, 200, 20, "B1"), (4, 150, 15, "B2"),
             (5, 400, 30, "C1"), (6, 100, 10, "C2"), (7, 80, 8, "D1"), (8, 250, 25, "D2"),
             (9, 180, 18, "E1"), (10, 600, 60, "E2"), (11, 40, 5, "F1"), (12, 300, 30, "F2")]
    for pid, qty, thr, bin_loc in stock:
        cursor.execute(
            "INSERT INTO warehouse_stock (product_id, quantity, safety_threshold, bin_location) VALUES (?, ?, ?, ?)",
            (pid, qty, thr, bin_loc)
        )

    # ── Dealers ──
    dealers = [
        ("Sri Sai Cement Traders", "srisai@email.com", "9000000001", "Guntur, AP", "Dealer", 500000.0, 125000.0, "Active", "Srinivas", "2026-08-15"),
        ("Venkateswara Steel Corp", "venkateswara@email.com", "9000000002", "Vijayawada, AP", "Dealer", 800000.0, 210000.0, "Active", "Rajesh", "2026-08-10"),
        ("Krishna Building Materials", "krishna@email.com", "9000000003", "Visakhapatnam, AP", "Dealer", 300000.0, 45000.0, "Active", "Srinivas", "2026-07-25"),
        ("Anjani Hardware & Sanitary", "anjani@email.com", "9000000004", "Kakinada, AP", "Retailer", 100000.0, 12000.0, "Active", "Kalyan", "2026-08-20"),
        ("Priya Infrastructure", "priya@email.com", "9000000005", "Rajahmundry, AP", "Dealer", 600000.0, 89000.0, "Active", "Rajesh", None),
        ("Ganesh Plywood & Hardware", "ganesh@email.com", "9000000006", "Eluru, AP", "Retailer", 75000.0, 5000.0, "Active", "Kalyan", "2026-08-05"),
        ("Lakshmi Cement Agency", "lakshmi@email.com", "9000000007", "Ongole, AP", "Dealer", 400000.0, 98000.0, "Active", "Srinivas", "2026-07-30"),
        ("Durga TMT & Steel", "durga@email.com", "9000000008", "Nellore, AP", "Dealer", 350000.0, 110000.0, "Blocked", "Rajesh", "2026-06-15"),
        ("Sai Ram Enterprises", "sairam@email.com", "9000000009", "Tirupati, AP", "Dealer", 550000.0, 76000.0, "Active", "Kalyan", None),
        ("Navayuga Traders", "navayuga@email.com", "9000000010", "Kurnool, AP", "Retailer", 125000.0, 0.0, "Active", "Srinivas", "2026-09-01"),
    ]
    for d in dealers:
        cursor.execute(
            "INSERT INTO dealers (name, email, phone, address, type, credit_limit, balance, status, owner, follow_up_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            d
        )

    # ── Customers ──
    customers = [
        ("R. Venkata Rao", "Venkat Constructions", "9876543210", "rv@email.com", "Guntur"),
        ("M. Surya Prakash", "Surya Builders", "9876543211", "surya@email.com", "Vijayawada"),
        ("K. Naga Raju", "Naga Constructions", "9876543212", "naga@email.com", "Visakhapatnam"),
        ("D. Srinivas Rao", "Srinivas Estates", "9876543213", "dsr@email.com", "Rajahmundry"),
        ("P. Rama Krishna", "RK Developers", "9876543214", "rk@email.com", "Kakinada"),
        ("S. V. Prasad", "Prasad & Sons", "9876543215", "svp@email.com", "Nellore"),
        ("G. Narasimha", "Narasimha Infrastructure", "9876543216", "gn@email.com", "Tirupati"),
        ("T. Subba Rao", "Subba Rao Associates", "9876543217", "tsr@email.com", "Eluru"),
        ("A. Chandra Sekhar", "Chandra Constructions", "9876543218", "acs@email.com", "Ongole"),
        ("B. Madhu Sudhan", "Madhu Developers", "9876543219", "bms@email.com", "Kurnool"),
    ]
    for c in customers:
        cursor.execute(
            "INSERT INTO customers (name, company, phone, email, address) VALUES (?, ?, ?, ?, ?)",
            c
        )

    # ── Vendor Purchases ──
    from datetime import datetime, timedelta
    base = datetime.now()
    purchases = []
    vendor_purchase_data = [
        ("UltraTech Supply Co", 1, 1000, 300.0, "2026-05-10"),
        ("ACC Distributors", 2, 800, 280.0, "2026-05-12"),
        ("JSW Steel Depot", 3, 500, 590.0, "2026-05-15"),
        ("Tata Steel Supply", 4, 300, 620.0, "2026-05-18"),
        ("Birla White Dealer", 5, 600, 210.0, "2026-05-20"),
        ("Asian Paint Wholesale", 6, 200, 370.0, "2026-05-22"),
        ("Nippon Paint Logistics", 7, 150, 430.0, "2026-05-25"),
        ("Kajaria Tile Mart", 8, 400, 540.0, "2026-05-28"),
        ("Somany Showroom", 9, 350, 340.0, "2026-06-01"),
        ("Jaquar Distributors", 10, 800, 125.0, "2026-06-03"),
        ("Hindware Bath Fittings", 11, 100, 960.0, "2026-06-05"),
        ("Polycab Cable Co", 12, 500, 68.0, "2026-06-07"),
    ]
    for vendor, pid, qty, unit_cost, date_str in vendor_purchase_data:
        total = qty * unit_cost
        cursor.execute(
            "INSERT INTO vendor_purchases (vendor_name, product_id, quantity, unit_cost, total_amount, status, purchase_date) VALUES (?, ?, ?, ?, ?, 'Paid', ?)",
            (vendor, pid, qty, unit_cost, total, date_str)
        )

    # ── Sales Orders ──
    orders_data = [
        (1, "2026-05-20", "Paid", [
            (1, 100, 380.0), (5, 50, 280.0)
        ]),
        (2, "2026-05-25", "Paid", [
            (3, 80, 720.0), (4, 40, 750.0)
        ]),
        (3, "2026-06-01", "Pending", [
            (2, 60, 350.0), (8, 30, 680.0)
        ]),
        (4, "2026-06-05", "Paid", [
            (6, 25, 450.0), (7, 15, 520.0)
        ]),
        (5, "2026-06-10", "Pending", [
            (1, 200, 380.0), (3, 50, 720.0), (10, 100, 180.0)
        ]),
        (6, "2026-06-15", "Paid", [
            (11, 10, 1200.0), (12, 60, 95.0)
        ]),
        (7, "2026-06-18", "Pending", [
            (5, 80, 280.0), (9, 40, 420.0)
        ]),
    ]
    for dealer_id, date_str, pay_status, items in orders_data:
        total = sum(q * up for _, q, up in items)
        cursor.execute(
            "INSERT INTO sales_orders (dealer_id, total_amount, payment_status, order_date) VALUES (?, ?, ?, ?)",
            (dealer_id, total, pay_status, date_str)
        )
        order_id = cursor.lastrowid
        for pid, qty, up in items:
            cursor.execute(
                "INSERT INTO sales_order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                (order_id, pid, qty, up)
            )

    # ── Delivery Assignments ──
    deliveries = [
        (1, "Srinivas", "AP-32-TC-1234", "Guntur Route", "Delivered", "2026-05-22"),
        (2, "Rajesh", "AP-32-TC-5678", "Vijayawada Route", "Delivered", "2026-05-27"),
        (3, "Kalyan", "AP-32-TC-9012", "Visakhapatnam Route", "In Transit", "2026-06-03"),
        (4, "Srinivas", "AP-32-TC-3456", "Kakinada Route", "Delivered", "2026-06-07"),
        (5, "Rajesh", "AP-32-TC-7890", "Rajahmundry Route", "Pending", "2026-06-14"),
        (6, "Kalyan", "AP-32-TC-1111", "Nellore Route", "Delivered", "2026-06-17"),
        (7, "Srinivas", "AP-32-TC-2222", "Tirupati Route", "Pending", "2026-06-20"),
    ]
    for oid, person, vehicle, route, status, date_str in deliveries:
        cursor.execute(
            "INSERT INTO delivery_assignments (order_id, delivery_person, vehicle_no, route, status, assignment_date) VALUES (?, ?, ?, ?, ?, ?)",
            (oid, person, vehicle, route, status, date_str)
        )

    # ── Follow-ups ──
    followups = [
        ("Follow up on payment", "Dealer #3 has pending balance of ₹45,000", "2026-07-25", "High", "Pending"),
        ("Credit limit review", "Review credit limit increase for Dealer #2", "2026-08-10", "Medium", "Pending"),
        ("New product demo", "Schedule UltraTech Cement demo for Dealer #5", "2026-08-01", "Low", "Completed"),
        ("Quarterly meeting", "Quarterly business review with top 5 dealers", "2026-08-15", "High", "Pending"),
        ("Site visit", "Visit Dealer #1 for stock verification", "2026-07-30", "Medium", "Pending"),
    ]
    for title, notes, sched, priority, status in followups:
        cursor.execute(
            "INSERT INTO follow_ups (title, notes, scheduled_date, priority, status) VALUES (?, ?, ?, ?, ?)",
            (title, notes, sched, priority, status)
        )

    # ── Follow-up Notes ──
    fnotes = [
        (1, "Discussed pending payment of ₹1,25,000. Promised to clear by next week.", "2026-07-20", "2026-08-15", "Srinivas"),
        (2, "Requested additional steel stock. Order placed for 100 units.", "2026-07-18", "2026-08-10", "Rajesh"),
        (3, "New credit limit approved at ₹5,00,000. Documentation completed.", "2026-07-15", "2026-07-25", "Srinivas"),
        (5, "Dealer interested in new paint product line. Demo scheduled.", "2026-07-22", "2026-08-01", "Kalyan"),
        (7, "Complaint about delayed delivery resolved. Compensation provided.", "2026-07-12", None, "Rajesh"),
    ]
    for did, note, cdate, next_fu, owner in fnotes:
        cursor.execute(
            "INSERT INTO follow_up_notes (dealer_id, note, contact_date, next_follow_up, owner) VALUES (?, ?, ?, ?, ?)",
            (did, note, cdate, next_fu, owner)
        )

    # ── Workflow Logs ──
    logs = [
        ("AUTH_LOGIN", "USER", 1, "Success"),
        ("CREATE_DEALER", "DEALER", 1, "Success"),
        ("CREATE_ORDER", "ORDER", 1, "Success"),
        ("DELIVERY_COMPLETE", "DELIVERY", 1, "Success"),
        ("CREATE_PURCHASE", "PURCHASE", 1, "Success"),
        ("AUTH_LOGIN", "USER", 2, "Success"),
        ("CREATE_DEALER", "DEALER", 5, "Success"),
        ("CREATE_ORDER", "ORDER", 5, "Success"),
    ]
    for evt, ent, eid, status in logs:
        cursor.execute(
            "INSERT INTO workflow_logs (event_type, entity_type, entity_id, status) VALUES (?, ?, ?, ?)",
            (evt, ent, eid, status)
        )

    conn.commit()
    print("Demo data seeded successfully.")

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
        sku TEXT,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        unit_price REAL NOT NULL,
        price REAL,
        cost REAL,
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

    # Seed demo data if tables are empty (showcase/testing mode)
    seed_demo_data(conn)

    conn.close()

if __name__ == "__main__":
    init_db()