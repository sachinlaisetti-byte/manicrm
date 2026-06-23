// --- Manikanta Enterprises CRM App Client Logic ---
const API_BASE = ""; // Relative paths since served from same server
let categoryChart = null;
let crmActiveView = "dealers";
document.addEventListener("DOMContentLoaded", () => {
    // 1. Initialize Tabs & Navigation (for post-login use)
    initNavigation();
    
    // 2. Set up form-auth-native mode attribute + attach login submit handler
    const authFormEl = document.getElementById("form-auth-native");
    if (authFormEl) authFormEl.dataset.mode = "signin";
    initAuthFormListener();

    // 3. Header Actions (only active post-login)
    const refreshBtn = document.getElementById("btn-refresh");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", () => {
            loadAllData();
            showNotification("Data refreshed successfully!");
        });
    }
    // Update Header Date
    const dateOptions = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    const headerTime = document.getElementById("header-time");
    if (headerTime) headerTime.innerText = new Date().toLocaleDateString("en-US", dateOptions);
    // Global Search Filter
    const globalSearch = document.getElementById("global-search");
    if (globalSearch) globalSearch.addEventListener("input", handleGlobalSearch);

    // 4. Bell / Notification dropdown toggle
    const bellWrapper = document.getElementById("notification-bell-wrapper");
    const notifPanel  = document.getElementById("notif-dropdown-panel");
    if (bellWrapper && notifPanel) {
        bellWrapper.addEventListener("click", (e) => {
            e.stopPropagation();
            const isHidden = notifPanel.classList.toggle("hidden");
            if (!isHidden) {
                // Panel just opened — refresh data
                loadNotifications();
                if (typeof lucide !== "undefined") lucide.createIcons();
            }
        });
        // Close when clicking anywhere outside
        window.addEventListener("click", (e) => {
            if (!bellWrapper.contains(e.target)) {
                notifPanel.classList.add("hidden");
            }
        });
    }

    // 5. Check if already logged in (session restore)
    const savedUser = sessionStorage.getItem("crm_user");
    if (savedUser) {
        try {
            const user = JSON.parse(savedUser);
            const nameEl = document.getElementById("current-user-name");
            const avatarEl = document.getElementById("current-user-avatar");
            if (nameEl) nameEl.innerText = user.full_name || user.username || "Admin";
            if (avatarEl) {
                const initials = (user.full_name || user.username || "AD")
                    .split(" ").map(n => n[0]).join("").substring(0, 2).toUpperCase();
                avatarEl.innerText = initials;
            }
            document.getElementById("auth-container").style.display = "none";
            document.getElementById("app-runtime-container").style.display = "flex";
            loadAllData();
            setupFormListeners();
            if (typeof lucide !== "undefined") lucide.createIcons();
        } catch (e) {
            sessionStorage.removeItem("crm_user");
        }
    }
});

// --- Notification System ---

function safeArray(val) {
    return Array.isArray(val) ? val : [];
}

async function loadNotifications() {
    const body  = document.getElementById("notif-dropdown-body");
    const badge = document.getElementById("notif-badge-count");
    const bellDot = document.getElementById("bell-dot-alert");
    if (!body) return;

    body.innerHTML = `<div class="notif-empty-state"><p style="color:#6b7280;font-size:12px;">Fetching alerts...</p></div>`;

    try {
        // Fetch follow-ups and low-stock simultaneously
        const [fuRes, stockRes] = await Promise.allSettled([
            fetch(`${API_BASE}/api/follow-ups`).then(r => r.json()),
            fetch(`${API_BASE}/api/products`).then(r => r.json())
        ]);

        const followUps  = safeArray(fuRes.status === 'fulfilled' ? fuRes.value?.data : []);
        const products   = safeArray(stockRes.status === 'fulfilled' ? stockRes.value?.data : []);

        // Pending follow-ups
        const pendingFU = followUps.filter(f =>
            (f.status || '').toLowerCase() !== 'completed'
        );

        // Low-stock items
        const lowStock = products.filter(p =>
            (p.stock_quantity ?? p.quantity ?? 0) <= (p.safety_threshold ?? 10)
        );

        const allItems = [
            ...pendingFU.map(f => ({
                type:     'followup',
                title:    f.title || 'Follow-up reminder',
                priority: (f.priority || 'medium').toLowerCase(),
                date:     f.scheduled_date || '',
                status:   f.status || 'Pending'
            })),
            ...lowStock.map(p => ({
                type:     'stock',
                title:    `Low stock: ${p.name || p.product_name || 'Product'}`,
                priority: 'high',
                date:     '',
                status:   'Alert'
            }))
        ];

        const totalCount = allItems.length;

        // Update badge
        if (badge) {
            if (totalCount > 0) {
                badge.textContent = totalCount > 99 ? '99+' : totalCount;
                badge.style.display = 'flex';
            } else {
                badge.style.display = 'none';
            }
        }

        // Keep existing bell-dot logic in sync
        if (bellDot) bellDot.style.display = totalCount > 0 ? 'block' : 'none';

        renderNotifications(allItems);

    } catch (err) {
        if (body) body.innerHTML = `<div class="notif-empty-state"><p style="color:#ef4444;font-size:12px;">Could not load notifications</p></div>`;
        console.error("loadNotifications error:", err);
    }
}

