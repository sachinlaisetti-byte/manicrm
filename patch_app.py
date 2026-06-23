import os
import re

def patch_app_py():
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()

    # We will inject the MongoDB lifecycle endpoints at the end of the file.
    
    mongo_endpoints = """
# --- MONGODB LIFECYCLE ENDPOINTS ---
@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    try:
        conn = get_db_connection()
        status = request.json.get('status')
        if conn.engine_type == 'mongodb':
            conn.conn.sales_orders.update_one({"id": order_id}, {"$set": {"lifecycle_status": status}})
            # Also update payment status based on lifecycle
            payment = "Paid" if status == "FINISHED" else "Pending"
            conn.conn.sales_orders.update_one({"id": order_id}, {"$set": {"payment_status": payment}})
        else:
            cursor = conn.cursor()
            cursor.execute("UPDATE sales_orders SET lifecycle_status = ? WHERE id = ?;", (status, order_id))
            if status == "FINISHED":
                cursor.execute("UPDATE sales_orders SET payment_status = 'Paid' WHERE id = ?;", (order_id,))
            conn.commit()
        return jsonify({"success": True, "message": f"Order status updated to {status}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
"""
    if "# --- MONGODB LIFECYCLE ENDPOINTS ---" not in content:
        content = content.replace("if __name__ == '__main__':", mongo_endpoints + "\nif __name__ == '__main__':")
        
    with open("app.py", "w", encoding="utf-8") as f:
        f.write(content)
        
if __name__ == "__main__":
    patch_app_py()
