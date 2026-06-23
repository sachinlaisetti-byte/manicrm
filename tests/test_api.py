import unittest
import json
import os
import sys
# Ensure project root is on Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
from database import init_db
class TestCRMAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize the database schema and default records
        init_db()
    def setUp(self):
        # Configure app for testing
        app.config['TESTING'] = True
        self.client = app.test_client()
    def test_1_dashboard_metrics(self):
        """Test GET /api/dashboard metrics endpoint"""
        response = self.client.get('/api/dashboard')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertTrue(data['success'])
        self.assertIn('metrics', data)
        self.assertIn('recent_orders', data)
        self.assertIn('category_data', data)
        
        metrics = data['metrics']
        self.assertGreaterEqual(metrics['total_revenue'], 0)
        self.assertGreaterEqual(metrics['total_credit_dues'], 0)
    def test_2_dealers_endpoints(self):
        """Test GET and POST /api/dealers"""
        # Test GET all dealers
        response = self.client.get('/api/dealers')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertGreater(len(data['data']), 0)
        # Test POST create new dealer
        new_dealer = {
            "name": "Testing Supplies Ltd",
            "phone": "9988776655",
            "type": "Dealer",
            "credit_limit": 50000.0,
            "balance": 0.0,
            "owner": "Test Runner"
        }
        post_response = self.client.post('/api/dealers', 
                                         data=json.dumps(new_dealer), 
                                         content_type='application/json')
        self.assertEqual(post_response.status_code, 200)
        post_data = json.loads(post_response.data)
        self.assertTrue(post_data['success'])
        self.assertIn('id', post_data)
        
        # Keep track of created dealer ID
        dealer_id = post_data['id']
        # Test GET detail page
        detail_response = self.client.get(f'/api/dealers/{dealer_id}')
        self.assertEqual(detail_response.status_code, 200)
        detail_data = json.loads(detail_response.data)
        self.assertTrue(detail_data['success'])
        self.assertEqual(detail_data['dealer']['name'], "Testing Supplies Ltd")
    def test_3_products_endpoints(self):
        """Test GET and POST /api/products"""
        # Test GET products list
        response = self.client.get('/api/products')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertGreater(len(data['data']), 0)
        # Test POST create new product SKU
        new_sku = {
            "name": "JSW Steel Rebar (10mm)",
            "sku": "SKU-STL-JSW-10",
            "price": 600.0,
            "cost": 500.0,
            "category": "Steel",
            "initial_stock": 50,
            "safety_threshold": 5,
            "bin_location": "AISLE-B2"
        }
        post_response = self.client.post('/api/products', 
                                         data=json.dumps(new_sku), 
                                         content_type='application/json')
        self.assertEqual(post_response.status_code, 200)
        post_data = json.loads(post_response.data)
        self.assertTrue(post_data['success'])
    def test_4_order_processing_and_validation(self):
        """Test POST /api/orders & validation rules (stock deduction, credit limit checks)"""
        # Attempt to order with valid stock & credit
        order_payload = {
            "dealer_id": 1, # Laxmi Traders
            "payment_status": "Pending",
            "items": [
                {
                    "product_id": 3, # Dr. Fixit Waterproofing (5L)
                    "quantity": 2
                }
            ]
        }
        response = self.client.post('/api/orders', 
                                    data=json.dumps(order_payload), 
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('order_id', data)
        # Attempt to order exceeding stock
        invalid_stock_payload = {
            "dealer_id": 1,
            "payment_status": "Pending",
            "items": [
                {
                    "product_id": 3,
                    "quantity": 1000 # Way over stock limit
                }
            ]
        }
        err_response = self.client.post('/api/orders', 
                                        data=json.dumps(invalid_stock_payload), 
                                        content_type='application/json')
        self.assertEqual(err_response.status_code, 400)
        err_data = json.loads(err_response.data)
        self.assertFalse(err_data['success'])
        self.assertIn("Insufficient stock", err_data['error'])
    def test_5_payments_collection(self):
        """Test POST /api/credit/payment"""
        payment_payload = {
            "dealer_id": 1,
            "amount": 5000.0
        }
        response = self.client.post('/api/credit/payment', 
                                    data=json.dumps(payment_payload), 
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('new_balance', data)
    def test_6_profitability_metrics(self):
        """Test GET /api/profitability metrics"""
        response = self.client.get('/api/profitability')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('summary', data)
        self.assertIn('product_margins', data)
    def test_7_ai_insights(self):
        """Test GET /api/ai/insights rules-based engine"""
        response = self.client.get('/api/ai/insights')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertGreater(len(data['data']), 0)
        
        # Check output structure
        first_insight = data['data'][0]
        self.assertIn('health', first_insight)
        self.assertIn('suggested_message', first_insight)
        self.assertIn('next_step', first_insight)
if __name__ == '__main__':
    unittest.main()