function renderNotifications(items) {
    const body = document.getElementById("notif-dropdown-body");
    if (!body) return;

    if (!items || items.length === 0) {
        body.innerHTML = `
            <div class="notif-empty-state">
                <i data-lucide="check-circle" style="width:32px;height:32px;margin-bottom:10px;opacity:0.4;"></i>
                <p>All clear — no pending alerts</p>
            </div>`;
        if (typeof lucide !== "undefined") lucide.createIcons();
        return;
    }

    // Sort: high first, then medium, then low
    const priorityOrder = { high: 0, medium: 1, low: 2 };
    items.sort((a, b) => (priorityOrder[a.priority] ?? 1) - (priorityOrder[b.priority] ?? 1));

    body.innerHTML = items.map(item => {
        const dotClass   = item.priority === 'high' ? 'high' : (item.priority === 'medium' ? 'medium' : 'low');
        const typeLabel  = item.type === 'followup' ? 'Follow-up' : 'Stock Alert';
        const typeColor  = item.type === 'stock'    ? 'rgba(239,68,68,0.15)' : 'rgba(99,102,241,0.15)';
        const typeText   = item.type === 'stock'    ? '#fca5a5' : '#a5b4fc';
        const dateStr    = item.date
            ? `<span>📅 ${item.date}</span>`
            : `<span style="color:#ef4444;">⚠ Restock needed</span>`;

        const titleSafe  = (item.title || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');

        return `
            <div class="notif-item unread">
                <div class="notif-dot ${dotClass}"></div>
                <div class="notif-content">
                    <div class="notif-content-title" title="${titleSafe}">${titleSafe}</div>
                    <div class="notif-content-meta">
                        <span class="notif-type-tag" style="background:${typeColor};color:${typeText};">${typeLabel}</span>
                        ${dateStr}
                    </div>
                </div>
            </div>
        `;
    }).join('');

    if (typeof lucide !== "undefined") lucide.createIcons();
}

function markAllNotificationsRead(e) {
    if (e) e.stopPropagation();
    const body  = document.getElementById("notif-dropdown-body");
    const badge = document.getElementById("notif-badge-count");
    const bellDot = document.getElementById("bell-dot-alert");

    // Visually clear all unread states
    document.querySelectorAll(".notif-item.unread").forEach(el => el.classList.remove("unread"));

    if (badge)   badge.style.display = 'none';
    if (bellDot) bellDot.style.display = 'none';

    if (body) {
        body.innerHTML = `
            <div class="notif-empty-state">
                <i data-lucide="check-circle" style="width:32px;height:32px;margin-bottom:10px;opacity:0.4;"></i>
                <p>All notifications marked as read</p>
            </div>`;
        if (typeof lucide !== "undefined") lucide.createIcons();
    }

    showNotification("All notifications marked as read.", "success");
}

// --- Navigation & Routing ---
function initNavigation() {
    const menuItems = document.querySelectorAll(".menu-item");
    menuItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            const tabName = item.getAttribute("data-tab");
            switchTab(tabName);
        });
    });
}
function switchTab(tabName) {
    // Toggle active menu class
    document.querySelectorAll(".menu-item").forEach(menu => {
        if (menu.getAttribute("data-tab") === tabName) {
            menu.classList.add("active");
        } else {
            menu.classList.remove("active");
        }
    });
    // Toggle active tab pane
    document.querySelectorAll(".tab-pane").forEach(pane => {
        if (pane.id === `pane-${tabName}`) {
            pane.classList.add("active");
        } else {
            pane.classList.remove("active");
        }
    });
    // Trigger specific loaders
    if (tabName === "dashboard") loadDashboardMetrics();
    else if (tabName === "orders") {
        loadOrdersTab();
    }
    else if (tabName === "stock") {
        loadStockTab();
    }
    else if (tabName === "crm") {
        loadCRMTab();
    }
    else if (tabName === "deliveries") {
        loadDeliveriesTab();
    }
    else if (tabName === "credit") {
        loadCreditTab();
    }
    else if (tabName === "vendors") {
        loadVendorsTab();
    }
    else if (tabName === "profitability") {
        loadProfitabilityTab();
    }
    else if (tabName === "insights") {
        loadInsightsTab();
    }
    else if (tabName === "followups") {
        loadFollowupsTab();
    }
    else if (tabName === "logs") {
        loadWorkflowLogsTab();
    }
}
// --- Data Fetching Operations ---
function loadAllData() {
    loadDashboardMetrics();
    // Pre-cache other metadata dropdowns
    fetchDealersList();
    fetchProductsList();
    // Refresh notification badge count
    loadNotifications();
}
// 1. Dashboard Tab Data
async function loadDashboardMetrics() {
    try {
        const res = await fetch(`${API_BASE}/api/dashboard`);
        const result = await res.json();
        if (!result.success) throw new Error(result.error);
        const data = result.metrics;
        
        // Populate KPI Metrics
        document.getElementById("metric-revenue").innerText = `Rs ${data.total_revenue.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        document.getElementById("metric-outstanding").innerText = `Rs ${data.total_credit_dues.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        document.getElementById("metric-dealers").innerText = data.active_dealers;
        document.getElementById("metric-stock-alert").innerText = data.low_stock_alerts;
        // Alerts badges
        const alertBadge = document.getElementById("text-stock-alert");
        const bellDot = document.getElementById("bell-dot-alert");
        if (alertBadge) {
            if (data.low_stock_alerts > 0) {
                alertBadge.classList.add("text-danger");
                alertBadge.innerText = `${data.low_stock_alerts} SKUs below safety threshold`;
            } else {
                alertBadge.classList.remove("text-danger");
                alertBadge.innerText = "All SKUs fully stocked";
            }
        }
        if (bellDot) {
            bellDot.style.display = data.low_stock_alerts > 0 ? "block" : "none";
        }
        // Overdue count badge
        const overdueBadge = document.getElementById("badge-ai-alerts");
        if (overdueBadge) {
            overdueBadge.innerText = data.overdue_followups;
        }
        // Populate Recent Orders Table
        const recentTbody = document.getElementById("dashboard-recent-orders");
        recentTbody.innerHTML = "";
        
        if (result.recent_orders.length === 0) {
            recentTbody.innerHTML = `<tr><td colspan="5" class="text-center">No orders registered yet</td></tr>`;
        } else {
            result.recent_orders.forEach(order => {
                const date = new Date(order.order_date).toLocaleDateString();
                const statusBadge = getStatusBadge(order.payment_status);
                recentTbody.innerHTML += `
                    <tr>
                        <td><strong>#ORD-${order.id}</strong></td>
                        <td>${order.dealer_name}</td>
                        <td>${date}</td>
                        <td>Rs ${order.total_amount.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                        <td>${statusBadge}</td>
                    </tr>
                `;
            });
        }
        // Render Category Sales Chart
        renderCategorySalesChart(result.category_data);
        lucide.createIcons();
    } catch (err) {
        console.error("Dashboard Load Error:", err);
        showNotification(`Error loading dashboard: ${err.message}`, "danger");
    }
}
// Render Donut Chart using Chart.js
function renderCategorySalesChart(chartData) {
    const ctx = document.getElementById('chartCategorySales').getContext('2d');
    
    if (categoryChart) {
        categoryChart.destroy();
    }
    if (chartData.length === 0) {
        // Dummy placeholder to keep layout consistent
        chartData = [{ category: "No Sales Yet", value: 1 }];
    }
    const labels = chartData.map(item => item.category || "General");
    const values = chartData.map(item => item.value);
    categoryChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: [
                    '#6366f1', // Indigo
                    '#a855f7', // Violet
                    '#10b981', // Emerald
                    '#f59e0b', // Amber
                    '#3b82f6'  // Blue
                ],
                borderWidth: 1,
                borderColor: '#1f2937'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#f3f4f6',
                        font: { family: 'Plus Jakarta Sans', size: 11 }
                    }
                }
            },
            cutout: '65%'
        }
    });
}

// Trigger Google Sign-In when custom button is clicked
function triggerGoogleSignIn() {
    // Demo mode: directly call backend with a mock google_credential flag
    fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ google_credential: 'demo_token' })
    })
    .then(r => r.json())
    .then(result => {
        if (result.success) {
            sessionStorage.setItem('crm_user', JSON.stringify(result.user));
            document.getElementById('auth-container').style.display = 'none';
            document.getElementById('app-runtime-container').style.display = 'flex';
            const nameEl = document.getElementById('current-user-name');
            const avatarEl = document.getElementById('current-user-avatar');
            if (nameEl) nameEl.innerText = result.user.full_name || result.user.username || 'Admin';
            if (avatarEl) {
                const initials = (result.user.full_name || result.user.username || 'AD')
                    .split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
                avatarEl.innerText = initials;
            }
            loadAllData();
            setupFormListeners();
            if (typeof lucide !== 'undefined') lucide.createIcons();
            showNotification('Signed in with Google successfully!', 'success');
        } else {
            showNotification('Google sign-in failed: ' + result.error, 'danger');
        }
    })
    .catch(err => showNotification('Sign-in error: ' + err.message, 'danger'));
}

// 2. Orders Tab Data
async function loadOrdersTab() {
    await fetchDealersList();
    await fetchProductsList();
    
    // Reset order builder items with a single fresh row
    resetOrderForm();
    
    // Fetch and populate Orders list table
    try {
        const res = await fetch(`${API_BASE}/api/orders`);
        const result = await res.json();
        const orders = Array.isArray(result?.data) ? result.data : [];
        const tbody = document.getElementById("sales-orders-list-table");
        tbody.innerHTML = "";
        if (orders.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center">No sales orders found.</td></tr>`;
        } else {
            orders.forEach(order => {
                const orderItems = Array.isArray(order?.items) ? order.items : [];
                const date = new Date(order.order_date).toLocaleString();
                const itemsCount = orderItems.reduce((acc, i) => acc + (i.quantity || 0), 0);
                const itemsDetails = orderItems.map(i => `${i.product_name} (x${i.quantity})`).join(", ");
                const statusBadge = getStatusBadge(order.payment_status);
                
                tbody.innerHTML += `
                    <tr>
                        <td><strong>#ORD-${order.id}</strong></td>
                        <td>${order.dealer_name}</td>
                        <td>${order.dealer_phone}</td>
                        <td>${date}</td>
                        <td title="${itemsDetails}">${itemsDetails.length > 30 ? itemsDetails.substring(0, 30) + '...' : itemsDetails}</td>
                        <td>Rs ${order.total_amount.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                        <td>
                            <select class="status-select form-group btn-sm" style="padding: 2px 6px; width:110px;" onchange="updateStatus(this, 'order', ${order.id})" ${order.lifecycle_status === 'FINISHED' ? 'disabled' : ''}>
                                <option value="PENDING" ${(order.lifecycle_status || 'PENDING') === 'PENDING' ? 'selected' : ''}>Pending</option>
                                <option value="FINISHED" ${order.lifecycle_status === 'FINISHED' ? 'selected' : ''}>Finished</option>
                            </select>
                        </td>
                        <td>
                            <button class="btn btn-sm btn-outline" onclick="dispatchOrder(${order.id}, '${order.dealer_name}')">
                                <i data-lucide="truck" style="width:12px; height:12px;"></i> Dispatch
                            </button>
                        </td>
                    </tr>
                `;
            });
        }
        lucide.createIcons();
    } catch (err) {
        showNotification(`Error loading orders: ${err.message}`, "danger");
    }
}
// 3. Stock Inventory Tab Data
async function loadStockTab() {
    try {
        const res = await fetch(`${API_BASE}/api/products`);
        const result = await res.json();
        if (!result.success) throw new Error(result.error);
        // Populate table
        const tbody = document.getElementById("stock-list-table");
        tbody.innerHTML = "";
        const select = document.getElementById("stock-product-select");
        select.innerHTML = `<option value="">-- Choose Product --</option>`;
        result.data.forEach(p => {
            const isLowStock = p.stock_quantity <= p.safety_threshold;
            const statusBadge = isLowStock 
                ? `<span class="badge badge-danger">Low Stock</span>` 
                : `<span class="badge badge-success">Available</span>`;
            
            tbody.innerHTML += `
                <tr class="${isLowStock ? 'text-danger' : ''}">
                    <td><strong>${p.name}</strong></td>
                    <td>${p.sku}</td>
                    <td>${p.category || 'N/A'}</td>
                    <td>Rs ${p.price.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                    <td>Rs ${p.cost.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                    <td>${p.stock_quantity} units</td>
                    <td>${p.safety_threshold}</td>
                    <td><span class="current-time">${p.bin_location || 'N/A'}</span></td>
                    <td>${statusBadge}</td>
                </tr>
            `;
            // Populate quick forms selection
            select.innerHTML += `<option value="${p.id}">${p.name} (${p.sku})</option>`;
        });
        
        lucide.createIcons();
    } catch (err) {
        showNotification(`Error loading stock: ${err.message}`, "danger");
    }
}
// 4. CRM Tab Data
async function loadCRMTab() {
    if (crmActiveView === "customers") {
        await loadCustomersCRM();
        return;
    }
    try {
        const res = await fetch(`${API_BASE}/api/dealers`);
        const result = await res.json();
        if (!result.success) throw new Error(result.error);
        const dealers = Array.isArray(result?.data) ? result.data : [];
        const profilesContainer = document.getElementById("crm-dealers-profiles");
        profilesContainer.innerHTML = "";
        if (dealers.length === 0) {
            profilesContainer.innerHTML = `<div class="text-center text-muted">No dealer profiles registered yet.</div>`;
            return;
        }
        dealers.forEach(dl => {
            const statusClass = dl.status === 'Active' ? 'badge-success' : (dl.status === 'Blocked' ? 'badge-danger' : 'badge-warning');
            const followUpStr = dl.follow_up_date ? `Next call: ${dl.follow_up_date}` : 'No follow-up set';
            
            profilesContainer.innerHTML += `
                <div class="dealer-profile-card" onclick="openDealerDetailModal(${dl.id})">
                    <div class="dealer-card-left">
                        <h4>${dl.name}</h4>
                        <div class="dealer-card-sub">
                            <span>Type: <strong>${dl.type}</strong></span>
                            <span>Phone: <strong>${dl.phone}</strong></span>
                        </div>
                        <div class="help-text">${followUpStr}</div>
                    </div>
                    <div class="dealer-card-right">
                        <span class="badge ${statusClass}">${dl.status}</span>
                        <div class="balance-text">Balance: Rs ${(dl.balance || 0).toLocaleString('en-IN')}</div>
                    </div>
                </div>
            `;
        });
    } catch (err) {
        showNotification(`Error loading CRM profiles: ${err.message}`, "danger");
    }
}

