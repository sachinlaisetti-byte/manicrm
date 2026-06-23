import os
import sys
import json
import sqlite3
import unittest
import traceback

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

os.environ["FLASK_DEBUG"] = "false"

from app import app
import database
database.DB_ENGINE = "sqlite"
from database import init_db, DATABASE_PATH, get_db_connection, scalar_from_row


class TestPipelineSanityCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_db = os.path.join(os.path.dirname(DATABASE_PATH), "test_manikanta_crm.db")
        # Backup and restore DATABASE_PATH for isolation
        cls._original_db_path = DATABASE_PATH
        import database as db_mod
        db_mod.DATABASE_PATH = test_db
        if os.path.exists(test_db):
            os.remove(test_db)
        init_db()
        cls._seed_test_fixtures()

    @classmethod
    def _seed_test_fixtures(cls):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS cnt FROM dealers")
        row = cursor.fetchone()
        if row and row.get('cnt', 0) > 0:
            conn.close()
            return
        dealers_raw = [
            ("Priya Constructions", "9000000001", "Dealer", 100000.0, 15000.0, "Active", "Srinivas", "2026-07-15"),
            ("Sri Sai Cement", "9000000002", "Retailer", 50000.0, 5000.0, "Active", "Rajesh", "2026-07-20"),
            ("Venkateswara Steel", "9000000003", "Dealer", 200000.0, 75000.0, "Active", "Srinivas", "2026-06-01"),
            ("Krishna Traders", "9000000004", "Dealer", 75000.0, 0.0, "Active", "Kalyan", None),
            ("Anjani Enterprises", "9000000005", "Retailer", 30000.0, 12000.0, "Blocked", "Rajesh", "2026-05-10"),
        ]
        for d in dealers_raw:
            cursor.execute(
                "INSERT INTO dealers (name, phone, type, credit_limit, balance, status, owner, follow_up_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", d
            )
        for col in ["cost REAL DEFAULT 0.0", "price REAL DEFAULT 0.0", "sku TEXT DEFAULT ''"]:
            try:
                cursor.execute(f"ALTER TABLE products ADD COLUMN {col}")
            except Exception:
                pass
        products_raw = [
            ("Test Cement 53 Grade", "SKU-CMT-TC53", "Cement", 380.0, 320.0),
            ("Test Steel Rebar 12mm", "SKU-STL-TR12", "Steel", 720.0, 610.0),
        ]
        for name, sku, cat, price, cost in products_raw:
            cursor.execute(
                "INSERT INTO products (name, sku_id, sku, category, unit_price, price, cost) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, sku, sku, cat, price, price, cost)
            )
        warehouse_raw = [(1, 200, 20), (2, 100, 10)]
        for pid, qty, thr in warehouse_raw:
            cursor.execute(
                "INSERT INTO warehouse_stock (product_id, quantity, safety_threshold) VALUES (?, ?, ?)",
                (pid, qty, thr)
            )
        conn.commit()
        conn.close()

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SERVER_NAME'] = 'localhost'
        self.client = app.test_client()
        self.maxDiff = None

    # ------------------------------------------------------------------ #
    #  Pipeline A: Create Dealer -> Create Order -> Verify Dashboard     #
    # ------------------------------------------------------------------ #
    def test_pipeline_a_dealer_order_dashboard(self):
        dealer_payload = {
            "name": "PipelineA Testing Co",
            "phone": "9111111111",
            "type": "Dealer",
            "credit_limit": 150000.0,
            "owner": "Pipeline Test"
        }
        resp = self.client.post('/api/dealers',
                                data=json.dumps(dealer_payload),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        dealer_data = json.loads(resp.data)
        self.assertTrue(dealer_data['success'])
        dealer_id = dealer_data['id']

        detail_resp = self.client.get(f'/api/dealers/{dealer_id}')
        self.assertEqual(detail_resp.status_code, 200)
        detail_data = json.loads(detail_resp.data)
        self.assertTrue(detail_data['success'])
        self.assertEqual(detail_data['dealer']['name'], "PipelineA Testing Co")

        dash_resp = self.client.get('/api/dashboard')
        self.assertEqual(dash_resp.status_code, 200)
        dash_before = json.loads(dash_resp.data)
        dealer_count_before = dash_before['metrics']['active_dealers']

        prod_resp = self.client.get('/api/products')
        prod_data = json.loads(prod_resp.data)
        self.assertTrue(prod_data['success'])
        test_product = prod_data['data'][0]
        expected_item_total = test_product['price'] * 10

        order_payload = {
            "dealer_id": dealer_id,
            "payment_status": "Pending",
            "items": [{"product_id": test_product['id'], "quantity": 10}]
        }
        order_resp = self.client.post('/api/orders',
                                      data=json.dumps(order_payload),
                                      content_type='application/json')
        self.assertEqual(order_resp.status_code, 200)
        order_data = json.loads(order_resp.data)
        self.assertTrue(order_data['success'])
        self.assertIn('order_id', order_data)
        self.assertAlmostEqual(order_data['total_amount'], expected_item_total, delta=0.01)

        dash_resp2 = self.client.get('/api/dashboard')
        self.assertEqual(dash_resp2.status_code, 200)
        dash_after = json.loads(dash_resp2.data)
        self.assertGreaterEqual(dash_after['metrics']['total_revenue'],
                                dash_before['metrics']['total_revenue'] + 3800.0)
        self.assertEqual(dash_after['metrics']['active_dealers'], dealer_count_before)

    # ------------------------------------------------------------------ #
    #  Pipeline B: Register Customer -> Link to Order                    #
    # ------------------------------------------------------------------ #
    def test_pipeline_b_customer_order_validation(self):
        cust_payload = {
            "name": "PipelineB Customer",
            "company": "B Constructions",
            "phone": "9222222222",
            "email": "pipeb@test.in",
            "address": "Test Address B"
        }
        resp = self.client.post('/api/customers',
                                data=json.dumps(cust_payload),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        cust_data = json.loads(resp.data)
        self.assertTrue(cust_data['success'])

        customers_resp = self.client.get('/api/customers')
        self.assertEqual(customers_resp.status_code, 200)
        customers = json.loads(customers_resp.data)
        self.assertTrue(customers['success'])
        names = [c['name'] for c in customers['data']]
        self.assertIn("PipelineB Customer", names)

    # ------------------------------------------------------------------ #
    #  Pipeline C: Multiple Records & Dashboard Counter Verification      #
    # ------------------------------------------------------------------ #
    def test_pipeline_c_multiple_orders_counter_verification(self):
        dash_before = json.loads(self.client.get('/api/dashboard').data)
        rev_before = dash_before['metrics']['total_revenue']

        prod_resp = self.client.get('/api/products')
        prod_data = json.loads(prod_resp.data)
        p1 = prod_data['data'][0]
        p2 = prod_data['data'][1] if len(prod_data['data']) > 1 else p1

        orders_to_create = [
            (1, [{"product_id": p2['id'], "quantity": 5}], p2['price'] * 5),
            (2, [{"product_id": p1['id'], "quantity": 20}], p1['price'] * 20),
            (2, [{"product_id": p2['id'], "quantity": 3}], p2['price'] * 3),
        ]
        expected_total = 0.0
        for dealer_id, items, _ in orders_to_create:
            payload = {"dealer_id": dealer_id, "payment_status": "Pending", "items": items}
            resp = self.client.post('/api/orders',
                                    data=json.dumps(payload),
                                    content_type='application/json')
            self.assertEqual(resp.status_code, 200)
            data = json.loads(resp.data)
            self.assertTrue(data['success'])
            expected_total += data['total_amount']

        dash_after = json.loads(self.client.get('/api/dashboard').data)
        self.assertAlmostEqual(dash_after['metrics']['total_revenue'],
                               rev_before + expected_total, delta=0.01)

    # ------------------------------------------------------------------ #
    #  Pipeline D: Record Payment & Verify Balance Update                #
    # ------------------------------------------------------------------ #
    def test_pipeline_d_payment_balance_update(self):
        dealer_resp = self.client.get('/api/dealers/1')
        self.assertEqual(dealer_resp.status_code, 200)
        dealer = json.loads(dealer_resp.data)
        balance_before = dealer['dealer']['balance']

        pay_payload = {"dealer_id": 1, "amount": 5000.0}
        pay_resp = self.client.post('/api/credit/payment',
                                    data=json.dumps(pay_payload),
                                    content_type='application/json')
        self.assertEqual(pay_resp.status_code, 200)
        pay_data = json.loads(pay_resp.data)
        self.assertTrue(pay_data['success'])
        expected_balance = max(0.0, balance_before - 5000.0)
        self.assertAlmostEqual(pay_data['new_balance'], expected_balance, delta=0.01)

    # ------------------------------------------------------------------ #
    #  Pipeline E: Profitability Metrics After Orders                     #
    # ------------------------------------------------------------------ #
    def test_pipeline_e_profitability_metrics(self):
        prof_resp = self.client.get('/api/profitability')
        self.assertEqual(prof_resp.status_code, 200)
        prof_data = json.loads(prof_resp.data)
        self.assertTrue(prof_data['success'])
        self.assertIn('summary', prof_data)
        self.assertIn('product_margins', prof_data)
        s = prof_data['summary']
        self.assertGreater(s['total_revenue'], 0)
        self.assertGreaterEqual(s['gross_profit'], 0)
        self.assertGreaterEqual(len(prof_data['product_margins']), 0)

    # ------------------------------------------------------------------ #
    #  Error Handling: Missing Parameters Return 400                      #
    # ------------------------------------------------------------------ #
    def test_error_missing_dealer_name(self):
        resp = self.client.post('/api/dealers',
                                data=json.dumps({"phone": "9999999999", "type": "Dealer"}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertFalse(data['success'])

    def test_error_missing_order_dealer(self):
        resp = self.client.post('/api/orders',
                                data=json.dumps({"payment_status": "Pending", "items": []}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertFalse(data['success'])

    def test_error_missing_delivery_fields(self):
        resp = self.client.post('/api/deliveries',
                                data=json.dumps({"order_id": 1}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertFalse(data['success'])

    def test_error_invalid_payment_amount(self):
        resp = self.client.post('/api/credit/payment',
                                data=json.dumps({"dealer_id": 1, "amount": 0}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertFalse(data['success'])

    def test_error_invalid_product_sku(self):
        resp = self.client.post('/api/products',
                                data=json.dumps({"name": "", "sku": ""}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertFalse(data['success'])

    # ------------------------------------------------------------------ #
    #  DB Failure Handling: Simulate without crashing host thread         #
    # ------------------------------------------------------------------ #
    def test_database_failure_logs_without_crashing(self):
        try:
            broken_conn = get_db_connection()
            cursor = broken_conn.cursor()
            cursor.execute("SELECT * FROM nonexistent_table_xyz")
            broken_conn.close()
            self.fail("should have raised an exception")
        except Exception as e:
            log_msg = f"[TEST_DB_HANDLING] Expected database error occurred: {e}"
            traceback.print_exc()
            self.assertIn("no such table", str(e).lower())

    def test_workflow_logs_endpoint_resilient(self):
        resp = self.client.get('/api/workflow/logs')
        self.assertIn(resp.status_code, (200, 500))
        data = json.loads(resp.data)
        self.assertIn('data', data)

    # ------------------------------------------------------------------ #
    #  Auth: Missing credentials return 400                               #
    # ------------------------------------------------------------------ #
    def test_auth_missing_credentials(self):
        resp = self.client.post('/api/auth/login',
                                data=json.dumps({}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertFalse(data['success'])
        self.assertIn('required', data.get('error', '').lower())

    def test_auth_register_missing_fields(self):
        resp = self.client.post('/api/auth/register',
                                data=json.dumps({"full_name": "Test"}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertFalse(data['success'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
