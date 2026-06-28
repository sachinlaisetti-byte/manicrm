**README.md content for GitHub:**

---

# Manikanta Enterprises CRM — Distribution Management System

A full-stack web application for managing wholesale building materials distribution operations — dealer management, sales orders, inventory tracking, delivery dispatch, credit management, profitability analytics, and AI-powered sales insights.

**Live Demo:** [https://manicrm.onrender.com](https://manicrm.onrender.com)

---

## Features

| Module | Description |
|--------|-------------|
| **Dashboard** | Real-time KPIs — Revenue, Credit Outstanding, Active Dealers, Low Stock Alerts + Chart.js category-wise sales donut chart |
| **Goods Order Form** | Multi-item sales orders with dynamic line-item builder, real-time stock validation, and credit limit enforcement |
| **Warehouse Stock** | Full inventory catalogue with bin locations, safety thresholds, stock adjustments, and new SKU registration |
| **Dealer & Customer CRM** | Dealer/retailer profiles with order history, follow-up timeline, credit tracking, and contact notes |
| **Deliveries & Dispatch** | Route, driver, and vehicle assignment with transit status monitoring and lifecycle management |
| **Credit Sales Tracker** | Payment collection logging, automated oldest-order reconciliation, and credit risk matrix |
| **Vendor Purchases** | Supplier restock recording with automatic warehouse stock updates |
| **Profitability Analytics** | Revenue, COGS, Gross Profit, per-product margin matrix with colour-coded profit rates |
| **AI Sales Insights** | Rule-based dealer health engine generating personalized WhatsApp/SMS message templates |
| **Follow-ups Tracker** | Priority-scheduled reminders with completion workflow |
| **Workflow Audit Logs** | Complete event-sourced audit trail of all system operations |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3, Flask 3.0, Gunicorn |
| **Frontend** | Vanilla JavaScript SPA, HTML5, CSS3 (glassmorphism design system) |
| **Database** | SQLite (dev) / MySQL (production) / MongoDB (future) via custom abstraction layer |
| **Auth** | Google Identity Services (OAuth 2.0) + native username/password |
| **Visualization** | Chart.js, Lucide Icons |
| **Deployment** | Render Cloud, CI/CD via GitHub |

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/sachinlaisetti-byte/manicrm.git
cd manicrm

# Install dependencies
pip install -r requirements.txt

# Set environment variables (copy and edit)
cp .env.example .env

# Run the application
python app.py
```

The application will be available at `http://localhost:5000`.

**Default credentials:** `admin@manikanta.in` / `admin123`

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Login (native or Google credential) |
| POST | `/api/auth/register` | Register new user |
| GET | `/api/dashboard` | KPIs, recent orders, category distribution |
| GET/POST | `/api/dealers` | List / Create dealers |
| GET/PUT | `/api/dealers/<id>` | Dealer detail / Update |
| POST | `/api/dealers/<id>/notes` | Add follow-up note |
| GET/POST | `/api/customers` | List / Create customers |
| GET/POST | `/api/products` | List / Create products |
| POST | `/api/stock/update` | Adjust warehouse stock |
| GET/POST | `/api/orders` | List / Create sales orders |
| PUT | `/api/orders/<id>/status` | Update order lifecycle |
| GET/POST | `/api/deliveries` | List / Create deliveries |
| PUT/DELETE | `/api/deliveries/<id>` | Update / Delete delivery |
| POST | `/api/credit/payment` | Log payment collection |
| GET/POST | `/api/vendors` | List / Create vendor purchases |
| GET | `/api/profitability` | Revenue, COGS, gross profit, margins |
| GET | `/api/ai/insights` | Dealer health analysis |
| GET/POST | `/api/follow-ups` | List / Create follow-ups |
| POST | `/api/follow-ups/<id>/complete` | Mark follow-up done |
| GET | `/api/workflow/logs` | Audit log stream |

---

## Database Architecture

The application uses a custom proxy-pattern abstraction layer supporting three database engines:

- **SQLite** — Default for local development
- **MySQL** — Production via `mysql-connector-python` (set `DB_ENGINE=mysql`)
- **MongoDB** — Future-ready via `pymongo` (set `DB_ENGINE=mongodb`)

The `SQLCursorProxy` transparently handles SQL dialect differences (`?` → `%s` parameter style, `PRAGMA table_info` → `SHOW COLUMNS`, DDL variations) without requiring an ORM.

**12 database tables:** `users`, `customers`, `dealers`, `products`, `warehouse_stock`, `sales_orders`, `sales_order_items`, `delivery_assignments`, `vendor_purchases`, `follow_ups`, `follow_up_notes`, `workflow_logs`

---

## Deployment

The application is deployed on Render with automatic deploys from the `main` branch:

1. Push to GitHub → Render auto-deploys
2. Environment variables configured in Render dashboard
3. Serves via Gunicorn on port `$PORT`

---

## Testing

```bash
# Run integration pipeline tests
python -m pytest test_pipeline.py -v

# Run API unit tests
python -m pytest tests/test_api.py -v
```

The test suite uses an isolated SQLite database with 7 end-to-end pipeline tests covering dealer creation, order placement, payment reconciliation, profitability computation, error handling, and database failure resilience.

---

## Project Structure

```
├── app.py                  # Flask application — 28 API routes
├── database.py             # DB layer — schema, migrations, seeding, proxy
├── requirements.txt        # Python dependencies
├── .env / .env.example     # Environment configuration
├── test_pipeline.py        # Integration tests
├── templates/
│   └── index.html          # SPA template — all UI
├── static/
│   ├── css/style.css       # Design system (1644 lines)
│   └── js/app.js           # Frontend application (1993 lines)
└── tests/test_api.py       # Unit tests
```

---

## Contributors

- **Sachin Laisetti** — 252U1R3080
- **S Sobhan** — 252U1R3083

---

## License

This project is developed for Manikanta Enterprises as part of an internship program.