function switchCRMView(view) {
    try {
        crmActiveView = view === "customers" ? "customers" : "dealers";

        const dealersTab = document.getElementById("crm-tab-dealers");
        const customersTab = document.getElementById("crm-tab-customers");
        const dealerFormBox = document.getElementById("crm-add-dealer-box");
        const customerFormBox = document.getElementById("crm-add-customer-box");
        const dealersWrapper = document.getElementById("dealers-profiles-wrapper");
        const customersWrapper = document.getElementById("customers-profiles-wrapper");

        if (dealersTab) dealersTab.classList.toggle("active", crmActiveView === "dealers");
        if (customersTab) customersTab.classList.toggle("active", crmActiveView === "customers");
        if (dealerFormBox) dealerFormBox.style.display = crmActiveView === "dealers" ? "" : "none";
        if (customerFormBox) customerFormBox.style.display = crmActiveView === "customers" ? "" : "none";
        if (dealersWrapper) dealersWrapper.style.display = crmActiveView === "dealers" ? "" : "none";
        if (customersWrapper) customersWrapper.style.display = crmActiveView === "customers" ? "" : "none";

        if (crmActiveView === "customers") {
            loadCustomersCRM();
        } else {
            loadCRMTab();
        }
    } catch (err) {
        showNotification(`CRM view switch failed: ${err.message}`, "danger");
    }
}

async function loadCustomersCRM() {
    try {
        const res = await fetch(`${API_BASE}/api/customers`);
        const result = await res.json();
        if (!result.success) throw new Error(result.error || "Failed to load customers");

        const customers = Array.isArray(result?.data) ? result.data : [];
        const profilesContainer = document.getElementById("crm-customers-profiles");
        if (!profilesContainer) return;

        profilesContainer.innerHTML = "";
        if (customers.length === 0) {
            profilesContainer.innerHTML = `<div class="text-center text-muted">No direct customer profiles registered yet.</div>`;
            return;
        }

        customers.forEach(cust => {
            const statusClass = cust.status === 'Active' ? 'badge-success' : (cust.status === 'Blocked' ? 'badge-danger' : 'badge-warning');
            profilesContainer.innerHTML += `
                <div class="dealer-profile-card">
                    <div class="dealer-card-left">
                        <h4>${cust.name}</h4>
                        <div class="dealer-card-sub">
                            <span>Company: <strong>${cust.company || 'Retail Customer'}</strong></span>
                            <span>Phone: <strong>${cust.phone}</strong></span>
                        </div>
                        <div class="help-text">${cust.address || 'No address on file'}</div>
                    </div>
                    <div class="dealer-card-right">
                        <span class="badge ${statusClass}">${cust.status || 'Active'}</span>
                        <div class="help-text">Owner: ${cust.owner || 'Unassigned'}</div>
                    </div>
                </div>
            `;
        });
    } catch (err) {
        showNotification(`Error loading direct customers: ${err.message}`, "danger");
    }
}

function cancelCustomerEdit() {
    const form = document.getElementById("form-create-customer");
    const editId = document.getElementById("edit-customer-id");
    const submitBtn = document.getElementById("btn-submit-customer");
    const cancelBtn = document.getElementById("btn-cancel-customer-edit");
    if (form) form.reset();
    if (editId) editId.value = "";
    if (submitBtn) submitBtn.innerHTML = `<i data-lucide="user-plus"></i> Save Customer Profile`;
    if (cancelBtn) cancelBtn.style.display = "none";
    if (typeof lucide !== "undefined") lucide.createIcons();
}

// 10. Follow-ups Reminders Tab
async function loadFollowupsTab() {
    const tbody = document.getElementById("followups-list-table");
    if (!tbody) return;

    try {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center">Loading reminders list...</td></tr>`;
        const res = await fetch(`${API_BASE}/api/follow-ups`);
        const result = await res.json();
        const followups = Array.isArray(result?.data) ? result.data : [];

        tbody.innerHTML = "";

        if (!result?.success) throw new Error(result?.error || "Failed to load follow-ups");

        if (followups.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center">No reminders scheduled yet.</td></tr>`;
            return;
        }

        followups.forEach(f => {
            const priorityClass = f.priority === 'High' ? 'badge-danger' : (f.priority === 'Medium' ? 'badge-warning' : 'badge-info');
            const statusClass   = f.status === 'Completed' ? 'badge-success' : 'badge-warning';
            const dateStr = f.scheduled_date || '—';

            tbody.innerHTML += `
                <tr>
                    <td>
                        <strong>${f.title || '—'}</strong>
                        ${f.notes ? `<br><span class="help-text" style="font-size:11px;">${f.notes}</span>` : ''}
                    </td>
                    <td>${dateStr}</td>
                    <td><span class="badge ${priorityClass}">${f.priority || 'Medium'}</span></td>
                    <td><span class="badge ${statusClass}">${f.status || 'Pending'}</span></td>
                    <td>
                        ${(f.status || 'Pending') !== 'Completed' ? `
                        <button class="btn btn-sm btn-outline" style="padding:3px 10px; font-size:11px;"
                            onclick="markFollowupComplete(${f.id})">
                            <i data-lucide="check-circle" style="width:11px;height:11px;"></i> Complete
                        </button>` : '<span class="text-muted" style="font-size:11px;">Done</span>'}
                    </td>
                </tr>
            `;
        });

        if (typeof lucide !== "undefined") lucide.createIcons();
    } catch (err) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">Error: ${err.message}</td></tr>`;
        showNotification(`Failed to load reminders: ${err.message}`, "danger");
    }
}

