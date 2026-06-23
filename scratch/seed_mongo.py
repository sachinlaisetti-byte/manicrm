import os
import pymongo
from datetime import datetime

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
client = pymongo.MongoClient(MONGO_URI)
db = client["manikanta_crm"]

def seed_database():
    # 1. Users
    db.users.drop()
    db.users.insert_many([
        {
            "id": 1,
            "full_name": "Operations Admin",
            "username": "operations@manikanta.in",
            "password": "admin"
        }
    ])

    # 2. Dealers
    db.dealers.drop()
    dealers = [
        {"id": 1, "name": "Balaji Cement Agency", "phone": "9876543210", "address": "Plot 45, Industrial Estate, Karimnagar", "type": "Wholesaler", "credit_limit": 500000, "balance": 136199.98, "status": "UPDATED"},
        {"id": 2, "name": "Sri Rama Hardware", "phone": "9876543211", "address": "Main Road, Warangal", "type": "Retailer", "credit_limit": 200000, "balance": 0.0, "status": "FINISHED"},
        {"id": 3, "name": "Venkateshwara Pipes", "phone": "9876543212", "address": "Auto Nagar, Nizamabad", "type": "Distributor", "credit_limit": 300000, "balance": 0.0, "status": "UPDATED"},
        {"id": 4, "name": "Durga Constructions", "phone": "9876543213", "address": "Kukatpally, Hyderabad", "type": "Contractor", "credit_limit": 1000000, "balance": 0.0, "status": "PENDING"},
        {"id": 5, "name": "Sai Ram Traders", "phone": "9876543214", "address": "MG Road, Secunderabad", "type": "Retailer", "credit_limit": 150000, "balance": 0.0, "status": "UPDATED"}
    ]
    db.dealers.insert_many(dealers)

    # 3. Products & Stock
    db.products.drop()
    db.warehouse_stock.drop()
    
    products = [
        {"id": 1, "name": "APCO Paint Primer (20L)", "sku": "PT-001", "price": 420.0, "cost": 300.0, "category": "Plumbing"},
        {"id": 2, "name": "PVC Pipe 1.5 inch (10ft)", "sku": "PL-001", "price": 150.0, "cost": 100.0, "category": "Plumbing"},
        {"id": 3, "name": "Cement Bag (50kg)", "sku": "CM-001", "price": 380.0, "cost": 320.0, "category": "Construction"},
        {"id": 4, "name": "Steel TMT Bar 12mm", "sku": "ST-001", "price": 600.0, "cost": 500.0, "category": "Construction"},
        {"id": 5, "name": "Hammer (Heavy Duty)", "sku": "TL-001", "price": 250.0, "cost": 180.0, "category": "Tools"}
    ]
    db.products.insert_many(products)
    
    stock = [
        {"product_id": 1, "quantity": 8, "safety_threshold": 10, "bin_location": "AISLE-D1", "status": "PENDING"},
        {"product_id": 2, "quantity": 50, "safety_threshold": 20, "bin_location": "AISLE-D2", "status": "FINISHED"},
        {"product_id": 3, "quantity": 100, "safety_threshold": 50, "bin_location": "AISLE-A1", "status": "UPDATED"},
        {"product_id": 4, "quantity": 200, "safety_threshold": 100, "bin_location": "AISLE-A2", "status": "FINISHED"},
        {"product_id": 5, "quantity": 5, "safety_threshold": 10, "bin_location": "AISLE-T1", "status": "PENDING"}
    ]
    db.warehouse_stock.insert_many(stock)

    # 4. Sales Orders & Items
    db.sales_orders.drop()
    db.sales_order_items.drop()
    
    orders = []
    order_items = []
    
    # 10 realistic orders
    # We want total FINISHED revenue + outstanding credit to match requirements if needed
    for i in range(1, 11):
        status = "FINISHED" if i <= 5 else ("PROCESSING" if i <= 8 else "PENDING")
        total_amount = i * 150.0
        orders.append({
            "id": i,
            "dealer_id": 1 if i % 2 == 0 else 2,
            "order_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_amount": total_amount,
            "lifecycle_status": status,
            "payment_status": "Paid" if status == "FINISHED" else "Pending"
        })
        order_items.append({
            "id": i,
            "order_id": i,
            "product_id": (i % 5) + 1,
            "quantity": i * 2,
            "unit_price": 75.0
        })
        
    db.sales_orders.insert_many(orders)
    db.sales_order_items.insert_many(order_items)

    # 5. Delivery Assignments
    db.delivery_assignments.drop()
    deliveries = [
        {
            "id": 1,
            "order_id": 6,
            "delivery_person": "Mallesh Yadav",
            "vehicle_no": "TS-08-2345",
            "route": "HYDERABAD",
            "status": "PENDING",
            "assignment_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        {
            "id": 2,
            "order_id": 7,
            "delivery_person": "Suresh Kumar",
            "vehicle_no": "TS-09-5678",
            "route": "WARANGAL",
            "status": "UPDATED",
            "assignment_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    ]
    db.delivery_assignments.insert_many(deliveries)

    # 6. Vendor Purchases
    db.vendor_purchases.drop()
    vendors = [
        {
            "id": 1,
            "vendor_name": "Jindal Steel Works",
            "purchase_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "product_id": 4,
            "quantity": 500,
            "unit_cost": 480.0,
            "total_amount": 240000.0,
            "status": "PENDING"
        }
    ]
    db.vendor_purchases.insert_many(vendors)
    
    print("MongoDB Seeded successfully with interconnected mock data.")

if __name__ == "__main__":
    seed_database()
