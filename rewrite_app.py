import re

def rewrite():
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()

    # We will replace get_db_connection usage with get_mongodb_connection in app.py
    # and rewrite the major endpoints.

    new_app = """from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import traceback
import os
import mimetypes
from datetime import datetime
from database import get_mongodb_connection, init_db

mimetypes.add_type('text/css', '.css')
mimetypes.add_type('application/javascript', '.js')

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

@app.errorhandler(Exception)
def handle_unexpected_error(e):
    traceback.print_exc()
    return jsonify({"success": False, "error": str(e)}), 500

def get_db():
    client = get_mongodb_connection()
    if client is None:
        raise Exception("MongoDB not connected")
    return client

def clean_id(doc):
    if doc and '_id' in doc:
        del doc['_id']
    return doc

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        google_credential = data.get('google_credential')
        db = get_db()

        if google_credential:
            user = db.users.find_one({"username": 'operations@manikanta.in'})
            return jsonify({
                "success": True,
                "message": "Google Authentication Successful",
                "user": {"full_name": user['full_name'] if user else "Google User", "username": "google_auth_account"}
            })

        if not username or not password:
            return jsonify({"success": False, "error": "Username and Password are required."}), 400

        user = db.users.find_one({"username": username, "password": password})
        if user:
            return jsonify({
                "success": True, "message": "Authentication Successful",
                "user": {"full_name": user['full_name'], "username": user['username']}
            })
        return jsonify({"success": False, "error": "Invalid username or password."}), 401
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard_metrics():
    try:
        db = get_db()
        orders = list(db.sales_orders.find())
        total_revenue = sum(o.get('total_amount', 0) for o in orders if o.get('lifecycle_status') == 'FINISHED')
        
        dealers = list(db.dealers.find({"status": "Active"}))
        active_dealers = len(dealers)
        total_credit_dues = sum(d.get('balance', 0) for d in dealers)

        low_stock_alerts = db.warehouse_stock.count_documents({"$expr": {"$lte": ["$quantity", "$safety_threshold"]}})
        
        today_str = datetime.now().strftime('%Y-%m-%d')
        overdue_followups = db.dealers.count_documents({"follow_up_date": {"$lt": today_str}, "status": "Active"})

        recent_orders = list(db.sales_orders.find().sort("id", -1).limit(5))
        for o in recent_orders:
            dealer = db.dealers.find_one({"id": o.get("dealer_id")})
            o["dealer_name"] = dealer["name"] if dealer else "Unknown"
            clean_id(o)

        cat_data = {}
        for oi in db.sales_order_items.find():
            p = db.products.find_one({"id": oi["product_id"]})
            if p:
                cat = p.get("category", "Uncategorized")
                cat_data[cat] = cat_data.get(cat, 0) + (oi.get("quantity", 0) * oi.get("unit_price", 0))
        category_data = [{"category": k, "value": v} for k, v in cat_data.items()]

        low_stock_items = []
        for ws in db.warehouse_stock.find({"$expr": {"$lte": ["$quantity", "$safety_threshold"]}}).limit(5):
            p = db.products.find_one({"id": ws["product_id"]})
            ws["name"] = p["name"] if p else "Unknown"
            clean_id(ws)
            low_stock_items.append(ws)

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

@app.route('/api/orders', methods=['GET', 'POST'])
def manage_orders():
    try:
        db = get_db()
        if request.method == 'GET':
            orders = list(db.sales_orders.find().sort("id", -1))
            for order in orders:
                dealer = db.dealers.find_one({"id": order.get("dealer_id")})
                order["dealer_name"] = dealer["name"] if dealer else "Unknown"
                order["dealer_phone"] = dealer["phone"] if dealer else "Unknown"
                
                items = list(db.sales_order_items.find({"order_id": order["id"]}))
                for i in items:
                    p = db.products.find_one({"id": i.get("product_id")})
                    if p:
                        i["product_name"] = p["name"]
                        i["sku"] = p["sku"]
                    clean_id(i)
                order["items"] = items
                clean_id(order)
            return jsonify({"success": True, "data": orders})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    try:
        db = get_db()
        status = request.json.get('status')
        db.sales_orders.update_one({"id": order_id}, {"$set": {"lifecycle_status": status}})
        return jsonify({"success": True, "message": f"Order status updated to {status}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/deliveries', methods=['GET'])
def get_deliveries():
    try:
        db = get_db()
        dels = list(db.delivery_assignments.find().sort("id", -1))
        for d in dels:
            o = db.sales_orders.find_one({"id": d.get("order_id")})
            if o:
                dealer = db.dealers.find_one({"id": o.get("dealer_id")})
                d["dealer_name"] = dealer["name"] if dealer else "Unknown"
                d["dealer_address"] = dealer["address"] if dealer else "Unknown"
                d["total_amount"] = o.get("total_amount", 0)
            clean_id(d)
        return jsonify({"success": True, "data": dels})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/deliveries/<int:id>/status', methods=['PUT'])
def update_delivery_status(id):
    try:
        db = get_db()
        status = request.json.get('status')
        db.delivery_assignments.update_one({"id": id}, {"$set": {"status": status}})
        return jsonify({"success": True, "message": f"Delivery updated to {status}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/products', methods=['GET'])
def manage_products():
    try:
        db = get_db()
        prods = list(db.products.find().sort("name", 1))
        for p in prods:
            ws = db.warehouse_stock.find_one({"product_id": p["id"]})
            p["stock_quantity"] = ws["quantity"] if ws else 0
            p["safety_threshold"] = ws["safety_threshold"] if ws else 10
            p["bin_location"] = ws["bin_location"] if ws else "N/A"
            clean_id(p)
        return jsonify({"success": True, "data": prods})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/dealers', methods=['GET'])
def manage_dealers():
    try:
        db = get_db()
        dealers = list(db.dealers.find().sort("name", 1))
        for d in dealers:
            clean_id(d)
        return jsonify({"success": True, "data": dealers})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/vendors', methods=['GET'])
def manage_vendors():
    try:
        db = get_db()
        vends = list(db.vendor_purchases.find().sort("id", -1))
        for v in vends:
            p = db.products.find_one({"id": v.get("product_id")})
            v["product_name"] = p["name"] if p else "Unknown"
            v["sku"] = p["sku"] if p else "Unknown"
            clean_id(v)
        return jsonify({"success": True, "data": vends})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    debug_mode = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes", "on"}
    app.run(host='0.0.0.0', port=5000, debug=debug_mode, use_reloader=False)
"""

    with open("app.py", "w", encoding="utf-8") as f:
        f.write(new_app)

    print("app.py rewritten successfully!")

if __name__ == "__main__":
    rewrite()