async function markFollowupComplete(followupId) {
    try {
        const res = await fetch(`${API_BASE}/api/follow-ups/${followupId}/complete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const result = await res.json();
        if (!result.success) throw new Error(result.error);
        showNotification("Reminder marked as completed.", "success");
        loadFollowupsTab();
    } catch (err) {
        showNotification(`Could not complete reminder: ${err.message}`, "danger");
    }
}

async function loadWorkflowLogsTab() {
    const tbody = document.getElementById("workflow-logs-stream-table");
    if (!tbody) return;

    try {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center">Loading logs audit stream...</td></tr>`;
        const res = await fetch(`${API_BASE}/api/workflow/logs`);
        const result = await res.json();
        const logs = Array.isArray(result?.data) ? result.data : [];

        tbody.innerHTML = "";
        if (!result?.success) {
            throw new Error(result?.error || "Failed to load workflow logs");
        }
        if (logs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center">No workflow audit entries recorded yet.</td></tr>`;
            return;
        }

        logs.forEach(log => {
            try {
                const timestamp = log?.timestamp ? new Date(log.timestamp).toLocaleString() : "N/A";
                tbody.innerHTML += `
                    <tr>
                        <td><strong>#LOG-${log?.id ?? "-"}</strong></td>
                        <td>${log?.event_type || "UNKNOWN"}</td>
                        <td>${log?.entity_type || "N/A"}</td>
                        <td>${log?.entity_id ?? "-"}</td>
                        <td><span class="badge badge-info">${log?.status || "Success"}</span></td>
                        <td><span class="current-time">${timestamp}</span></td>
                    </tr>
                `;
            } catch (rowErr) {
                console.error("Workflow log row render error:", rowErr);
            }
        });
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">Error loading workflow logs: ${err.message}</td></tr>`;
        showNotification(`Error loading workflow logs: ${err.message}`, "danger");
    }
}

async function updateStatus(selectEl, entityType, entityId) {
    if (!selectEl || !entityId) return;
    const newStatus = selectEl.value;
    try {
        if (entityType === "order") {
            await updateOrderStatus(entityId, newStatus);
        } else if (entityType === "delivery") {
            await updateDeliveryStatus(entityId, newStatus);
        }
    } catch (err) {
        showNotification(`Status update failed: ${err.message}`, "danger");
    }
}

async function updateOrderStatus(orderId, newStatus) {
    if (!confirm(`Update order #${orderId} status to ${newStatus}?`)) return;
    // Normalize to uppercase before sending
    const normalizedStatus = newStatus.trim().toUpperCase();
    try {
        const res = await fetch(`${API_BASE}/api/orders/${orderId}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: normalizedStatus })
        });
        const result = await res.json();
        if (result.success) {
            showNotification(result.message, 'success');
            loadOrdersTab(); // Refresh the table
            loadDashboardMetrics(); // Refresh dashboard stats
        } else {
            showNotification(result.error, 'danger');
        }
    } catch (err) {
        showNotification(err.message, 'danger');
    }
}

// 5. Deliveries Tab Data
async function loadDeliveriesTab() {
    // Populate pending orders for dispatch assignment select
    try {
        const resOrd = await fetch(`${API_BASE}/api/orders`);
        const resultOrd = await resOrd.json();
        const orders = Array.isArray(resultOrd?.data) ? resultOrd.data : [];

        const orderSelect = document.getElementById("del-order-select");
        orderSelect.innerHTML = `<option value="">-- Choose Sales Order --</option>`;
        orders.forEach(order => {
            orderSelect.innerHTML += `<option value="${order.id}">Order #ORD-${order.id} - ${order.dealer_name} (Rs ${order.total_amount})</option>`;
        });
        // Load dispatch logs
        const res = await fetch(`${API_BASE}/api/deliveries`);
        const result = await res.json();
        const deliveries = Array.isArray(result?.data) ? result.data : [];
        const tbody = document.getElementById("deliveries-list-table");
        tbody.innerHTML = "";
        if (deliveries.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center">No delivery dispatches active.</td></tr>`;
        } else {
            deliveries.forEach(d => {
                const date = new Date(d.assignment_date).toLocaleString();
                const statusClass = d.status === 'Delivered' ? 'badge-success' : (d.status === 'Dispatched' ? 'badge-info' : (d.status === 'Cancelled' ? 'badge-danger' : 'badge-warning'));
                
                tbody.innerHTML += `
                    <tr>
                        <td><strong>#DEL-${d.id}</strong></td>
                        <td>#ORD-${d.order_id}</td>
                        <td>
                            <strong>${d.dealer_name}</strong><br>
                            <span class="help-text">${d.dealer_address || 'No Address'}</span>
                        </td>
                        <td>
                            ${d.delivery_person}<br>
                            <span class="current-time">${d.vehicle_no}</span>
                        </td>
                        <td>${d.route}</td>
                        <td>${date}</td>
                        <td><span class="badge ${statusClass}">${d.status}</span></td>
                        <td>
                            ${(d.lifecycle_status || 'PENDING') !== 'FINISHED' ? `
                            <select class="status-select form-group btn-sm" style="padding: 2px 6px; width:110px;" onchange="updateStatus(this, 'delivery', ${d.id})" ${(d.lifecycle_status || 'PENDING') === 'FINISHED' ? 'disabled' : ''}>
                                <option value="PENDING" ${(d.lifecycle_status || 'PENDING') === 'PENDING' ? 'selected' : ''}>Pending</option>
                                <option value="FINISHED" ${d.lifecycle_status === 'FINISHED' ? 'selected' : ''}>Finished</option>
                            </select>
                            <button class="btn btn-sm btn-outline" style="padding:3px 8px; font-size:10px; margin-left:4px;" onclick="editDelivery(${d.id})">
                                <i data-lucide="edit-3" style="width:10px;height:10px;"></i> Edit
                            </button>
                            <button class="btn btn-sm" style="padding:3px 8px; font-size:10px; background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.3); color:#ef4444; border-radius:6px; margin-left:4px;" onclick="deleteDelivery(${d.id})">
                                <i data-lucide="trash-2" style="width:10px;height:10px;"></i> Delete
                            </button>` : '-'}
                        </td>
                    </tr>
                `;
            });
        }
    } catch (err) {
        showNotification(`Error loading deliveries: ${err.message}`, "danger");
    }
}
function dispatchOrder(orderId, dealerName) {
    switchTab("deliveries");
    document.getElementById("del-order-select").value = orderId;
    showNotification(`Dispatch configuration loaded for ${dealerName}`);
}
async function updateDeliveryStatus(deliveryId, nextStatus) {
    if (!nextStatus) return;
    // Normalize to uppercase before sending — ensures server validation always passes
    const normalizedStatus = nextStatus.trim().toUpperCase();
    try {
        const res = await fetch(`${API_BASE}/api/deliveries/${deliveryId}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: normalizedStatus })
        });
        const result = await res.json();
        if (!result.success) throw new Error(result.error);
        
        showNotification(`Delivery status updated to ${normalizedStatus}!`);
        loadDeliveriesTab();
    } catch (err) {
        showNotification(`Status update failed: ${err.message}`, "danger");
    }
}

async function editDelivery(deliveryId) {
    const driver = prompt("Enter new Delivery Driver Name:");
    if (driver === null) return;
    const vehicle = prompt("Enter new Vehicle Number:");
    if (vehicle === null) return;
    const route = prompt("Enter new Dispatch Route:");
    if (route === null) return;

    try {
        const res = await fetch(`${API_BASE}/api/deliveries/${deliveryId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                delivery_person: driver.trim(),
                vehicle_no: vehicle.trim(),
                route: route.trim()
            })
        });
        const result = await res.json();
        if (!result.success) throw new Error(result.error);
        showNotification("Delivery dispatch details updated successfully.");
        loadDeliveriesTab();
    } catch (err) {
        showNotification(`Edit delivery failed: ${err.message}`, "danger");
    }
}

