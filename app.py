from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import traceback
import sqlite3
import os
import mimetypes
from datetime import datetime

# Load .env file BEFORE importing database module so DB_ENGINE and credentials are available
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass  # dotenv not installed — rely on system environment variables

from database import get_db_connection, scalar_from_row, init_db, fetch_workflow_logs

# Force correct MIME types for Windows environments
mimetypes.add_type('text/css', '.css')
mimetypes.add_type('application/javascript', '.js')

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    traceback.print_exc()
    return jsonify({"success": False, "error": str(e)}), 500

# --- HELPER FUNCTIONS ---
def dict_from_row(row):
    if not row:
        return None
    if hasattr(row, "keys"):
        try:
            return {key: row[key] for key in row.keys()}
        except Exception:
            pass
    try:
        from collections.abc import Mapping, Sequence
        # If it's already mapping-like, make a plain dict copy
        if isinstance(row, Mapping):
            return dict(row)

        # If it's a sequence of (key, value) pairs, safe to convert
        if isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
            if len(row) > 0 and isinstance(row[0], Sequence) and len(row[0]) == 2:
                try:
                    return dict(row)
                except Exception:
                    pass
    except Exception:
        pass

    # Fallback: return the row as-is (caller should handle unexpected shapes)
    return row

def log_workflow_event(cursor, event_type, entity_type, entity_id, status="Success"):
    """Inserts an audit log trail into workflow_logs table"""
    try:
        cursor.execute('''
            INSERT INTO workflow_logs (event_type, entity_type, entity_id, status)
            VALUES (?, ?, ?, ?);
        ''', (event_type, entity_type, entity_id, status))
    except Exception as e:
        print(f"Logging workflow event failed: {str(e)}")

# --- UI SERVING ---
@app.route('/')
def index():
    return render_template('index.html')