async function deleteDelivery(deliveryId) {
    if (!confirm("Are you sure you want to delete this delivery record?")) return;
    try {
        const res = await fetch(`${API_BASE}/api/deliveries/${deliveryId}`, {
            method: 'DELETE'
        });
        const result = await res.json();
        if (!result.success) throw new Error(result.error);
        showNotification("Delivery record deleted successfully.");
        loadDeliveriesTab();
    } catch (err) {
        showNotification(`Delete delivery failed: ${err.message}`, "danger");
    }
}
// 6. Credit Sales Tab Data
async function loadCreditTab() {
    await fetchDealersList();
    try {
        const res = await fetch(`${API_BASE}/api/dealers`);
        const result = await res.json();
        if (!result.success) throw new Error(result.error);
        const tbody = document.getElementById("credit-ledger-table");
        tbody.innerHTML = "";
        result.data.forEach(dl => {
            const usagePercent = dl.credit_limit > 0 ? Math.min(100, Math.round((dl.balance / dl.credit_limit) * 100)) : 0;
            const progressColor = usagePercent > 90 ? 'bg-danger' : (usagePercent > 60 ? 'bg-warning' : 'bg-success');
            const statusClass = dl.status === 'Active' ? 'badge-success' : (dl.status === 'Blocked' ? 'badge-danger' : 'badge-warning');
            
            // Risk calculation based on outstanding dues
            let riskLabel = "Low Risk";
            let riskClass = "badge-success";
            if (dl.status === 'Blocked') {
                riskLabel = "Blocked / Default";
                riskClass = "badge-danger";
            } else if (usagePercent >= 90) {
                riskLabel = "High Risk Limit Out";
                riskClass = "badge-danger";
            } else if (usagePercent > 60 || dl.balance > 25000) {
                riskLabel = "Medium Risk Alert";
                riskClass = "badge-warning";
            }
            tbody.innerHTML += `
                <tr>
                    <td><strong>${dl.name}</strong></td>
                    <td>${dl.type}</td>
                    <td>Rs ${dl.credit_limit.toLocaleString('en-IN')}</td>
                    <td class="text-warning"><strong>Rs ${dl.balance.toLocaleString('en-IN')}</strong></td>
                    <td>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <div style="background:#2d3748; height:6px; width:80px; border-radius:3px; overflow:hidden;">
                                <div style="width:${usagePercent}%; height:100%;" class="${progressColor}"></div>
                            </div>
                            <span>${usagePercent}%</span>
                        </div>
                    </td>
                    <td><span class="badge ${statusClass}">${dl.status}</span></td>
                    <td><span class="badge ${riskClass}">${riskLabel}</span></td>
                </tr>
            `;
        });
    } catch (err) {
        showNotification(`Error loading credit tracker: ${err.message}`, "danger");
    }
}
// 7. Vendor Replenishment Tab Data
async function loadVendorsTab() {
    await fetchProductsList();
    
    // Load dropdown in vendor purchase
    try {
        const resP = await fetch(`${API_BASE}/api/products`);
        const resultP = await resP.json();
        
        const select = document.getElementById("vendor-product-select");
        select.innerHTML = `<option value="">-- Select SKU --</option>`;
        const products = Array.isArray(resultP?.data) ? resultP.data : [];
        products.forEach(p => {
            select.innerHTML += `<option value="${p.id}">${p.name} (${p.sku})</option>`;
        });
        // Load recent supplier purchases
        const res = await fetch(`${API_BASE}/api/vendors`);
        const result = await res.json();
        if (!result.success) throw new Error(result.error);
        const purchases = Array.isArray(result?.data) ? result.data : [];
        const tbody = document.getElementById("vendor-purchases-table");
        tbody.innerHTML = "";
        if (purchases.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center">No vendor replenishments recorded.</td></tr>`;
        } else {
            purchases.forEach(vp => {
                const date = new Date(vp.purchase_date).toLocaleString();
                tbody.innerHTML += `
                    <tr>
                        <td><strong>#VPO-${vp.id}</strong></td>
                        <td>${vp.vendor_name}</td>
                        <td>${vp.product_name} (${vp.sku})</td>
                        <td>${vp.quantity} units</td>
                        <td>Rs ${vp.unit_cost.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                        <td class="text-danger">Rs ${vp.total_amount.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                        <td>${date}</td>
                    </tr>
                `;
            });
        }
    } catch (err) {
        showNotification(`Error loading supplier logs: ${err.message}`, "danger");
    }
}
// 8. Profitability Tab Data
async function loadProfitabilityTab() {
    try {
        const res = await fetch(`${API_BASE}/api/profitability`);
        const result = await res.json();
        if (!result.success) throw new Error(result.error);
        const s = result.summary;
        
        // Update stats card
        document.getElementById("margin-revenue").innerText = `Rs ${s.total_revenue.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
        document.getElementById("margin-cogs").innerText = `Rs ${s.total_cogs.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
        
        const profitEl = document.getElementById("margin-profit");
        profitEl.innerText = `Rs ${s.gross_profit.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
        if (s.gross_profit < 0) {
            profitEl.className = "text-danger";
        } else {
            profitEl.className = "text-success";
        }
        document.getElementById("margin-rate").innerText = `${s.margin_percent.toFixed(1)}%`;
        document.getElementById("profit-stock-valuation").innerText = `Rs ${s.inventory_valuation.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
        document.getElementById("profit-vendor-expense").innerText = `Rs ${s.total_vendor_expenses.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
        // Product profitability details table
        const tbody = document.getElementById("profitability-table-body");
        tbody.innerHTML = "";
        result.product_margins.forEach(item => {
            const marginColorClass = item.unit_margin_percent > 20 ? 'text-success' : (item.unit_margin_percent > 10 ? 'text-warning' : 'text-danger');
            tbody.innerHTML += `
                <tr>
                    <td>
                        <strong>${item.name}</strong><br>
                        <span class="help-text">${item.sku} | ${item.category || 'General'}</span>
                    </td>
                    <td>${item.units_sold} units</td>
                    <td>Rs ${item.price.toLocaleString('en-IN')}</td>
                    <td>Rs ${item.cost.toLocaleString('en-IN')}</td>
                    <td>Rs ${item.profit_per_unit.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                    <td><strong class="${marginColorClass}">${item.unit_margin_percent.toFixed(1)}%</strong></td>
                </tr>
            `;
        });
    } catch (err) {
        showNotification(`Error loading profitability margin matrix: ${err.message}`, "danger");
    }
}
// 9. AI Insights Tab Data
async function loadInsightsTab() {
    try {
        const res = await fetch(`${API_BASE}/api/ai/insights`);
        const result = await res.json();
        if (!result.success) throw new Error(result.error);
        const container = document.getElementById("ai-insights-container");
        container.innerHTML = "";
        result.data.forEach(item => {
            let healthClass = "health-good";
            let healthBadgeClass = "badge-success";
            
            if (item.health === "Critical") {
                healthClass = "health-critical";
                healthBadgeClass = "badge-danger";
            } else if (item.health === "High Risk") {
                healthClass = "health-critical";
                healthBadgeClass = "badge-danger";
            } else if (item.health === "Action Required") {
                healthClass = "health-warn";
                healthBadgeClass = "badge-warning";
            } else if (item.health === "Medium Risk") {
                healthClass = "health-warn";
                healthBadgeClass = "badge-warning";
            }
            container.innerHTML += `
                <div class="ai-insight-card ${healthClass}">
                    <div class="ai-card-details">
                        <h4>${item.name} <span class="badge ${healthBadgeClass}">${item.health}</span></h4>
                        <div class="ai-meta-rows">
                            <div><strong>Type:</strong> ${item.type}</div>
                            <div><strong>Executive Owner:</strong> ${item.owner}</div>
                            <div><strong>Outstanding Dues:</strong> Rs ${item.balance.toLocaleString('en-IN')}</div>
                            <div><strong>Last Order Registered:</strong> ${item.last_order}</div>
                        </div>
                        <p class="help-text"><strong>Health Review:</strong><br>${item.summary}</p>
                    </div>
                    
                    <div class="ai-card-assistant">
                        <div class="ai-action-header" style="display:flex; justify-content:space-between; align-items:center; font-weight:600;">
                            <span>Follow-up Action Suggestion</span>
                            <span class="badge badge-info" style="font-size:9px;">${item.next_step}</span>
                        </div>
                        <div class="ai-message-box">
                            <button class="btn-copy" onclick="copyToClipboard(this, this.nextSibling.textContent)">Copy</button>
                            ${item.suggested_message}
                        </div>
                    </div>
                </div>
            `;
        });
        lucide.createIcons();
    } catch (err) {
        showNotification(`Error scanning AI insights: ${err.message}`, "danger");
    }
}
// --- Dynamic Form Metadata Loaders ---
async function fetchDealersList() {
    try {
        const res = await fetch(`${API_BASE}/api/dealers`);
        const result = await res.json();
        
        // List of forms to update
        const selects = [
            document.getElementById("order-dealer-select"),
            document.getElementById("pay-dealer-select")
        ];
        selects.forEach(sel => {
            if (!sel) return;
            const currentVal = sel.value;
            sel.innerHTML = `<option value="">-- Choose Account --</option>`;
            result.data.forEach(dl => {
                sel.innerHTML += `<option value="${dl.id}" data-balance="${dl.balance}">${dl.name} (${dl.type} - Dues: Rs ${dl.balance})</option>`;
            });
            sel.value = currentVal; // Preserve selection if refreshed
        });
    } catch (err) {
        console.error("Error cache loading dealer names:", err);
    }
}
async function fetchProductsList() {
    try {
        const res = await fetch(`${API_BASE}/api/products`);
        const result = await res.json();
        
        // Cache products globally for dynamic item order rows
        window.productsCatalogueCache = result.data;
    } catch (err) {
        console.error("Error cache loading product catalog:", err);
    }
}
// --- Order Items Rows Builder Logic ---
function resetOrderForm() {
    document.getElementById("form-create-order").reset();
    const container = document.getElementById("order-items-list");
    container.innerHTML = "";
    addOrderItemRow(); // add first item row
    updateOrderTotalEstimate();
}
function addOrderItemRow() {
    const container = document.getElementById("order-items-list");
    const rowId = Date.now() + Math.random().toString(36).substring(7);
    let productOptions = `<option value="">-- Select SKU --</option>`;
    if (window.productsCatalogueCache) {
        window.productsCatalogueCache.forEach(p => {
            productOptions += `<option value="${p.id}" data-price="${p.price}" data-stock="${p.stock_quantity}">${p.name} (Rs ${p.price} | Stock: ${p.stock_quantity})</option>`;
        });
    }
    const rowHTML = `
        <div class="order-item-row" id="row-${rowId}">
            <div class="form-group">
                <label>Select Wholesale SKU</label>
                <select class="item-product-select" onchange="onOrderItemChange()" required>
                    ${productOptions}
                </select>
            </div>
            <div class="form-group">
                <label>Qty to Order</label>
                <input type="number" class="item-qty-input" min="1" value="1" oninput="onOrderItemChange()" required>
            </div>
            <div class="form-group">
                <label>Estimated Price</label>
                <input type="text" class="item-price-estimate" readonly value="Rs 0.00">
            </div>
            <button type="button" class="btn-remove" onclick="removeOrderItemRow('${rowId}')" title="Delete Row">
                <i data-lucide="trash-2" style="width:16px; height:16px;"></i>
            </button>
        </div>
    `;
    
    const div = document.createElement("div");
    div.innerHTML = rowHTML;
    container.appendChild(div.firstElementChild);
    lucide.createIcons();
}
function removeOrderItemRow(rowId) {
    const row = document.getElementById(`row-${rowId}`);
    if (row) {
        row.remove();
        updateOrderTotalEstimate();
    }
}
function onOrderItemChange() {
    updateOrderTotalEstimate();
}
function updateOrderTotalEstimate() {
    const rows = document.querySelectorAll(".order-item-row");
    let grandTotal = 0.0;
    rows.forEach(row => {
        const select = row.querySelector(".item-product-select");
        const qtyInput = row.querySelector(".item-qty-input");
        const estimateInput = row.querySelector(".item-price-estimate");
        const selectedOption = select.options[select.selectedIndex];
        const qty = parseInt(qtyInput.value) || 0;
        
        if (selectedOption && selectedOption.value) {
            const price = parseFloat(selectedOption.getAttribute("data-price")) || 0.0;
            const itemTotal = price * qty;
            grandTotal += itemTotal;
            estimateInput.value = `Rs ${itemTotal.toLocaleString('en-IN', {minimumFractionDigits:2})}`;
        } else {
            estimateInput.value = "Rs 0.00";
        }
    });
    document.getElementById("order-total-price").innerText = `Rs ${grandTotal.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
}
// --- Modal Dealer Detail Controller ---
async function openDealerDetailModal(dealerId) {
    try {
        const res = await fetch(`${API_BASE}/api/dealers/${dealerId}`);
        const result = await res.json();
        if (!result.success) throw new Error(result.error);
        const dl = result.dealer;
        
        // Set info
        document.getElementById("modal-dealer-name").innerText = dl.name;
        document.getElementById("md-dealer-id").value = dl.id;
        document.getElementById("md-type").innerText = dl.type;
        document.getElementById("md-phone").innerText = dl.phone;
        document.getElementById("md-email").innerText = dl.email || 'N/A';
        document.getElementById("md-address").innerText = dl.address || 'N/A';
        document.getElementById("md-credit-limit").innerText = dl.credit_limit.toLocaleString('en-IN');
        document.getElementById("md-balance").innerText = dl.balance.toLocaleString('en-IN');
        document.getElementById("md-owner").innerText = dl.owner || 'Unassigned';
        document.getElementById("md-follow-up").innerText = dl.follow_up_date || 'No scheduled date';
        // Order history table
        const ordersTbody = document.getElementById("md-orders-history");
        ordersTbody.innerHTML = "";
        if (result.orders.length === 0) {
            ordersTbody.innerHTML = `<tr><td colspan="4" class="text-center">No orders history registered.</td></tr>`;
        } else {
            result.orders.forEach(order => {
                const date = new Date(order.order_date).toLocaleDateString();
                const badge = getStatusBadge(order.payment_status);
                ordersTbody.innerHTML += `
                    <tr>
                        <td>#ORD-${order.id}</td>
                        <td>${date}</td>
                        <td>Rs ${order.total_amount.toLocaleString('en-IN')}</td>
                        <td>${badge}</td>
                    </tr>
                `;
            });
        }
        // Timeline notes
        const timeline = document.getElementById("md-notes-timeline");
        timeline.innerHTML = "";
        if (result.notes.length === 0) {
            timeline.innerHTML = `<div class="text-center text-muted">No interactions logged yet.</div>`;
        } else {
            result.notes.forEach(note => {
                const date = new Date(note.contact_date).toLocaleString();
                const nextFollowupStr = note.next_follow_up ? `<br><span class="text-warning" style="font-size:11px;">Scheduled next call: ${note.next_follow_up}</span>` : '';
                timeline.innerHTML += `
                    <div class="timeline-item">
                        <div class="timeline-time">${date}</div>
                        <div class="timeline-text">${note.note} ${nextFollowupStr}</div>
                        <div class="timeline-owner">Owner: ${note.owner}</div>
                    </div>
                `;
            });
        }
        // Prepopulate note form fields
        document.getElementById("md-note-owner").value = dl.owner !== 'Unassigned' ? dl.owner : 'Srinivas Rao';
        document.getElementById("form-modal-add-note").reset();
        document.getElementById("md-dealer-id").value = dl.id;
        // Show Modal
        document.getElementById("modal-dealer-profile").classList.add("active");
        
        // Setup Modal Closing Listener
        document.getElementById("btn-close-modal").onclick = () => {
            document.getElementById("modal-dealer-profile").classList.remove("active");
        };
        window.onclick = (event) => {
            const modal = document.getElementById("modal-dealer-profile");
            if (event.target == modal) {
                modal.classList.remove("active");
            }
        };
    } catch (err) {
        showNotification(`Failed to load details: ${err.message}`, "danger");
    }
}
// --- Form Listeners Mapping ---
function setupFormListeners() {
    
    // Order Item add click
    document.getElementById("btn-add-order-item").addEventListener("click", addOrderItemRow);
    // Sales Order Form Submit
    document.getElementById("form-create-order").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const dealerId = document.getElementById("order-dealer-select").value;
        const paymentStatus = document.getElementById("order-payment-status").value;
        // Collect order items
        const itemRows = document.querySelectorAll(".order-item-row");
        const items = [];
        let hasInvalidQuantity = false;
        itemRows.forEach(row => {
            const productSelect = row.querySelector(".item-product-select");
            const qtyInput = row.querySelector(".item-qty-input");
            
            const productId = productSelect.value;
            const quantity = parseInt(qtyInput.value) || 0;
            const maxStock = parseInt(productSelect.options[productSelect.selectedIndex].getAttribute("data-stock")) || 0;
            if (quantity <= 0) {
                hasInvalidQuantity = true;
                return;
            }
            if (quantity > maxStock) {
                hasInvalidQuantity = true;
                showNotification(`Order quantity of ${quantity} exceeds available stock of ${maxStock} units!`, "danger");
                return;
            }
            items.push({
                product_id: productId,
                quantity: quantity
            });
        });
        if (hasInvalidQuantity) return;
        if (items.length === 0) {
            showNotification("Please add at least one wholesale product SKU row.", "warning");
            return;
        }
        try {
            const res = await fetch(`${API_BASE}/api/orders`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    dealer_id: dealerId,
                    payment_status: paymentStatus,
                    items: items
                })
            });
            const result = await res.json();
            if (!result.success) throw new Error(result.error);
            showNotification(`Sales Order #${result.order_id} recorded successfully for Rs ${result.total_amount}!`);
            loadOrdersTab();
            loadDashboardMetrics(); // update revenue counts
        } catch (err) {
            showNotification(`Order processing failed: ${err.message}`, "danger");
        }
    });
    // Adjust Stock Levels Form
    document.getElementById("form-update-stock").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const productId = document.getElementById("stock-product-select").value;
        const quantity = document.getElementById("stock-qty-input").value;
        const binLocation = document.getElementById("stock-bin-input").value;
        try {
            const res = await fetch(`${API_BASE}/api/stock/update`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    product_id: productId,
                    quantity: quantity,
                    bin_location: binLocation
                })
            });
            const result = await res.json();
            if (!result.success) throw new Error(result.error);
            showNotification("Warehouse Stock levels successfully adjusted.");
            loadStockTab();
            loadDashboardMetrics();
            document.getElementById("form-update-stock").reset();
        } catch (err) {
            showNotification(`Stock adjustment failed: ${err.message}`, "danger");
        }
    });
    // Initialize New Product SKU Form
    document.getElementById("form-create-product").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const name = document.getElementById("prod-name").value;
        const sku = document.getElementById("prod-sku").value;
        const price = document.getElementById("prod-price").value;
        const cost = document.getElementById("prod-cost").value;
        const category = document.getElementById("prod-category").value;
        const initialStock = document.getElementById("prod-stock").value;
        try {
            const res = await fetch(`${API_BASE}/api/products`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    sku: sku,
                    price: price,
                    cost: cost,
                    category: category,
                    initial_stock: initialStock
                })
            });
            const result = await res.json();
            if (!result.success) throw new Error(result.error);
            showNotification(`New SKU '${name}' registered in warehouse catalog.`);
            loadStockTab();
            document.getElementById("form-create-product").reset();
        } catch (err) {
            showNotification(`SKU creation failed: ${err.message}`, "danger");
        }
    });
    // Register Direct Customer Form
    const customerForm = document.getElementById("form-create-customer");
    if (customerForm) {
        customerForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const customerId = document.getElementById("edit-customer-id")?.value;
            const name = document.getElementById("cust-name").value;
            const company = document.getElementById("cust-company").value;
            const phone = document.getElementById("cust-phone").value;
            const email = document.getElementById("cust-email").value;
            const address = document.getElementById("cust-address").value;
            const owner = document.getElementById("cust-owner").value;
            try {
                const res = await fetch(`${API_BASE}/api/customers`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        id: customerId || undefined,
                        name,
                        company,
                        phone,
                        email,
                        address,
                        owner
                    })
                });
                const result = await res.json();
                if (!result.success) throw new Error(result.error);
                showNotification(result.message || `Customer profile saved for ${name}.`);
                cancelCustomerEdit();
                if (crmActiveView === "customers") {
                    loadCustomersCRM();
                } else {
                    switchCRMView("customers");
                }
            } catch (err) {
                showNotification(`Customer registration failed: ${err.message}`, "danger");
            }
        });
    }

    // Register CRM Account Form
    document.getElementById("form-create-dealer").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const name = document.getElementById("dl-name").value;
        const dtype = document.getElementById("dl-type").value;
        const phone = document.getElementById("dl-phone").value;
        const email = document.getElementById("dl-email").value;
        const address = document.getElementById("dl-address").value;
        const creditLimit = document.getElementById("dl-credit-limit").value;
        const owner = document.getElementById("dl-owner").value;
        const followUpDate = document.getElementById("dl-followup").value;
        try {
            const res = await fetch(`${API_BASE}/api/dealers`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    type: dtype,
                    phone: phone,
                    email: email,
                    address: address,
                    credit_limit: creditLimit,
                    owner: owner,
                    follow_up_date: followUpDate
                })
            });
            const result = await res.json();
            if (!result.success) throw new Error(result.error);
            showNotification(`CRM Profile successfully created for ${name}.`);
            loadCRMTab();
            document.getElementById("form-create-dealer").reset();
        } catch (err) {
            showNotification(`CRM Registration failed: ${err.message}`, "danger");
        }
    });
    // Assign Dispatch Route (Delivery) Form
    document.getElementById("form-assign-delivery").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const orderId = document.getElementById("del-order-select").value;
        const person = document.getElementById("del-person").value;
        const vehicle = document.getElementById("del-vehicle").value;
        const route = document.getElementById("del-route").value;
        try {
            const res = await fetch(`${API_BASE}/api/deliveries`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    order_id: orderId,
                    delivery_person: person,
                    vehicle_no: vehicle,
                    route: route
                })
            });
            const result = await res.json();
            if (!result.success) throw new Error(result.error);
            showNotification("Delivery dispatch assignment successfully scheduled.");
            loadDeliveriesTab();
            document.getElementById("form-assign-delivery").reset();
        } catch (err) {
            showNotification(`Dispatch scheduling failed: ${err.message}`, "danger");
        }
    });
    // Log Dues Payment Receipt (Credit Collection) Form
    document.getElementById("form-record-payment").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const dealerId = document.getElementById("pay-dealer-select").value;
        const amount = document.getElementById("pay-amount").value;
        try {
            const res = await fetch(`${API_BASE}/api/credit/payment`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    dealer_id: dealerId,
                    amount: amount
                })
            });
            const result = await res.json();
            if (!result.success) throw new Error(result.error);
            showNotification(`Credit Payment of Rs ${amount} recorded successfully!`);
            loadCreditTab();
            loadDashboardMetrics();
            document.getElementById("form-record-payment").reset();
            document.getElementById("lbl-current-dues").innerText = "Pending Dues: Rs 0.00";
        } catch (err) {
            showNotification(`Payment logging failed: ${err.message}`, "danger");
        }
    });
    // Dynamic dues notification label in payments form
    document.getElementById("pay-dealer-select").addEventListener("change", (e) => {
        const option = e.target.options[e.target.selectedIndex];
        if (option && option.value) {
            const balance = parseFloat(option.getAttribute("data-balance")) || 0;
            document.getElementById("lbl-current-dues").innerHTML = `Pending Dues: <strong class="text-warning">Rs ${balance.toLocaleString('en-IN')}</strong>`;
        } else {
            document.getElementById("lbl-current-dues").innerText = "Pending Dues: Rs 0.00";
        }
    });
    // Record Supplier Replenishment Form
    document.getElementById("form-vendor-purchase").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const name = document.getElementById("vendor-name-input").value;
        const productId = document.getElementById("vendor-product-select").value;
        const qty = document.getElementById("vendor-qty").value;
        const cost = document.getElementById("vendor-cost").value;
        try {
            const res = await fetch(`${API_BASE}/api/vendors`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    vendor_name: name,
                    product_id: productId,
                    quantity: qty,
                    unit_cost: cost
                })
            });
            const result = await res.json();
            if (!result.success) throw new Error(result.error);
            showNotification(`Recorded replenishment of inventory stocks.`);
            loadVendorsTab();
            loadDashboardMetrics();
            document.getElementById("form-vendor-purchase").reset();
        } catch (err) {
            showNotification(`Replenishment logging failed: ${err.message}`, "danger");
        }
    });
    // Follow-ups Reminder Scheduling Form
    const followupForm = document.getElementById("form-create-followup");
    if (followupForm) {
        followupForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const title         = document.getElementById("fup-title").value.trim();
            const notes         = document.getElementById("fup-notes").value.trim();
            const scheduledDate = document.getElementById("fup-date").value;
            const priority      = document.getElementById("fup-priority").value;

            if (!title || !scheduledDate) {
                showNotification("Task Title and Scheduled Date are required.", "warning");
                return;
            }
            try {
                const res = await fetch(`${API_BASE}/api/follow-ups`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title, notes, scheduled_date: scheduledDate, priority })
                });
                const result = await res.json();
                if (!result.success) throw new Error(result.error);
                showNotification(`Reminder "${title}" scheduled successfully.`, "success");
                followupForm.reset();
                loadFollowupsTab();
            } catch (err) {
                showNotification(`Failed to schedule reminder: ${err.message}`, "danger");
            }
        });
    }

    // Modal Add Note Form Submit
    document.getElementById("form-modal-add-note").addEventListener("submit", async (e) => {        e.preventDefault();
        
        const dealerId = document.getElementById("md-dealer-id").value;
        const note = document.getElementById("md-note-text").value;
        const nextFollowUp = document.getElementById("md-note-followup").value;
        const owner = document.getElementById("md-note-owner").value;
        try {
            const res = await fetch(`${API_BASE}/api/dealers/${dealerId}/notes`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    note: note,
                    next_follow_up: nextFollowUp,
                    owner: owner
                })
            });
            const result = await res.json();
            if (!result.success) throw new Error(result.error);
            showNotification("Interaction note successfully saved.");
            
            // Reload Modal details to show new note in timeline
            openDealerDetailModal(dealerId);
            
            // Refresh underlying CRM and Dashboard metrics
            loadCRMTab();
            loadDashboardMetrics();
        } catch (err) {
            showNotification(`Adding note failed: ${err.message}`, "danger");
        }
    });
}
// --- Global Search Handler ---
function handleGlobalSearch(e) {
    const query = e.target.value.toLowerCase().trim();
    if (!query) {
        // Remove filters: redraw original rows
        document.querySelectorAll("tbody tr").forEach(tr => tr.style.display = "");
        document.querySelectorAll(".dealer-profile-card").forEach(c => c.style.display = "");
        return;
    }
    // Filter table rows on active pane
    const activePane = document.querySelector(".tab-pane.active");
    if (activePane) {
        const rows = activePane.querySelectorAll("tbody tr");
        rows.forEach(row => {
            const text = row.innerText.toLowerCase();
            if (text.includes(query)) {
                row.style.display = "";
            } else {
                row.style.display = "none";
            }
        });
        // Specifically filter CRM cards if on CRM tab
        const cards = activePane.querySelectorAll(".dealer-profile-card");
        cards.forEach(card => {
            const text = card.innerText.toLowerCase();
            if (text.includes(query)) {
                card.style.display = "";
            } else {
                card.style.display = "none";
            }
        });
    }
}
// --- Global Utilities Helpers ---
function getStatusBadge(status) {
    if (status === 'Paid') return `<span class="badge badge-success">Paid</span>`;
    if (status === 'Partial') return `<span class="badge badge-warning">Partial</span>`;
    if (status === 'Pending') return `<span class="badge badge-warning">Pending</span>`;
    if (status === 'Overdue') return `<span class="badge badge-danger">Overdue</span>`;
    return `<span class="badge badge-info">${status}</span>`;
}
function showNotification(message, type = "success") {
    // Elegant temporary floating notification
    const alertDiv = document.createElement("div");
    alertDiv.style.position = "fixed";
    alertDiv.style.bottom = "24px";
    alertDiv.style.right = "24px";
    alertDiv.style.padding = "14px 24px";
    alertDiv.style.borderRadius = "8px";
    alertDiv.style.zIndex = "9999";
    alertDiv.style.boxShadow = "0 10px 30px rgba(0, 0, 0, 0.3)";
    alertDiv.style.fontWeight = "600";
    alertDiv.style.color = "#ffffff";
    alertDiv.style.fontSize = "13px";
    alertDiv.style.display = "flex";
    alertDiv.style.alignItems = "center";
    alertDiv.style.gap = "8px";
    alertDiv.style.animation = "fadeInUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)";
    
    if (type === "success") {
        alertDiv.style.background = "linear-gradient(135deg, #059669 0%, #10b981 100%)";
        alertDiv.style.border = "1px solid rgba(16, 185, 129, 0.3)";
        alertDiv.innerHTML = `&check; ${message}`;
    } else if (type === "danger") {
        alertDiv.style.background = "linear-gradient(135deg, #dc2626 0%, #ef4444 100%)";
        alertDiv.style.border = "1px solid rgba(239, 68, 68, 0.3)";
        alertDiv.innerHTML = `&#9888; ${message}`;
    } else {
        alertDiv.style.background = "linear-gradient(135deg, #d97706 0%, #f59e0b 100%)";
        alertDiv.style.border = "1px solid rgba(245, 158, 11, 0.3)";
        alertDiv.innerHTML = `&#9888; ${message}`;
    }
    document.body.appendChild(alertDiv);
    // Fade out
    setTimeout(() => {
        alertDiv.style.transition = "opacity 0.4s ease, transform 0.4s ease";
        alertDiv.style.opacity = "0";
        alertDiv.style.transform = "translateY(10px)";
        setTimeout(() => alertDiv.remove(), 400);
    }, 4000);
}
// Inject fadeInUp keyframes
const styleSheet = document.createElement("style");
styleSheet.innerText = `
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}
.bg-success { background-color: var(--color-success) !important; }
.bg-warning { background-color: var(--color-warning) !important; }
.bg-danger { background-color: var(--color-danger) !important; }
`;
document.head.appendChild(styleSheet);
function copyToClipboard(button, text) {
    navigator.clipboard.writeText(text).then(() => {
        const originalText = button.innerText;
        button.innerText = "Copied!";
        button.style.background = "var(--color-success)";
        button.style.color = "#fff";
        
        setTimeout(() => {
            button.innerText = originalText;
            button.style.background = "";
            button.style.color = "";
        }, 1500);
    }).catch(err => {
        showNotification("Failed to copy message", "danger");
    });
}

// =====================================================================
// --- AUTH FUNCTIONS ---
// =====================================================================

/**
 * Triggers the Google Sign-In popup.
 * Uses Google Identity Services (GSI) One Tap or prompt flow.
 * Falls back to a loading indicator when GSI is not yet loaded.
 */
function triggerGoogleSignIn() {
    const btn = document.getElementById("btn-google-signin");
    btn.classList.add("loading");
    btn.querySelector("span").innerText = "Connecting to Google...";

    if (typeof google !== "undefined" && google.accounts && google.accounts.id) {
        // Use GSI prompt (One Tap popup)
        google.accounts.id.prompt((notification) => {
            btn.classList.remove("loading");
            btn.querySelector("span").innerText = "Continue with Google";

            if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
                // GSI prompt was blocked or skipped — show instructions
                showNotification(
                    "Google Sign-In requires a configured OAuth Client ID. Using demo bypass.",
                    "warning"
                );
                // Demo bypass: auto-login using the default operations account
                handleGoogleLogin(null);
            }
        });
    } else {
        // GSI library not yet loaded — demo bypass
        setTimeout(() => {
            btn.classList.remove("loading");
            btn.querySelector("span").innerText = "Continue with Google";
            showNotification("Google SSO: Demo mode — signing in as portal admin.", "warning");
            handleGoogleLogin(null);
        }, 1200);
    }
}