# --- AUTHENTICATION API ---
@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        google_credential = data.get('google_credential')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Google sign-in wrapper mock authentication
        if google_credential:
            # In a real environment, verify token. Here we simulate successful user check
            cursor.execute("SELECT * FROM users WHERE username = 'operations@manikanta.in';")
            user = dict_from_row(cursor.fetchone())
            conn.close()
            return jsonify({
                "success": True,
                "message": "Google Authentication Successful",
                "user": {
                    "full_name": user['full_name'] if user else "Google User",
                    "username": "google_auth_account"
                }
            })

        # Native Authentication
        if not username or not password:
            conn.close()
            return jsonify({"success": False, "error": "Username and Password are required."}), 400

        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?;", (username, password))
        user = dict_from_row(cursor.fetchone())
        
        if user:
            log_workflow_event(cursor, "AUTH_LOGIN", "USER", user['id'], "Success")
            conn.commit()
            conn.close()
            return jsonify({
                "success": True,
                "message": "Authentication Successful",
                "user": {
                    "full_name": user['full_name'],
                    "username": user['username']
                }
            })
        else:
            conn.close()
            return jsonify({"success": False, "error": "Invalid username or password."}), 401
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    try:
        data = request.json
        full_name = data.get('full_name')
        username = data.get('username')
        password = data.get('password')

        if not full_name or not username or not password:
            return jsonify({"success": False, "error": "Full Name, Username and Password are required."}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check existing user
        cursor.execute("SELECT id FROM users WHERE username = ?;", (username,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"success": False, "error": "Username is already registered."}), 400

        cursor.execute("INSERT INTO users (full_name, username, password) VALUES (?, ?, ?);", (full_name, username, password))
        user_id = cursor.lastrowid
        log_workflow_event(cursor, "CREATE", "USER", user_id, "Success")
        conn.commit()
        conn.close()

        return jsonify({"success": True, "message": "User registered successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# --- CUSTOMERS ENDPOINTS ---
@app.route('/api/customers', methods=['GET', 'POST'])
def manage_customers():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            cursor.execute("SELECT * FROM customers ORDER BY name ASC;")
            customers = [dict_from_row(row) for row in cursor.fetchall()]
            conn.close()
            return jsonify({"success": True, "data": customers})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500

    elif request.method == 'POST':
        try:
            data = request.json
            cid = data.get('id')
            name = data.get('name')
            company = data.get('company')
            phone = data.get('phone')
            email = data.get('email')
            address = data.get('address')
            status = data.get('status', 'Active')
            owner = data.get('owner', 'Unassigned')

            if not name or not phone:
                return jsonify({"success": False, "error": "Name and Phone are required."}), 400

            if cid:  # UPDATE
                cursor.execute('''
                    UPDATE customers 
                    SET name = ?, company = ?, phone = ?, email = ?, address = ?, status = ?, owner = ?
                    WHERE id = ?;
                ''', (name, company, phone, email, address, status, owner, cid))
                log_workflow_event(cursor, "UPDATE", "CUSTOMER", cid, "Success")
                msg = "Customer updated successfully."
            else:    # CREATE
                cursor.execute('''
                    INSERT INTO customers (name, company, phone, email, address, status, owner)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                ''', (name, company, phone, email, address, status, owner))
                cid = cursor.lastrowid
                log_workflow_event(cursor, "CREATE", "CUSTOMER", cid, "Success")
                msg = "Customer registered successfully."

            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": msg, "id": cid})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500

# --- DEALER REGISTER ENDPOINT ---
@app.route('/api/dealers/register', methods=['POST'])
def register_dealer():
    try:
        data = request.json
        did = data.get('id')
        # Map firm_name to database 'name' column
        name = data.get('firm_name')
        phone = data.get('phone')
        credit_limit = float(data.get('credit_limit', 0.0))
        email = data.get('email', '')
        address = data.get('address', '')
        dtype = data.get('type', 'Dealer')
        balance = float(data.get('balance', 0.0))
        status = data.get('status', 'Active')
        owner = data.get('owner', 'Unassigned')
        follow_up_date = data.get('follow_up_date', '')

        if not name or not phone:
            return jsonify({"success": False, "error": "Firm Name and Phone are required."}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        if did:  # UPDATE
            cursor.execute('''
                UPDATE dealers 
                SET name = ?, phone = ?, credit_limit = ?, email = ?, address = ?, type = ?, balance = ?, status = ?, owner = ?, follow_up_date = ?
                WHERE id = ?;
            ''', (name, phone, credit_limit, email, address, dtype, balance, status, owner, follow_up_date, did))
            log_workflow_event(cursor, "UPDATE", "DEALER", did, "Success")
            msg = "Dealer updated successfully."
        else:    # CREATE
            cursor.execute('''
                INSERT INTO dealers (name, email, phone, address, type, credit_limit, balance, status, owner, follow_up_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            ''', (name, email, phone, address, dtype, credit_limit, balance, status, owner, follow_up_date))
            did = cursor.lastrowid
            log_workflow_event(cursor, "CREATE", "DEALER", did, "Success")
            msg = "Dealer registered successfully."

        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": msg, "id": did})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# --- FOLLOW-UPS ENDPOINTS ---
@app.route('/api/follow-ups', methods=['GET', 'POST'])
def manage_followups():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            cursor.execute("SELECT * FROM follow_ups ORDER BY scheduled_date ASC;")
            followups = [dict_from_row(row) for row in cursor.fetchall()]
            conn.close()
            return jsonify({"success": True, "data": followups})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500

    elif request.method == 'POST':
        try:
            data = request.json
            title = data.get('title')
            notes = data.get('notes', '')
            scheduled_date = data.get('scheduled_date')
            priority = data.get('priority', 'Medium')

            if not title or not scheduled_date:
                return jsonify({"success": False, "error": "Title and Scheduled Date are required."}), 400

            cursor.execute('''
                INSERT INTO follow_ups (title, notes, scheduled_date, priority)
                VALUES (?, ?, ?, ?);
            ''', (title, notes, scheduled_date, priority))
            
            fid = cursor.lastrowid
            log_workflow_event(cursor, "CREATE", "FOLLOW_UP", fid, "Success")
            conn.commit()
            conn.close()

            return jsonify({"success": True, "message": "Follow-up scheduled successfully.", "id": fid})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/follow-ups/<int:follow_up_id>/complete', methods=['POST'])
def complete_followup(follow_up_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM follow_ups WHERE id = ?;", (follow_up_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({"success": False, "error": "Follow-up not found."}), 404

        cursor.execute("UPDATE follow_ups SET status = 'Completed' WHERE id = ?;", (follow_up_id,))
        log_workflow_event(cursor, "UPDATE", "FOLLOW_UP", follow_up_id, "Completed")
        conn.commit()
        conn.close()

        return jsonify({"success": True, "message": "Follow-up status marked as Completed."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# --- WORKFLOW LOGS ENGINE ---
@app.route('/api/workflow/logs', methods=['GET'])
@app.route('/api/workflow_logs', methods=['GET'])
@app.route('/api/logs', methods=['GET'])
def get_workflow_logs():
    conn = None
    try:
        conn = get_db_connection()
        logs = fetch_workflow_logs(conn, limit=50)
        return jsonify({"success": True, "data": logs})
    except Exception as e:
        print(f"Workflow logs query failed: {str(e)}")
        return jsonify({"success": False, "error": str(e), "data": []}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

# --- PRE-EXISTING ENDPOINTS (Preserved & Enhanced with Audit Logs) ---

# 1. Dashboard Metrics
@app.route('/api/dashboard', methods=['GET'])
def get_dashboard_metrics():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COALESCE(SUM(total_amount), 0) FROM sales_orders;")
        total_revenue = scalar_from_row(cursor.fetchone()) or 0

        cursor.execute("SELECT COALESCE(SUM(balance), 0) FROM dealers;")
        total_credit_dues = scalar_from_row(cursor.fetchone()) or 0

        cursor.execute("SELECT COUNT(*) FROM dealers WHERE status = 'Active';")
        active_dealers = scalar_from_row(cursor.fetchone()) or 0

        cursor.execute('''
            SELECT COUNT(*) FROM warehouse_stock ws
            JOIN products p ON ws.product_id = p.id
            WHERE ws.quantity <= ws.safety_threshold;
        ''')
        low_stock_alerts = scalar_from_row(cursor.fetchone()) or 0

        today_str = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("SELECT COUNT(*) FROM dealers WHERE follow_up_date < ? AND status = 'Active';", (today_str,))
        overdue_followups = scalar_from_row(cursor.fetchone()) or 0

        cursor.execute('''
            SELECT so.id, d.name as dealer_name, so.order_date, so.total_amount, so.payment_status
            FROM sales_orders so
            JOIN dealers d ON so.dealer_id = d.id
            ORDER BY so.id DESC
            LIMIT 5;
        ''')
        recent_orders = [dict_from_row(row) for row in cursor.fetchall()]

        cursor.execute('''
            SELECT p.category, COALESCE(SUM(soi.quantity * soi.unit_price), 0) as value
            FROM sales_order_items soi
            JOIN products p ON soi.product_id = p.id
            GROUP BY p.category;
        ''')
        category_data = [dict_from_row(row) for row in cursor.fetchall()]

        cursor.execute('''
            SELECT p.name, ws.quantity, ws.safety_threshold, ws.bin_location
            FROM warehouse_stock ws
            JOIN products p ON ws.product_id = p.id
            WHERE ws.quantity <= ws.safety_threshold
            LIMIT 5;
        ''')
        low_stock_items = [dict_from_row(row) for row in cursor.fetchall()]

        conn.close()

        return jsonify({
            "success": True,
            "metrics": {
                "total_revenue": total_revenue,
                "total_credit_dues": total_credit_dues,
                "active_dealers": active_dealers,
                "low_stock_alerts": low_stock_alerts,
                "overdue_followups": overdue_followups
            },
            "recent_orders": recent_orders,
            "category_data": category_data,
            "low_stock_items": low_stock_items
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 2. Dealers Endpoints
@app.route('/api/dealers', methods=['GET', 'POST'])
def manage_dealers():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            cursor.execute("SELECT * FROM dealers ORDER BY name ASC;")
            dealers = [dict_from_row(row) for row in cursor.fetchall()]
            conn.close()
            return jsonify({"success": True, "data": dealers})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500

    elif request.method == 'POST':
        try:
            data = request.json
            name = data.get('name')
            email = data.get('email')
            phone = data.get('phone')
            address = data.get('address')
            dtype = data.get('type')
            credit_limit = float(data.get('credit_limit', 0.0))
            balance = float(data.get('balance', 0.0))
            status = data.get('status', 'Active')
            owner = data.get('owner', 'Unassigned')
            follow_up_date = data.get('follow_up_date')

            if not name or not phone or not dtype:
                return jsonify({"success": False, "error": "Name, Phone and Type are required fields."}), 400

            cursor.execute('''
                INSERT INTO dealers (name, email, phone, address, type, credit_limit, balance, status, owner, follow_up_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            ''', (name, email, phone, address, dtype, credit_limit, balance, status, owner, follow_up_date))
            
            new_id = cursor.lastrowid
            log_workflow_event(cursor, "CREATE", "DEALER", new_id, "Success")
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": "Dealer created successfully", "id": new_id})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/dealers/<int:dealer_id>', methods=['GET', 'PUT'])
def get_update_dealer(dealer_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            cursor.execute("SELECT * FROM dealers WHERE id = ?;", (dealer_id,))
            dealer = dict_from_row(cursor.fetchone())
            if not dealer:
                conn.close()
                return jsonify({"success": False, "error": "Dealer not found"}), 404
            
            cursor.execute('''
                SELECT id, order_date, total_amount, payment_status 
                FROM sales_orders 
                WHERE dealer_id = ? 
                ORDER BY id DESC;
            ''', (dealer_id,))
            orders = [dict_from_row(row) for row in cursor.fetchall()]

            cursor.execute('''
                SELECT id, note, contact_date, next_follow_up, owner 
                FROM follow_up_notes 
                WHERE dealer_id = ? 
                ORDER BY id DESC;
            ''', (dealer_id,))
            notes = [dict_from_row(row) for row in cursor.fetchall()]

            conn.close()
            return jsonify({
                "success": True,
                "dealer": dealer,
                "orders": orders,
                "notes": notes
            })
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500

    elif request.method == 'PUT':
        try:
            data = request.json
            cursor.execute("SELECT * FROM dealers WHERE id = ?;", (dealer_id,))
            dealer = cursor.fetchone()
            if not dealer:
                conn.close()
                return jsonify({"success": False, "error": "Dealer not found"}), 404

            name = data.get('name', dealer['name'])
            email = data.get('email', dealer['email'])
            phone = data.get('phone', dealer['phone'])
            address = data.get('address', dealer['address'])
            dtype = data.get('type', dealer['type'])
            credit_limit = float(data.get('credit_limit', dealer['credit_limit']))
            balance = float(data.get('balance', dealer['balance']))
            status = data.get('status', dealer['status'])
            owner = data.get('owner', dealer['owner'])
            follow_up_date = data.get('follow_up_date', dealer['follow_up_date'])

            cursor.execute('''
                UPDATE dealers 
                SET name = ?, email = ?, phone = ?, address = ?, type = ?, credit_limit = ?, balance = ?, status = ?, owner = ?, follow_up_date = ?
                WHERE id = ?;
            ''', (name, email, phone, address, dtype, credit_limit, balance, status, owner, follow_up_date, dealer_id))
            log_workflow_event(cursor, "UPDATE", "DEALER", dealer_id, "Success")
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": "Dealer updated successfully"})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500

# 3. Follow-up Notes Endpoints
@app.route('/api/dealers/<int:dealer_id>/notes', methods=['POST'])
def add_dealer_note(dealer_id):
    try:
        data = request.json
        note = data.get('note')
        next_follow_up = data.get('next_follow_up')
        owner = data.get('owner', 'System')

        if not note:
            return jsonify({"success": False, "error": "Note content is required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM dealers WHERE id = ?;", (dealer_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({"success": False, "error": "Dealer not found"}), 404

        cursor.execute('''
            INSERT INTO follow_up_notes (dealer_id, note, next_follow_up, owner)
            VALUES (?, ?, ?, ?);
        ''', (dealer_id, note, next_follow_up, owner))

        if next_follow_up:
            cursor.execute("UPDATE dealers SET follow_up_date = ? WHERE id = ?;", (next_follow_up, dealer_id))

        log_workflow_event(cursor, "CREATE", "FOLLOW_UP_NOTE", dealer_id, "Success")
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Note added and dealer profile updated."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 4. Products & Stock Endpoints
@app.route('/api/products', methods=['GET', 'POST'])
def manage_products():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            cursor.execute('''
                SELECT p.*, COALESCE(ws.quantity, 0) as stock_quantity, COALESCE(ws.safety_threshold, 10) as safety_threshold, ws.bin_location
                FROM products p
                LEFT JOIN warehouse_stock ws ON p.id = ws.product_id
                ORDER BY p.name ASC;
            ''')
            products = [dict_from_row(row) for row in cursor.fetchall()]
            conn.close()
            return jsonify({"success": True, "data": products})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500

    elif request.method == 'POST':
        try:
            data = request.json
            name = data.get('name')
            sku = data.get('sku')
            price = float(data.get('price', 0.0))
            cost = float(data.get('cost', 0.0))
            category = data.get('category')
            initial_stock = int(data.get('initial_stock', 0))
            safety_threshold = int(data.get('safety_threshold', 10))
            bin_location = data.get('bin_location', 'N/A')

            if not name or not sku:
                return jsonify({"success": False, "error": "Product Name and SKU are required"}), 400

            cursor.execute("SELECT id FROM products WHERE sku = ?;", (sku,))
            existing_product = cursor.fetchone()

            if existing_product:
                product_id = existing_product['id']
                cursor.execute('''
                    UPDATE products
                    SET name = ?, price = ?, cost = ?, category = ?
                    WHERE id = ?;
                ''', (name, price, cost, category, product_id))
                event_type = "UPDATE"
                message = "Product and stock updated successfully"
            else:
                cursor.execute('''
                    INSERT INTO products (name, sku, price, cost, category)
                    VALUES (?, ?, ?, ?, ?);
                ''', (name, sku, price, cost, category))
                product_id = cursor.lastrowid
                event_type = "CREATE"
                message = "Product and stock initialized successfully"

            cursor.execute("SELECT id FROM warehouse_stock WHERE product_id = ?;", (product_id,))
            if cursor.fetchone():
                cursor.execute('''
                    UPDATE warehouse_stock
                    SET quantity = ?, safety_threshold = ?, bin_location = ?
                    WHERE product_id = ?;
                ''', (initial_stock, safety_threshold, bin_location, product_id))
            else:
                cursor.execute('''
                    INSERT INTO warehouse_stock (product_id, quantity, safety_threshold, bin_location)
                    VALUES (?, ?, ?, ?);
                ''', (product_id, initial_stock, safety_threshold, bin_location))

            log_workflow_event(cursor, event_type, "PRODUCT", product_id, "Success")
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": message, "id": product_id})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/stock/update', methods=['POST'])
def update_stock():
    try:
        data = request.json
        product_id = data.get('product_id')
        new_quantity = data.get('quantity')
        bin_location = data.get('bin_location')

        if product_id is None or new_quantity is None:
            return jsonify({"success": False, "error": "Product ID and Quantity are required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM products WHERE id = ?;", (product_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({"success": False, "error": "Product not found"}), 404

        cursor.execute("SELECT id FROM warehouse_stock WHERE product_id = ?;", (product_id,))
        exists = cursor.fetchone()
        if exists:
            if bin_location:
                cursor.execute('''
                    UPDATE warehouse_stock 
                    SET quantity = ?, bin_location = ?
                    WHERE product_id = ?;
                ''', (new_quantity, bin_location, product_id))
            else:
                cursor.execute('''
                    UPDATE warehouse_stock 
                    SET quantity = ?
                    WHERE product_id = ?;
                ''', (new_quantity, product_id))
        else:
            cursor.execute('''
                INSERT INTO warehouse_stock (product_id, quantity, bin_location)
                VALUES (?, ?, ?);
            ''', (product_id, new_quantity, bin_location or 'N/A'))

        log_workflow_event(cursor, "UPDATE", "STOCK", product_id, "Success")
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Stock updated successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 5. Orders Endpoints (Sales)
@app.route('/api/orders', methods=['GET', 'POST'])
def manage_orders():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            cursor.execute('''
                SELECT so.id, d.name as dealer_name, d.phone as dealer_phone, so.order_date, so.total_amount, so.payment_status, so.lifecycle_status
                FROM sales_orders so
                JOIN dealers d ON so.dealer_id = d.id
                ORDER BY so.id DESC;
            ''')
            orders = []
            for row in cursor.fetchall():
                const_order = dict_from_row(row)
                cursor.execute('''
                    SELECT soi.quantity, soi.unit_price, p.name as product_name, p.sku
                    FROM sales_order_items soi
                    JOIN products p ON soi.product_id = p.id
                    WHERE soi.order_id = ?;
                ''', (const_order['id'],))
                const_order['items'] = [dict_from_row(r) for r in cursor.fetchall()]
                orders.append(const_order)

            conn.close()
            return jsonify({"success": True, "data": orders})
        except Exception as e:
            error_message = str(e)
            conn.close()
            if 'Unknown column' in error_message and 'lifecycle_status' in error_message:
                print('Orders query failed due to missing lifecycle_status column:', error_message)
                return jsonify({"success": True, "data": []}), 200
            return jsonify({"success": False, "error": error_message, "data": []}), 500

    elif request.method == 'POST':
        try:
            data = request.json
            dealer_id = data.get('dealer_id')
            items = data.get('items')
            payment_status = data.get('payment_status', 'Pending')

            if not dealer_id or not items or len(items) == 0:
                return jsonify({"success": False, "error": "Dealer ID and items list are required"}), 400

            cursor.execute("SELECT credit_limit, balance, status FROM dealers WHERE id = ?;", (dealer_id,))
            dealer = cursor.fetchone()
            if not dealer:
                conn.close()
                return jsonify({"success": False, "error": "Dealer not found"}), 404
            
            if dealer['status'] == 'Blocked':
                conn.close()
                return jsonify({"success": False, "error": "Dealer is currently blocked. Order cannot be placed."}), 400

            total_amount = 0.0
            order_items_processed = []

            for item in items:
                p_id = item.get('product_id')
                qty = int(item.get('quantity', 0))

                if qty <= 0:
                    return jsonify({"success": False, "error": f"Invalid quantity {qty} for product ID {p_id}"}), 400

                cursor.execute('''
                    SELECT p.price, p.name, COALESCE(ws.quantity, 0) as stock
                    FROM products p
                    LEFT JOIN warehouse_stock ws ON p.id = ws.product_id
                    WHERE p.id = ?;
                ''', (p_id,))
                prod = cursor.fetchone()
                if not prod:
                    conn.close()
                    return jsonify({"success": False, "error": f"Product ID {p_id} not found"}), 404

                if prod['stock'] < qty:
                    conn.close()
                    return jsonify({"success": False, "error": f"Insufficient stock for '{prod['name']}'. Available: {prod['stock']}, Requested: {qty}"}), 400

                item_total = prod['price'] * qty
                total_amount += item_total
                order_items_processed.append({
                    "product_id": p_id,
                    "quantity": qty,
                    "unit_price": prod['price'],
                    "available_stock": prod['stock']
                })

            new_balance = dealer['balance'] + total_amount
            if payment_status != 'Paid' and dealer['credit_limit'] > 0 and new_balance > dealer['credit_limit']:
                conn.close()
                return jsonify({
                    "success": False,
                    "error": f"Order total (Rs {total_amount:.2f}) exceeds dealer's credit limit. Current balance: Rs {dealer['balance']:.2f}, Limit: Rs {dealer['credit_limit']:.2f}"
                }), 400

            cursor.execute('''
                INSERT INTO sales_orders (dealer_id, total_amount, payment_status)
                VALUES (?, ?, ?);
            ''', (dealer_id, total_amount, payment_status))
            order_id = cursor.lastrowid

            for o_item in order_items_processed:
                cursor.execute('''
                    INSERT INTO sales_order_items (order_id, product_id, quantity, unit_price)
                    VALUES (?, ?, ?, ?);
                ''', (order_id, o_item['product_id'], o_item['quantity'], o_item['unit_price']))

                new_stock = o_item['available_stock'] - o_item['quantity']
                cursor.execute("UPDATE warehouse_stock SET quantity = ? WHERE product_id = ?;", (new_stock, o_item['product_id']))

            if payment_status != 'Paid':
                cursor.execute("UPDATE dealers SET balance = ? WHERE id = ?;", (new_balance, dealer_id))

            log_workflow_event(cursor, "CREATE", "SALES_ORDER", order_id, "Success")
            conn.commit()
            conn.close()

            return jsonify({
                "success": True, 
                "message": "Order created successfully", 
                "order_id": order_id,
                "total_amount": total_amount
            })
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500

# 6. Collections & Payments Endpoint
@app.route('/api/credit/payment', methods=['POST'])
def record_payment():
    try:
        data = request.json
        dealer_id = data.get('dealer_id')
        payment_amount = float(data.get('amount', 0.0))

        if not dealer_id or payment_amount <= 0:
            return jsonify({"success": False, "error": "Dealer ID and valid payment amount are required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT balance, name FROM dealers WHERE id = ?;", (dealer_id,))
        dealer = cursor.fetchone()
        if not dealer:
            conn.close()
            return jsonify({"success": False, "error": "Dealer not found"}), 404

        new_balance = max(0.0, dealer['balance'] - payment_amount)
        cursor.execute("UPDATE dealers SET balance = ? WHERE id = ?;", (new_balance, dealer_id))

        cursor.execute('''
            INSERT INTO follow_up_notes (dealer_id, note, owner)
            VALUES (?, ?, ?);
        ''', (dealer_id, f"Payment Received: Rs {payment_amount:.2f}. Updated balance is Rs {new_balance:.2f}.", "Accounts Team"))

        cursor.execute('''
            SELECT id, total_amount, payment_status 
            FROM sales_orders 
            WHERE dealer_id = ? AND payment_status != 'Paid'
            ORDER BY id ASC;
        ''', (dealer_id,))
        
        unpaid_orders = cursor.fetchall()
        remaining_payment = payment_amount

        for order in unpaid_orders:
            if remaining_payment <= 0:
                break
            order_id = order['id']
            cursor.execute("UPDATE sales_orders SET payment_status = 'Paid' WHERE id = ?;", (order_id,))
            remaining_payment -= order['total_amount']

        log_workflow_event(cursor, "CREATE", "CREDIT_PAYMENT", dealer_id, "Success")
        conn.commit()
        conn.close()
        return jsonify({
            "success": True, 
            "message": f"Payment of Rs {payment_amount:.2f} logged for {dealer['name']}",
            "new_balance": new_balance
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 7. Delivery Assignments Endpoints
@app.route('/api/deliveries', methods=['GET', 'POST'])
def manage_deliveries():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            cursor.execute('''
                SELECT da.id, da.order_id, da.delivery_person, da.vehicle_no, da.route, da.status,
                       da.lifecycle_status, da.assignment_date,
                       d.name as dealer_name, d.address as dealer_address, so.total_amount
                FROM delivery_assignments da
                JOIN sales_orders so ON da.order_id = so.id
                JOIN dealers d ON so.dealer_id = d.id
                ORDER BY da.id DESC;
            ''')
            deliveries = [dict_from_row(row) for row in cursor.fetchall()]
            conn.close()
            return jsonify({"success": True, "data": deliveries})
        except Exception as e:
            error_message = str(e)
            if 'Unknown column' in error_message and 'lifecycle_status' in error_message:
                print('Deliveries query falling back without lifecycle_status column:', error_message)
                try:
                    cursor.execute('''
                        SELECT da.id, da.order_id, da.delivery_person, da.vehicle_no, da.route, da.status,
                               da.assignment_date,
                               d.name as dealer_name, d.address as dealer_address, so.total_amount
                        FROM delivery_assignments da
                        JOIN sales_orders so ON da.order_id = so.id
                        JOIN dealers d ON so.dealer_id = d.id
                        ORDER BY da.id DESC;
                    ''')
                    deliveries = []
                    for row in cursor.fetchall():
                        delivery = dict_from_row(row)
                        delivery['lifecycle_status'] = delivery.get('lifecycle_status', 'PENDING')
                        deliveries.append(delivery)
                    conn.close()
                    return jsonify({"success": True, "data": deliveries})
                except Exception as fallback_err:
                    conn.close()
                    return jsonify({"success": False, "error": str(fallback_err), "data": []}), 500
            conn.close()
            return jsonify({"success": False, "error": error_message, "data": []}), 500

    elif request.method == 'POST':
        try:
            data = request.json
            order_id = data.get('order_id')
            delivery_person = data.get('delivery_person')
            vehicle_no = data.get('vehicle_no')
            route = data.get('route')
            status = data.get('status', 'Pending')

            if not order_id or not delivery_person or not vehicle_no or not route:
                return jsonify({"success": False, "error": "Order ID, Delivery Person, Vehicle No, and Route are required"}), 400

            cursor.execute("SELECT id FROM sales_orders WHERE id = ?;", (order_id,))
            if not cursor.fetchone():
                conn.close()
                return jsonify({"success": False, "error": "Sales Order not found"}), 404

            cursor.execute('''
                INSERT INTO delivery_assignments (order_id, delivery_person, vehicle_no, route, status)
                VALUES (?, ?, ?, ?, ?);
            ''', (order_id, delivery_person, vehicle_no, route, status))

            new_id = cursor.lastrowid
            log_workflow_event(cursor, "CREATE", "DELIVERY", new_id, "Success")
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": "Delivery dispatch assignment successfully scheduled"})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/deliveries/<int:delivery_id>/status', methods=['PUT'])
def update_delivery_status(delivery_id):
    conn = None
    try:
        data = request.json or {}
        raw_status = data.get('status', '')

        # Normalize: uppercase for lifecycle statuses, title-case for transit statuses
        # Try uppercase match first (lifecycle), then title-case (transit)
        new_status = raw_status.strip().upper() if raw_status else ''

        lifecycle_statuses = ['PENDING', 'FINISHED', 'UPDATED', 'PROCESSING']
        transit_statuses_upper = {'DISPATCHED': 'Dispatched', 'DELIVERED': 'Delivered', 'CANCELLED': 'Cancelled'}

        if new_status in transit_statuses_upper:
            new_status = transit_statuses_upper[new_status]

        transit_statuses = ['Pending', 'Dispatched', 'Delivered', 'Cancelled']

        if not new_status or (new_status not in lifecycle_statuses and new_status not in transit_statuses):
            return jsonify({"success": False, "error": "Invalid status value"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM delivery_assignments WHERE id = ?;", (delivery_id,))
        if not cursor.fetchone():
            return jsonify({"success": False, "error": "Delivery assignment not found"}), 404

        if new_status in lifecycle_statuses:
            cursor.execute(
                "UPDATE delivery_assignments SET lifecycle_status = ? WHERE id = ?;",
                (new_status, delivery_id)
            )
            if new_status == "FINISHED":
                cursor.execute(
                    "UPDATE delivery_assignments SET status = 'Delivered' WHERE id = ?;",
                    (delivery_id,)
                )
        else:
            cursor.execute(
                "UPDATE delivery_assignments SET status = ? WHERE id = ?;",
                (new_status, delivery_id)
            )

        log_workflow_event(cursor, "UPDATE", "DELIVERY", delivery_id, new_status)
        conn.commit()
        return jsonify({"success": True, "message": f"Delivery status updated to {new_status}."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

@app.route('/api/deliveries/<int:delivery_id>', methods=['PUT', 'DELETE'])
def modify_delivery(delivery_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'PUT':
        try:
            data = request.json
            driver = data.get('delivery_person')
            vehicle = data.get('vehicle_no')
            route = data.get('route')
            
            if not driver or not vehicle or not route:
                conn.close()
                return jsonify({"success": False, "error": "Driver name, vehicle number, and route details are required."}), 400
                
            cursor.execute('''
                UPDATE delivery_assignments 
                SET delivery_person = ?, vehicle_no = ?, route = ?
                WHERE id = ?;
            ''', (driver, vehicle, route, delivery_id))
            log_workflow_event(cursor, "UPDATE_DETAILS", "DELIVERY", delivery_id, "Success")
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": "Delivery details updated successfully."})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500
            
    elif request.method == 'DELETE':
        try:
            cursor.execute("DELETE FROM delivery_assignments WHERE id = ?;", (delivery_id,))
            log_workflow_event(cursor, "DELETE", "DELIVERY", delivery_id, "Success")
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": "Delivery record deleted."})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500

# 8. Vendor Purchases Endpoints
@app.route('/api/vendors', methods=['GET', 'POST'])
def manage_vendor_purchases():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            cursor.execute('''
                SELECT vp.*, p.name as product_name, p.sku
                FROM vendor_purchases vp
                JOIN products p ON vp.product_id = p.id
                ORDER BY vp.id DESC;
            ''')
            purchases = [dict_from_row(row) for row in cursor.fetchall()]
            conn.close()
            return jsonify({"success": True, "data": purchases})
        except Exception as e:
            error_message = str(e)
            conn.close()
            if 'Unknown column' in error_message and 'lifecycle_status' in error_message:
                print('Vendor purchases query failed due to missing lifecycle_status column:', error_message)
                return jsonify({"success": True, "data": []}), 200
            return jsonify({"success": False, "error": error_message}), 500

    elif request.method == 'POST':
        try:
            data = request.json
            vendor_name = data.get('vendor_name')
            product_id = data.get('product_id')
            quantity = int(data.get('quantity', 0))
            unit_cost = float(data.get('unit_cost', 0.0))
            status = data.get('status', 'Paid')

            if not vendor_name or not product_id or quantity <= 0 or unit_cost <= 0:
                return jsonify({"success": False, "error": "Vendor, Product, valid Quantity and Cost are required"}), 400

            cursor.execute("SELECT id FROM products WHERE id = ?;", (product_id,))
            if not cursor.fetchone():
                conn.close()
                return jsonify({"success": False, "error": "Product not found"}), 404

            total_amount = quantity * unit_cost

            cursor.execute('''
                INSERT INTO vendor_purchases (vendor_name, product_id, quantity, unit_cost, total_amount, status)
                VALUES (?, ?, ?, ?, ?, ?);
            ''', (vendor_name, product_id, quantity, unit_cost, total_amount, status))

            new_id = cursor.lastrowid

            cursor.execute("SELECT quantity FROM warehouse_stock WHERE product_id = ?;", (product_id,))
            existing_stock = cursor.fetchone()
            if existing_stock:
                existing_qty = scalar_from_row(existing_stock) or 0
                new_stock = existing_qty + quantity
                cursor.execute("UPDATE warehouse_stock SET quantity = ? WHERE product_id = ?;", (new_stock, product_id))
            else:
                cursor.execute("INSERT INTO warehouse_stock (product_id, quantity) VALUES (?, ?);", (product_id, quantity))

            log_workflow_event(cursor, "CREATE", "VENDOR_PURCHASE", new_id, "Success")
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": f"Recorded restock of {quantity} units and updated warehouse inventory."})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "error": str(e)}), 500

# 9. Profitability Analytics
@app.route('/api/profitability', methods=['GET'])
def get_profitability_metrics():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COALESCE(SUM(total_amount), 0) FROM sales_orders;")
        total_revenue = scalar_from_row(cursor.fetchone()) or 0

        cursor.execute('''
            SELECT COALESCE(SUM(soi.quantity * p.cost), 0)
            FROM sales_order_items soi
            JOIN products p ON soi.product_id = p.id;
        ''')
        total_cogs = scalar_from_row(cursor.fetchone()) or 0

        cursor.execute("SELECT COALESCE(SUM(total_amount), 0) FROM vendor_purchases;")
        total_expenses = scalar_from_row(cursor.fetchone()) or 0

        cursor.execute('''
            SELECT COALESCE(SUM(ws.quantity * p.cost), 0)
            FROM warehouse_stock ws
            JOIN products p ON ws.product_id = p.id;
        ''')
        inventory_valuation = scalar_from_row(cursor.fetchone()) or 0

        gross_profit = total_revenue - total_cogs
        margin_percent = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0.0

        cursor.execute('''
            SELECT p.name, p.sku, p.category, 
                   COALESCE(SUM(soi.quantity), 0) as units_sold,
                   p.price, p.cost,
                   (p.price - p.cost) as profit_per_unit,
                   ((p.price - p.cost) / p.price * 100) as unit_margin_percent
            FROM products p
            LEFT JOIN sales_order_items soi ON p.id = soi.product_id
            GROUP BY p.id;
        ''')
        product_margins = [dict_from_row(row) for row in cursor.fetchall()]

        conn.close()

        return jsonify({
            "success": True,
            "summary": {
                "total_revenue": total_revenue,
                "total_cogs": total_cogs,
                "gross_profit": gross_profit,
                "margin_percent": round(margin_percent, 2),
                "total_vendor_expenses": total_expenses,
                "inventory_valuation": inventory_valuation
            },
            "product_margins": product_margins
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 10. AI / Rule-Based Insight Generator
@app.route('/api/ai/insights', methods=['GET'])
def get_ai_insights():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM dealers WHERE status != 'Inactive';")
        dealers = [dict_from_row(row) for row in cursor.fetchall()]

        today = datetime.now()
        insights = []

        for dl in dealers:
            dealer_id = dl['id']
            cursor.execute(
                "SELECT COUNT(*) AS order_count, MAX(order_date) AS last_order_date FROM sales_orders WHERE dealer_id = ?;",
                (dealer_id,)
            )
            order_info = cursor.fetchone()
            order_count = order_info.get('order_count', 0) if order_info else 0
            last_order_date = order_info.get('last_order_date') if order_info else None

            health = "Good"
            summary = "Healthy partner with active engagement."
            message = ""

            if dl['status'] == 'Blocked':
                health = "Critical"
                summary = "Account is currently BLOCKED due to payment defaults."
                message = f"Dear {dl['name']}, this is a reminder regarding your overdue outstanding balance of Rs {dl['balance']:.2f}. Please clear the amount immediately to restore supply operations. - Manikanta Enterprises"
            elif dl['balance'] > 0 and dl['credit_limit'] > 0 and (dl['balance'] >= dl['credit_limit'] * 0.9):
                health = "High Risk"
                summary = f"Credit utilization at {int((dl['balance']/dl['credit_limit'])*100)}%. Near credit limit bounds."
                message = f"Dear {dl['name']}, your outstanding balance of Rs {dl['balance']:.2f} has reached {int((dl['balance']/dl['credit_limit'])*100)}% of your credit limit of Rs {dl['credit_limit']:.2f}. Please make a payment to prevent order disruption. - Manikanta Enterprises"
            elif dl['follow_up_date']:
                try:
                    f_date = datetime.strptime(dl['follow_up_date'], '%Y-%m-%d')
                    if f_date < today:
                        health = "Action Required"
                        summary = f"Follow-up scheduled on {dl['follow_up_date']} is OVERDUE. Needs immediate callback."
                        message = f"Hello {dl['name']}, we missed our scheduled call on {dl['follow_up_date']}. Please let us know a convenient time to discuss your next cement and steel requirements. - Manikanta Enterprises"
                except:
                    pass
            elif order_count == 0 and dl['balance'] > 0:
                health = "Medium Risk"
                summary = "Dues pending without recent purchase history."
                message = f"Hello {dl['name']}, we would love to resume our partnership! Please connect with us to clear the pending dues of Rs {dl['balance']:.2f} and inspect our latest catalog. - Manikanta Enterprises"
            
            if not message:
                message = f"Hello {dl['name']}, thank you for being a valued partner of Manikanta Enterprises. We have freshly stocked cement and steel bars available in our warehouse. Let us know if you need to place a dispatch order today! - Sales Team"

            if health == "Good":
                next_step = "Send seasonal greeting or promotion."
            elif health == "Action Required":
                next_step = "Call owner immediately and log call results."
            elif health == "High Risk":
                next_step = "Collect partial payment before executing new orders."
            else:
                next_step = "Escalate to collections officer."

            insights.append({
                "dealer_id": dealer_id,
                "name": dl['name'],
                "type": dl['type'],
                "phone": dl['phone'],
                "balance": dl['balance'],
                "credit_limit": dl['credit_limit'],
                "health": health,
                "summary": summary,
                "suggested_message": message,
                "next_step": next_step,
                "owner": dl['owner'],
                "last_order": last_order_date or "No orders yet"
            })

        conn.close()
        return jsonify({"success": True, "data": insights})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- MONGODB LIFECYCLE ENDPOINTS ---
@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    conn = None
    try:
        data = request.json or {}
        raw_status = data.get('status', '')

        # Normalize to uppercase immediately to handle any frontend casing variants
        status = raw_status.strip().upper() if raw_status else ''
        allowed_statuses = ['PENDING', 'FINISHED', 'PROCESSING', 'UPDATED']

        if not status or status not in allowed_statuses:
            return jsonify({"success": False, "error": "Invalid lifecycle status value"}), 400

        conn = get_db_connection()
        if conn.engine_type == 'mongodb':
            conn.conn.sales_orders.update_one({"id": order_id}, {"$set": {"lifecycle_status": status}})
            payment = "Paid" if status == "FINISHED" else "Pending"
            conn.conn.sales_orders.update_one({"id": order_id}, {"$set": {"payment_status": payment}})
        else:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM sales_orders WHERE id = ?;", (order_id,))
            if not cursor.fetchone():
                return jsonify({"success": False, "error": "Sales order not found"}), 404

            cursor.execute("UPDATE sales_orders SET lifecycle_status = ? WHERE id = ?;", (status, order_id))
            if status == "FINISHED":
                cursor.execute("UPDATE sales_orders SET payment_status = 'Paid' WHERE id = ?;", (order_id,))
            log_workflow_event(cursor, "UPDATE", "SALES_ORDER", order_id, status)
            conn.commit()
        return jsonify({"success": True, "message": f"Order status updated to {status}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

if __name__ == '__main__':
    init_db()
    debug_mode = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes", "on"}
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug_mode, use_reloader=False)