/**
 * Called after Google returns a credential token (or null for demo bypass).
 * Posts the credential to the backend /api/auth/login for verification.
 */
async function handleGoogleLogin(credential) {
    const btn = document.getElementById("btn-google-signin");
    btn.classList.add("loading");
    btn.querySelector("span").innerText = "Verifying...";

    try {
        const res = await fetch(`${API_BASE}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ google_credential: credential || "demo_google_auth" })
        });
        const result = await res.json();

        btn.classList.remove("loading");
        btn.querySelector("span").innerText = "Continue with Google";

        if (result.success) {
            const user = result.user;
            // Store session info
            sessionStorage.setItem("crm_user", JSON.stringify(user));

            // Update sidebar user display
            const nameEl = document.getElementById("current-user-name");
            const avatarEl = document.getElementById("current-user-avatar");
            if (nameEl) nameEl.innerText = user.full_name || "Google User";
            if (avatarEl) {
                const initials = (user.full_name || "G U")
                    .split(" ").map(n => n[0]).join("").substring(0, 2).toUpperCase();
                avatarEl.innerText = initials;
            }

            // Switch from auth screen to dashboard
            document.getElementById("auth-container").style.display = "none";
            document.getElementById("app-runtime-container").style.display = "flex";
            setupFormListeners();
            loadAllData();
            if (typeof lucide !== "undefined") lucide.createIcons();
            showNotification(`Welcome, ${user.full_name || "Google User"}! Signed in via Google.`);
        } else {
            showNotification(result.error || "Google sign-in failed. Try again.", "danger");
        }
    } catch (err) {
        btn.classList.remove("loading");
        btn.querySelector("span").innerText = "Continue with Google";
        showNotification(`Google sign-in error: ${err.message}`, "danger");
    }
}

/**
 * Toggles between Sign In and Create Account tabs.
 * Shows/hides the Full Name field and updates submit button label.
 */
function toggleAuthTab(mode) {
    const titleEl = document.getElementById("auth-title");
    const descEl = document.getElementById("auth-desc");
    const fullNameGroup = document.getElementById("group-full-name");
    const actionsSignIn = document.getElementById("auth-actions-signin");
    const submitBtn = document.getElementById("btn-auth-submit");
    const tabSignIn = document.getElementById("btn-tab-signin");
    const tabRegister = document.getElementById("btn-tab-register");

    if (mode === "signin") {
        tabSignIn.classList.add("active");
        tabRegister.classList.remove("active");
        titleEl.innerText = "Welcome Back";
        descEl.innerText = "Sign in with your registered staff account to open the Dispatch Operations Terminal.";
        fullNameGroup.style.display = "none";
        actionsSignIn.style.display = "flex";
        submitBtn.innerText = "Access Dashboard";
        submitBtn.onclick = null; // use form submit
        document.getElementById("form-auth-native").dataset.mode = "signin";
    } else {
        tabSignIn.classList.remove("active");
        tabRegister.classList.add("active");
        titleEl.innerText = "Create Staff Account";
        descEl.innerText = "Register a new Manikanta CRM staff account. Admin approval may be required.";
        fullNameGroup.style.display = "block";
        actionsSignIn.style.display = "none";
        submitBtn.innerText = "Create Account";
        document.getElementById("form-auth-native").dataset.mode = "register";
    }
}

/**
 * Native Login / Register form submit handler.
 * Wired to the form-auth-native submit event.
 * Safely attached inside DOMContentLoaded to prevent null-crash on page load.
 */
function initAuthFormListener() {
    const authForm = document.getElementById("form-auth-native");
    if (!authForm) return; // guard: element must exist before attaching

    authForm.addEventListener("submit", async function(e) {
        e.preventDefault();
        const mode = this.dataset.mode || "signin";
        const submitBtn = document.getElementById("btn-auth-submit");
        const originalText = submitBtn.innerText;
        submitBtn.innerText = "Please wait...";
        submitBtn.disabled = true;

        try {
            if (mode === "register") {
                const fullName = document.getElementById("auth-fullname").value.trim();
                const username = document.getElementById("auth-username").value.trim();
                const password = document.getElementById("auth-password").value;

                if (!fullName || !username || !password) {
                    showNotification("Full Name, Username and Password are all required.", "warning");
                    return;
                }

                const res = await fetch(`${API_BASE}/api/auth/register`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ full_name: fullName, username, password })
                });
                const result = await res.json();
                if (!result.success) throw new Error(result.error);
                showNotification("Account created! You can now sign in.", "success");
                toggleAuthTab("signin");
                this.reset();

            } else {
                // Sign In
                const username = document.getElementById("auth-username").value.trim();
                const password = document.getElementById("auth-password").value;

                if (!username || !password) {
                    showNotification("Username and Password are required.", "warning");
                    return;
                }

                const res = await fetch(`${API_BASE}/api/auth/login`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password })
                });
                const result = await res.json();
                if (!result.success) throw new Error(result.error);

                const user = result.user;
                sessionStorage.setItem("crm_user", JSON.stringify(user));

                // Update sidebar user display
                const nameEl = document.getElementById("current-user-name");
                const avatarEl = document.getElementById("current-user-avatar");
                if (nameEl) nameEl.innerText = user.full_name || username;
                if (avatarEl) {
                    const initials = (user.full_name || username)
                        .split(" ").map(n => n[0]).join("").substring(0, 2).toUpperCase();
                    avatarEl.innerText = initials;
                }

                document.getElementById("auth-container").style.display = "none";
                document.getElementById("app-runtime-container").style.display = "flex";
                setupFormListeners();
                loadAllData();
                if (typeof lucide !== "undefined") lucide.createIcons();
                showNotification(`Welcome back, ${user.full_name || username}!`);
            }
        } catch (err) {
            showNotification(err.message || "Authentication failed. Please try again.", "danger");
        } finally {
            submitBtn.innerText = originalText;
            submitBtn.disabled = false;
        }
    });
}

/**
 * Signs out the current user and returns to the login screen.
 */
function handleSignOut() {
    sessionStorage.removeItem("crm_user");
    document.getElementById("app-runtime-container").style.display = "none";
    document.getElementById("auth-container").style.display = "grid";
    // Reset auth form
    document.getElementById("form-auth-native").reset();
    toggleAuthTab("signin");
    // Sign out from Google GSI too
    if (typeof google !== "undefined" && google.accounts && google.accounts.id) {
        google.accounts.id.disableAutoSelect();
    }
    showNotification("You have been signed out securely.", "success");
}
