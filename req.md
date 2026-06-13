# Odoo Cafe POS — Product Requirements & Technical Specification
Version 1.0 | June 2026

---

## 1. Introduction & Project Overview

### 1.1 Purpose

Odoo Cafe POS is a complete web-based restaurant point-of-sale system. It consists of three interconnected modules: a Backend Administration panel, a POS Terminal used by employees, and a real-time Kitchen Display System (KDS). The system handles the full lifecycle of a cafe order — from table selection and product ordering through kitchen preparation and payment to reporting and analytics.

### 1.2 Scope

- Authentication and role-based access control
- Backend configuration: products, categories, tables, payment methods, coupons & promotions, employees
- POS terminal: order management, discount application, payment processing, receipt delivery
- Kitchen Display System: real-time order tracking with stage progression
- Reporting and analytics dashboard with export capability

### 1.3 User Roles

| Role | Access Area | Responsibilities |
|---|---|---|
| User / Admin | Backend + POS | Configures products, tables, employees, payment methods, promotions. Reviews reports. Opens and closes POS sessions. |
| Employee / Cashier | POS Terminal | Takes orders, assigns customers, applies discounts, sends to kitchen, processes payments. |
| Customer | Managed via POS | Visited cafe guest linked to an order. Managed by the employee within the POS terminal. |

### 1.4 High-Level Application Flow

1. User signs up or logs in via the authentication screen.
2. On successful login, the POS session screen opens showing last session info.
3. Employee clicks "Open Session" to launch the POS terminal.
4. Floor pop-up appears; employee selects a table.
5. Order View opens. Employee browses products, adds to cart, adjusts quantities.
6. Automated promotions trigger based on qty or cart total. Manual coupons entered via popup.
7. Employee clicks "Send to Kitchen"; order appears on the KDS.
8. Kitchen staff progresses the order: To Cook → Preparing → Completed.
9. Employee processes payment (Cash / Card / UPI QR). Receipt is printed or emailed.
10. At shift end, employee closes the session and admin reviews daily reports.

---

## 2. System Architecture

### 2.1 Architecture Overview

The application follows a client–server architecture with three front-end modules communicating with a shared REST API backend backed by a relational database. All three front-end modules (Backend Admin, POS Terminal, KDS) connect to the same REST API. Real-time updates for the KDS are delivered via WebSockets or Server-Sent Events (SSE).

### 2.2 Technology Stack (Recommended)

| Layer | Options |
|---|---|
| Frontend | React.js / Vue.js (SPA) or any modern JS framework |
| Backend API | Node.js (Express) / Python (Django/FastAPI) / PHP (Laravel) |
| Database | PostgreSQL or MySQL (relational; enforces FK constraints) |
| Real-time | WebSockets (Socket.io) or Server-Sent Events for KDS updates |
| Auth | JWT tokens with role claims; HTTP-only cookie or Authorization header |
| QR Generation | Server-side QR library from UPI ID string |
| PDF Export | PDFKit / jsPDF / WeasyPrint |
| Excel Export | SheetJS (xlsx) / openpyxl |

### 2.3 Deployment Topology

- Single-origin deployment preferred (same domain for API and frontend) to simplify CORS.
- KDS accessible at a fixed URL path, e.g. `/kds`, intended for a dedicated kitchen screen.
- Authentication tokens must be passed by the KDS screen; no anonymous access to order data.

---

## 3. Data Models

### 3.1 User / Employee

| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID / INT PK | NOT NULL, unique | Auto-generated primary key |
| name | VARCHAR(120) | NOT NULL | Display name |
| email | VARCHAR(255) | NOT NULL, unique | Used for login and receipts |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt hash; never returned by API |
| role | ENUM | NOT NULL | 'admin' or 'cashier' |
| is_archived | BOOLEAN | DEFAULT false | Soft-delete via archive action |
| created_at | TIMESTAMP | DEFAULT NOW() | |

### 3.2 Product Category

| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID / INT PK | NOT NULL | |
| name | VARCHAR(100) | NOT NULL, unique | |
| color | VARCHAR(7) | NOT NULL | Hex color code e.g. #FF6B6B |

### 3.3 Product

| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID / INT PK | NOT NULL | |
| name | VARCHAR(200) | NOT NULL | |
| category_id | FK → Category | NOT NULL | Cascade on category delete: set null or restrict |
| price | DECIMAL(10,2) | NOT NULL, ≥ 0 | Base price before tax |
| unit_of_measure | VARCHAR(50) | NOT NULL | E.g. per piece, per kg, per litre |
| tax_percentage | DECIMAL(5,2) | DEFAULT 0 | Applied as percentage on top of price |
| description | TEXT | NULLABLE | |
| show_in_kds | BOOLEAN | DEFAULT true | Controls visibility on Kitchen Display |
| is_active | BOOLEAN | DEFAULT true | |

### 3.4 Floor

| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID / INT PK | NOT NULL | |
| name | VARCHAR(100) | NOT NULL | E.g. Ground Floor, Terrace |

### 3.5 Table

| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID / INT PK | NOT NULL | |
| floor_id | FK → Floor | NOT NULL | |
| table_number | VARCHAR(20) | NOT NULL | E.g. T1, T2, 101 |
| seats | INT | NOT NULL, ≥ 1 | Number of seats |
| is_active | BOOLEAN | DEFAULT true | Inactive tables hidden in POS |

### 3.6 Payment Method

| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID / INT PK | NOT NULL | |
| type | ENUM | NOT NULL | 'cash', 'card', 'upi' |
| is_enabled | BOOLEAN | DEFAULT false | Toggle in backend |
| upi_id | VARCHAR(100) | NULLABLE | Required when type = upi; e.g. cafe@ybl |

### 3.7 Coupon

| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID / INT PK | NOT NULL | |
| code | VARCHAR(50) | NOT NULL, unique | Case-insensitive comparison recommended |
| discount_type | ENUM | NOT NULL | 'percentage' or 'fixed' |
| discount_value | DECIMAL(10,2) | NOT NULL, > 0 | % or flat amount |
| is_active | BOOLEAN | DEFAULT true | |

### 3.8 Promotion

| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID / INT PK | NOT NULL | |
| name | VARCHAR(150) | NOT NULL | |
| apply_to | ENUM | NOT NULL | 'product' or 'order' |
| product_id | FK → Product | NULLABLE | Required when apply_to = product |
| min_quantity | INT | NULLABLE | Required when apply_to = product |
| min_order_amount | DECIMAL(10,2) | NULLABLE | Required when apply_to = order |
| discount_type | ENUM | NOT NULL | 'percentage' or 'fixed' |
| discount_value | DECIMAL(10,2) | NOT NULL | |
| is_active | BOOLEAN | DEFAULT true | |

### 3.9 Customer

| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID / INT PK | NOT NULL | |
| name | VARCHAR(150) | NOT NULL | |
| email | VARCHAR(255) | NULLABLE, unique | Used for receipt delivery |
| phone | VARCHAR(20) | NULLABLE | |

### 3.10 POS Session

| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID / INT PK | NOT NULL | |
| opened_by | FK → User | NOT NULL | |
| opened_at | TIMESTAMP | NOT NULL | |
| closed_at | TIMESTAMP | NULLABLE | NULL = session still open |
| closing_sale_amount | DECIMAL(12,2) | NULLABLE | Total revenue at close |
| status | ENUM | NOT NULL | 'open' or 'closed' |

### 3.11 Order

| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID / INT PK | NOT NULL | |
| order_number | VARCHAR(30) | NOT NULL, unique | Human-readable; auto-generated e.g. ORD-0042 |
| session_id | FK → Session | NOT NULL | |
| table_id | FK → Table | NULLABLE | |
| customer_id | FK → Customer | NULLABLE | |
| employee_id | FK → User | NOT NULL | Cashier who created the order |
| status | ENUM | NOT NULL | 'draft', 'sent_to_kitchen', 'paid', 'cancelled' |
| subtotal | DECIMAL(12,2) | NOT NULL | Sum of line totals before tax/discount |
| tax_amount | DECIMAL(12,2) | NOT NULL | |
| discount_amount | DECIMAL(12,2) | DEFAULT 0 | Total discount applied |
| total | DECIMAL(12,2) | NOT NULL | Final amount charged |
| coupon_id | FK → Coupon | NULLABLE | |
| promotion_id | FK → Promotion | NULLABLE | |
| created_at | TIMESTAMP | NOT NULL | |
| paid_at | TIMESTAMP | NULLABLE | |

### 3.12 Order Line Item

| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID / INT PK | NOT NULL | |
| order_id | FK → Order | NOT NULL | Cascade delete |
| product_id | FK → Product | NOT NULL | |
| quantity | INT | NOT NULL, ≥ 1 | |
| unit_price | DECIMAL(10,2) | NOT NULL | Snapshot of price at order time |
| line_discount | DECIMAL(10,2) | DEFAULT 0 | Product-level promotion discount |
| line_total | DECIMAL(12,2) | NOT NULL | (unit_price × qty) − line_discount |
| kds_status | ENUM | DEFAULT 'to_cook' | 'to_cook', 'preparing', 'completed' |

### 3.13 Payment Record

| Field | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID / INT PK | NOT NULL | |
| order_id | FK → Order | NOT NULL | One-to-one in typical flow |
| method_type | ENUM | NOT NULL | 'cash', 'card', 'upi' |
| amount_tendered | DECIMAL(12,2) | NOT NULL | Cash: amount given. Card/UPI: equals total |
| change_due | DECIMAL(12,2) | DEFAULT 0 | Cash only |
| transaction_ref | VARCHAR(100) | NULLABLE | Card transaction reference |
| paid_at | TIMESTAMP | NOT NULL | |

---

## 4. Backend Administration — Detailed Requirements

### 4.1 Authentication

#### 4.1.1 Signup
Route: `POST /api/auth/signup`

- Fields: Name (required), Email (required, valid format, unique), Password (required, min 8 chars).
- Password is hashed with bcrypt (min cost factor 10) before storage.
- On success: return JWT token + user object. Redirect to POS session screen.
- On failure: return 400 with field-level validation errors.

#### 4.1.2 Login
Route: `POST /api/auth/login`

- Fields: Email, Password.
- Verify email exists and password matches hash.
- On success: return JWT token containing `{ userId, role, name }`. Redirect to POS session screen.
- On failure: return 401 "Invalid credentials".
- Archived accounts must not be permitted to log in (return 403 "Account disabled").

#### 4.1.3 JWT Strategy
- Token expiry: 8 hours (covers a standard shift).
- Refresh token optional but recommended for long sessions.
- All protected routes validate the Bearer token in the Authorization header.
- Role enforcement: admin-only routes return 403 if role !== "admin".

---

### 4.2 Product Management

Full CRUD for products. Access restricted to admin role.

#### Business Rules
- Price must be ≥ 0. Tax percentage must be 0–100.
- Category field is a searchable dropdown. If the user types a name that does not exist, a "Create category" option appears inline — creating the category on the fly without leaving the product form.
- Deleting a product that appears in existing orders must be soft-deleted (set `is_active = false`) to preserve historical data.
- Products with `is_active = false` do not appear in the POS product grid.

#### API Endpoints

| Method | Endpoint | Auth | Body / Params | Response / Notes |
|---|---|---|---|---|
| GET | /api/products | Admin/Cashier | ?category_id, ?search, ?page | Paginated list of active products |
| POST | /api/products | Admin | { name, category_id, price, unit_of_measure, tax_percentage, description, show_in_kds } | 201 Created with product object |
| GET | /api/products/:id | Admin/Cashier | — | Single product |
| PUT | /api/products/:id | Admin | Same as POST body (partial ok) | 200 with updated product |
| DELETE | /api/products/:id | Admin | — | Soft-delete if in orders; hard-delete otherwise |

---

### 4.3 Product Category Management

#### Business Rules
- Color is stored as a hex code (e.g. `#FF6B6B`). UI renders a color picker.
- Color changes propagate immediately to all POS views (product cards, filter tabs) — fetch categories fresh on POS terminal launch.
- Deleting a category that has associated products: either block with a 400 error or reassign products to a default "Uncategorised" category.

#### API Endpoints

| Method | Endpoint | Auth | Body / Params | Response / Notes |
|---|---|---|---|---|
| GET | /api/categories | Admin/Cashier | — | Full list (unpaginated) |
| POST | /api/categories | Admin | { name, color } | 201 with category object |
| PUT | /api/categories/:id | Admin | { name, color } | 200 with updated category |
| DELETE | /api/categories/:id | Admin | — | 400 if products exist; 204 otherwise |

---

### 4.4 Payment Method Setup

#### Business Rules
- Three methods exist by default (seeded at DB init): Cash, Card, UPI. They cannot be added or removed — only toggled.
- When UPI is enabled and no `upi_id` is saved, a validation error must be returned.
- The generated QR code is a standard UPI deep link: `upi://pay?pa={upi_id}&am={amount}&cu=INR`.
- Disabling a method removes it from the payment options in the POS terminal instantly.

#### API Endpoints

| Method | Endpoint | Auth | Body / Params | Response / Notes |
|---|---|---|---|---|
| GET | /api/payment-methods | Admin/Cashier | — | Returns all 3 methods with is_enabled and upi_id |
| PATCH | /api/payment-methods/:id | Admin | { is_enabled, upi_id? } | 200 updated; 400 if UPI enabled without upi_id |

---

### 4.5 Floor Plan & Table Management

#### Business Rules
- A floor must be created before tables can be added under it.
- Table numbers are unique per floor (not globally).
- Deactivating a table hides it from the POS floor pop-up.
- Tables with an open Draft order cannot be deactivated; return 409.

#### API Endpoints

| Method | Endpoint | Auth | Body / Params | Response / Notes |
|---|---|---|---|---|
| GET | /api/floors | Admin/Cashier | ?include_tables=true | Floors with nested tables |
| POST | /api/floors | Admin | { name } | 201 with floor |
| PUT | /api/floors/:id | Admin | { name } | 200 |
| DELETE | /api/floors/:id | Admin | — | Only if no active tables |
| GET | /api/floors/:id/tables | Admin/Cashier | — | Tables for a floor |
| POST | /api/floors/:id/tables | Admin | { table_number, seats, is_active } | 201 |
| PUT | /api/tables/:id | Admin | { table_number, seats, is_active } | 200 |
| DELETE | /api/tables/:id | Admin | — | 409 if open order; 204 otherwise |

---

### 4.6 Coupons & Promotions

#### Coupon Rules
- Code is case-insensitive (store uppercased; compare uppercased).
- One coupon code can be applied per order.
- If `discount_type = "percentage"`, value is 0–100. If `"fixed"`, value is a flat amount.
- Fixed discounts must not exceed order subtotal (cap at subtotal).

#### Promotion Rules
- Promotions trigger automatically during cart calculation; no code entry needed.
- **Product promotion:** triggered when the qty of the specific product in the cart reaches `min_quantity`.
- **Order promotion:** triggered when cart subtotal (before any coupon) reaches `min_order_amount`.
- Only the highest-value promotion applies if multiple are eligible (or define stacking explicitly).
- Promotions and coupons can co-exist: promotion is calculated first, then coupon on the resulting total.

#### API Endpoints

| Method | Endpoint | Auth | Body / Params | Response / Notes |
|---|---|---|---|---|
| GET | /api/coupons | Admin | — | All coupons |
| POST | /api/coupons | Admin | { code, discount_type, discount_value } | 201 |
| PUT | /api/coupons/:id | Admin | Partial update | 200 |
| DELETE | /api/coupons/:id | Admin | — | 204 |
| POST | /api/coupons/validate | Cashier | { code, order_subtotal } | 200 { valid, discount_amount } or 400 |
| GET | /api/promotions | Admin/Cashier | — | All active promotions |
| POST | /api/promotions | Admin | { name, apply_to, product_id?, min_quantity?, min_order_amount?, discount_type, discount_value } | 201 |
| PUT | /api/promotions/:id | Admin | Partial update | 200 |
| DELETE | /api/promotions/:id | Admin | — | 204 |

---

### 4.7 User / Employee Management

#### Business Rules
- Only an admin can list, create, and manage user accounts.
- Archive sets `is_archived = true`. Archived users cannot log in.
- Hard-delete is prevented if the user has associated orders (return 409).
- Change Password: admin provides a new plaintext password; the API hashes it and updates.
- An admin cannot archive or delete their own account (return 403).

#### API Endpoints

| Method | Endpoint | Auth | Body / Params | Response / Notes |
|---|---|---|---|---|
| GET | /api/users | Admin | — | All non-deleted users |
| POST | /api/users | Admin | { name, email, password, role } | 201 — hashes password |
| PATCH | /api/users/:id/password | Admin | { new_password } | 200 |
| PATCH | /api/users/:id/archive | Admin | — | 200 toggles is_archived |
| DELETE | /api/users/:id | Admin | — | 409 if has orders; 204 otherwise |

---

### 4.8 POS Session Management

#### Business Rules
- Only one session can be open at a time (enforce at DB/API level).
- The POS session screen shows: last open date, last closing sale amount.
- Opening a session creates a new Session record with `status = "open"`.
- Closing a session sets `closed_at`, computes `closing_sale_amount` (sum of paid orders in session), sets `status = "closed"`, and returns a closing summary.
- Closing summary includes: total orders, total revenue, breakdown by payment method.

#### API Endpoints

| Method | Endpoint | Auth | Body / Params | Response / Notes |
|---|---|---|---|---|
| GET | /api/sessions/current | Admin/Cashier | — | Returns open session or { lastSession } if none open |
| POST | /api/sessions/open | Admin | — | 201 with new session; 409 if already open |
| POST | /api/sessions/close | Admin | — | 200 with closing summary |

---

### 4.9 Reports & Dashboard

#### Filters
- Period: Today, This Week, This Month, Custom Date Range (from/to).
- Employee: filter by specific employee UUID.
- Session: filter by session UUID.
- Product: filter by product UUID.

#### Dashboard Components

| Component | Calculation / Content |
|---|---|
| Total Orders | COUNT of paid orders in period |
| Revenue | SUM of total on paid orders |
| Average Order Value | Revenue ÷ Total Orders |
| Sales Trend Chart | Revenue or order count grouped by day/week (line or bar chart) |
| Top Categories Chart | Revenue grouped by category (pie or donut chart) |
| Top Orders Table | Orders sorted by total DESC, top 10 |
| Top Products Table | Product + qty sold + revenue |
| Top Categories Table | Category + revenue |

#### Export
- **PDF:** renders the current dashboard view (metrics + charts + tables) as a printable PDF.
- **XLS:** exports raw order data with columns: Order#, Date, Customer, Employee, Items, Subtotal, Tax, Discount, Total, Payment Method.

#### API Endpoints

| Method | Endpoint | Auth | Params | Response |
|---|---|---|---|---|
| GET | /api/reports/summary | Admin | ?from, ?to, ?employee_id, ?session_id, ?product_id | { total_orders, revenue, avg_order_value } |
| GET | /api/reports/sales-trend | Admin | ?from, ?to, ?group_by (day\|week) | Array of { date, revenue, order_count } |
| GET | /api/reports/top-products | Admin | ?from, ?to, ?limit | Array of { product, qty_sold, revenue } |
| GET | /api/reports/top-categories | Admin | ?from, ?to | Array of { category, revenue } |
| GET | /api/reports/top-orders | Admin | ?from, ?to, ?limit | Array of order objects sorted by total |
| GET | /api/reports/export/pdf | Admin | Same filters | PDF binary with Content-Disposition attachment |
| GET | /api/reports/export/xls | Admin | Same filters | XLSX binary |

---

## 5. POS Terminal — Detailed Requirements

### 5.1 Navigation Bar

Persistent top bar visible across all POS views. Contains:

- **POS Order** — navigates to the main order-taking screen.
- **Orders** — navigates to the session order list.
- **Customer** — opens customer management view.
- **Table View** — opens the floor/table selector.
- **Product Search Bar** — full-width search filtering products by name in real time.
- **Current Table Indicator** — displays the active table number (e.g. "Table T3"). Clicking it opens the floor pop-up.
- **Employee Icon** — displays logged-in employee name/avatar.
- **Hamburger Menu** — dropdown with links to all backend sections (Products, Category, Payment Method, Coupon & Promotion, User/Employee, KDS, Reports) and Log-Out.

---

### 5.2 Floor Pop-up

Displayed when the session starts or when the employee taps "Table View".

#### Layout
- Tabs at the top for each floor. Selecting a tab shows only that floor's tables.
- Tables rendered as a numbered grid of cards.
- Each card shows: table number and seat count.
- Available tables: neutral background. Tables with a Draft order: visually highlighted (e.g. amber border or tinted background).

#### Interaction
- Clicking an available table creates a new Draft order for that table and opens the Order View.
- Clicking an occupied table opens the existing Draft order in the Order View.
- The pop-up can be dismissed (X button) to return to the previous view.

---

### 5.3 Order View

The primary working screen, divided into three panels.

#### 5.3.1 Product Panel (Left)
- Category filter tabs across the top — each tab uses the category's color as its background/accent.
- An "All" tab shows all active products.
- Products rendered as cards with: name, price, and category color accent.
- Clicking a product adds one unit to the cart. Rapid successive clicks increment qty without adding duplicate lines.
- Search bar filters products in real time by name.

#### 5.3.2 Cart Panel (Middle)
- Each line: product name, quantity controls (−/+), unit price, line total.
- Quantity controls update line total immediately.
- Setting qty to 0 removes the line.
- If a product-level promotion is active, the discount amount is shown inline below the product line (e.g. "Promo: −₹20").

#### 5.3.3 Order Summary (Bottom of Cart Panel)

| Line | Calculation |
|---|---|
| Subtotal | Sum of all line totals |
| Tax | Calculated per product using its tax_percentage |
| Discount | Total of all applied discounts (promotion + coupon) |
| Total | Subtotal + Tax − Discount |

#### 5.3.4 Action Buttons
- **Customer** — opens a customer search/assign popup.
- **Discount** — opens the coupon code entry popup.
- **Send** — opens the receipt email popup.
- **Send to Kitchen** — sends current order lines to the KDS. Disabled if cart is empty. Shows a confirmation toast after sending.

#### 5.3.5 Payment Panel (Right)
- Shows all enabled payment methods as selectable cards.
- Selecting a method opens the payment flow for that method.
- The panel shows the order total prominently.

---

### 5.4 Coupon / Discount Popup
- Text input for coupon code. "Apply" button triggers `POST /api/coupons/validate`.
- On success: discount shown in order summary; popup closes.
- On failure (invalid/expired code): inline error message. Popup stays open.
- One coupon per order. Re-entering a code replaces the existing one.
- Automated promotions are not affected by this popup — they recalculate on every cart update.

---

### 5.5 Payment Flows

#### 5.5.1 Cash
1. Employee enters the cash amount received.
2. System displays change due = amount tendered − order total.
3. Employee clicks "Confirm Payment".
4. Order status → "paid". Payment record created.

#### 5.5.2 UPI QR
1. System generates a QR code from the UPI deep link string with the order total.
2. QR code displayed full-screen or in a large modal with the total amount shown.
3. Employee clicks "Confirmed" after verifying payment on the UPI app.
4. Alternatively, employee clicks "Cancel" to return to the payment panel without marking paid.

#### 5.5.3 Card / Digital
1. Employee enters the bank/card transaction reference number (alphanumeric).
2. Employee clicks "Confirm Payment".
3. Order status → "paid". Transaction ref stored in payment record.

#### 5.5.4 Post-Payment Options
- **Print Receipt** — triggers browser print dialog with a formatted receipt.
- **Email Receipt** — opens a popup pre-filled with the assigned customer's email. Sends receipt via API.
- **New Order** — resets the cart and returns to the floor pop-up.

Receipt content: Order#, date/time, table, employee, customer (if assigned), itemised list (name, qty, price, line total), subtotal, tax, discount, total, payment method, change due (cash only).

---

### 5.6 Orders List View
- Shows all orders created in the current active session.
- Search bar filters by customer name, order number, or date.
- Status filter tabs: All | Draft | Paid | Cancelled.

Columns per order:

| Column | Content |
|---|---|
| Order Number | e.g. ORD-0042, sorted newest first |
| Date | Created at, localised date & time |
| Customer | Customer name or "Walk-in" |
| Amount | Total, currency formatted |
| Status | Draft / Paid / Cancelled (color-coded badge) |

#### Order Detail
- Clicking a row opens an order detail panel/modal.
- Shows all order metadata + itemised product list.
- **Draft orders:** "Edit Order" button loads the order back into the cart; "Delete" soft-deletes (status → cancelled).
- **Paid orders:** view-only with receipt print/email options.

---

### 5.7 Customer Management (POS)
- Search by name, email, or phone. Results appear as a list; clicking assigns the customer to the current order.
- "Create New Customer" form: Name (required), Email (optional), Phone (optional).
- Editing a customer from within the POS updates the global customer record.
- Deleting a customer linked to orders must be blocked (return 409).

#### API Endpoints

| Method | Endpoint | Auth | Body / Params | Response |
|---|---|---|---|---|
| GET | /api/customers | Cashier/Admin | ?search | Search by name/email/phone |
| POST | /api/customers | Cashier/Admin | { name, email?, phone? } | 201 |
| PUT | /api/customers/:id | Cashier/Admin | Partial update | 200 |
| DELETE | /api/customers/:id | Cashier/Admin | — | 409 if linked to orders; 204 otherwise |

---

### 5.8 Order API Endpoints

| Method | Endpoint | Auth | Body / Params | Response / Notes |
|---|---|---|---|---|
| GET | /api/orders | Cashier/Admin | ?session_id, ?status, ?search, ?page | Paginated order list |
| POST | /api/orders | Cashier | { session_id, table_id, employee_id } | 201 with Draft order |
| GET | /api/orders/:id | Cashier/Admin | — | Order detail with line items |
| PUT | /api/orders/:id | Cashier | { customer_id?, coupon_id? } | Update metadata |
| POST | /api/orders/:id/lines | Cashier | { product_id, quantity } | Add/update line; recalculates totals + promotions |
| PUT | /api/orders/:id/lines/:lid | Cashier | { quantity } | Update qty; qty=0 removes line |
| DELETE | /api/orders/:id/lines/:lid | Cashier | — | Remove line item |
| POST | /api/orders/:id/send-to-kitchen | Cashier | — | Sets kds_status = to_cook; broadcasts to KDS |
| POST | /api/orders/:id/pay | Cashier | { method_type, amount_tendered, transaction_ref? } | 200; creates payment record; marks order paid |
| POST | /api/orders/:id/cancel | Cashier | — | Sets status = cancelled; Draft orders only |
| POST | /api/orders/:id/receipt/email | Cashier | { email } | Sends formatted receipt email |

---

## 6. Kitchen Display System (KDS)

### 6.1 Overview

The KDS runs on a dedicated screen (separate browser tab or device) and shows live order tickets for kitchen staff. It receives new orders the moment an employee clicks "Send to Kitchen" from the POS terminal. KDS URL is fixed (e.g. `/kds`) and requires authentication — kitchen staff must be logged in with at minimum a Cashier role.

### 6.2 Real-Time Updates
- Implement via WebSocket (preferred) or SSE (Server-Sent Events).
- When an order is sent to kitchen, the server broadcasts an event to all KDS connections.
- KDS clients listen for `new_order`, `order_updated`, and `order_stage_changed` events.
- No page reload should be required to see new orders.

### 6.3 Ticket Card Layout

Each order is displayed as a ticket card:
- **Header:** Order Number (e.g. ORD-0042) + timestamp of when it was sent to kitchen.
- Table number.
- List of line items: only products where `show_in_kds = true`.
- Each line item shows: product name and quantity.
- Items marked individually completed appear with a strikethrough.
- A stage badge at the top-right: "TO COOK", "PREPARING", or "COMPLETED".

### 6.4 Stage Progression

#### Whole-Order Stage
- Clicking anywhere on the ticket card (outside individual items) advances the entire order's KDS stage.
- To Cook → Preparing → Completed.
- Completed tickets can be hidden after a configurable delay (default 60 seconds) or manually dismissed.

#### Individual Item Stage
- Clicking an individual product line marks that line's `kds_status = "completed"` with a strikethrough.
- This does not advance the overall order stage.
- Allows item-by-item progress tracking without marking the whole order done.

### 6.5 Search & Filters
- **Search bar:** filters visible tickets by product name or order number.
- **Product filter:** dropdown to show only tickets containing a specific product.
- **Category filter:** dropdown to show only tickets containing products from a specific category.
- **Stage filter tabs:** All | To Cook | Preparing | Completed.

### 6.6 KDS API Endpoints

| Method | Endpoint | Auth | Body / Params | Response / Notes |
|---|---|---|---|---|
| GET | /api/kds/orders | Cashier/Admin | ?status, ?product_id, ?category_id | Orders currently in kitchen |
| PATCH | /api/kds/orders/:id/stage | Cashier/Admin | { stage: "preparing"\|"completed" } | Advance whole order KDS stage; broadcasts WS event |
| PATCH | /api/kds/orders/:id/lines/:lid/complete | Cashier/Admin | — | Mark single line item completed |

---

## 7. UI/UX Specifications

### 7.1 Design Principles
- **Touch-friendly:** all interactive elements minimum 44×44px tap target.
- **High contrast** for POS environments (bright ambient light in cafes).
- **Minimal navigation depth** — core actions reachable in 2 taps.
- **Real-time feedback:** cart totals update instantly on every change.
- **Error states** must be visible inline, not just in browser console.

### 7.2 Screen Inventory

| Screen | Module | Description |
|---|---|---|
| Login / Signup | Auth | Centered form with tabs for Login/Signup |
| POS Session | Backend | Last session info + Open Session CTA |
| Dashboard / Reports | Backend | Charts, metrics, filter bar, export buttons |
| Product List | Backend | Data table with search, add/edit/delete |
| Product Form | Backend | Create/edit product; inline category creation |
| Category List | Backend | List with color swatches |
| Payment Methods | Backend | Toggle cards per method; UPI ID input |
| Floor Plan | Backend | Floor tabs + table grid with add/edit |
| Coupons | Backend | List of coupon codes with CRUD |
| Promotions | Backend | List of promotions with CRUD |
| User Management | Backend | Employee list with role, archive, password actions |
| Floor Pop-up | POS | Modal overlay with floor tabs and table grid |
| Order View | POS | 3-panel: Products | Cart | Payment |
| Coupon Popup | POS | Small modal for code entry |
| Payment — Cash | POS | Amount tendered input + change display |
| Payment — UPI | POS | Large QR code + total + Confirm/Cancel |
| Payment — Card | POS | Transaction reference input |
| Receipt Screen | POS | Post-payment with Print/Email/New Order options |
| Orders List | POS | Session order history with search/filter |
| Order Detail | POS | Full order view with Edit/Delete/Receipt actions |
| Customer List/Form | POS | Search + create/edit customer |
| KDS Board | KDS | Full-screen ticket cards with stage controls |

### 7.3 Responsive Behavior
- **Backend admin:** designed for desktop (≥1280px). Sidebar nav collapses on tablets.
- **POS Terminal:** designed for tablet landscape (≥1024px). 3-panel layout adjusts to 2-panel on smaller screens (product panel becomes a slide-in drawer).
- **KDS:** optimised for a 55"–65" mounted kitchen display. Font sizes and card dimensions scale up accordingly.

---

## 8. Non-Functional Requirements

### 8.1 Performance
- API response time: ≤ 200ms for list endpoints (with DB indexing on FK columns and common search fields).
- Product search in POS: debounced at 300ms; results returned ≤ 100ms from cache/DB.
- Dashboard report queries: ≤ 2 seconds for 30-day range on 10,000 orders.
- KDS WebSocket message delivery: ≤ 500ms from "Send to Kitchen" action.

### 8.2 Security
- All passwords stored as bcrypt hashes (cost factor ≥ 10). Never logged or returned by API.
- JWT tokens signed with HS256 or RS256. Secrets loaded from environment variables — never hardcoded.
- Role-based middleware applied at the route level, not just on the frontend.
- Input validation on all POST/PUT bodies: type checking, length limits, enum validation.
- SQL injection prevention: use parameterised queries or ORM (never raw string concatenation).
- CORS: restrict to known frontend origins.
- Rate limiting: apply to auth endpoints (e.g. 10 attempts per minute per IP) to prevent brute force.

### 8.3 Data Integrity
- Database-level foreign key constraints on all FK columns.
- Order totals (subtotal, tax, discount, total) must be recalculated server-side on every cart mutation — never trust client-provided totals.
- Soft-delete preferred over hard-delete for products, users, and coupons.
- Transaction wrapping for payment: the order status update and payment record creation must be atomic.

### 8.4 Availability & Reliability
- POS terminal must degrade gracefully on slow connections — show loading states, not blank screens.
- KDS must reconnect automatically if WebSocket connection drops (exponential backoff, max 30s).
- Failed API calls in the POS must surface a user-readable error, not a raw HTTP error code.

---

## 9. Error Handling & Edge Cases

### 9.1 Standard HTTP Error Responses

All error responses follow this JSON schema:
```json
{ "error": true, "code": "COUPON_INVALID", "message": "Coupon code has expired.", "details": {} }
```

| HTTP Status | Meaning | Usage Examples |
|---|---|---|
| 400 Bad Request | Invalid input | Validation failures, UPI enabled without UPI ID |
| 401 Unauthorized | No/invalid token | Missing or expired JWT |
| 403 Forbidden | Insufficient role | Cashier accessing admin endpoint |
| 404 Not Found | Resource missing | Product/order UUID does not exist |
| 409 Conflict | State conflict | Session already open; table has active order; user has orders |
| 500 Internal | Server error | Unexpected DB or runtime error (log internally, don't expose) |

### 9.2 Edge Case Handling

| Edge Case | Required Handling |
|---|---|
| Coupon discount > order subtotal | Cap discount at subtotal; total = tax only. |
| Product price changes after order created | Snapshot price in `order_line_item.unit_price`; changes do not affect existing orders. |
| Closing session with open Draft orders | Warn user; allow proceeding (draft orders auto-cancelled) or block until resolved — define per implementation. |
| Two employees claim same table simultaneously | Use DB transaction + row lock. Second request receives 409 "Table already has an active order." |
| UPI QR shown but payment not confirmed | "Cancel" returns to payment panel; order remains Draft. |
| Employee logs out mid-order | JWT expiry returns 401. POS shows "Session expired" and redirects to login. Draft order persists in DB. |
| Product deleted while in active cart | Product is soft-deleted; POS cart retains the line (snapshots unit price). New orders cannot add the deleted product. |

---

## 10. Acceptance Criteria

### 10.1 Authentication
- A new user can sign up, receive a JWT, and be directed to the POS session screen.
- An archived user cannot log in; receives a 403 error.
- An expired JWT causes a redirect to the login screen on the next API call.

### 10.2 Backend Configuration
- Admin can create a product, assign a new category created inline, and see it appear on the POS terminal without a page reload.
- Changing a category color updates all POS product cards within the same session.
- Disabling Cash payment removes it from the POS payment panel.
- Enabling UPI without entering a UPI ID shows a validation error and does not save.
- Creating a table under a floor causes it to appear on the POS floor pop-up.

### 10.3 POS Terminal
- Employee opens a session, selects a table, adds 3 products, and sees correct subtotal, tax, and total.
- Applying a valid coupon code reduces the total by the correct amount.
- Adding a product that triggers an automated promotion shows the discount on the relevant cart line.
- Clicking "Send to Kitchen" creates a ticket on the KDS within 1 second.
- Cash payment with tendered amount > total shows correct change due.
- UPI payment generates a QR code; clicking Confirmed marks the order as paid.
- A paid order cannot be edited; it is view-only in the Orders list.

### 10.4 Kitchen Display
- A new ticket appears on the KDS the instant "Send to Kitchen" is clicked in the POS.
- Clicking a ticket card advances its stage: To Cook → Preparing → Completed.
- Clicking an individual item marks it completed with a strikethrough; the order stage remains unchanged.
- Filtering by category shows only tickets containing products from that category.

### 10.5 Reporting
- Dashboard shows correct order count, revenue, and average order value for "Today".
- Changing the period filter updates all charts and tables without a page reload.
- PDF export downloads a formatted report matching the current dashboard view.
- XLS export contains one row per order with all required columns.

---

## 11. Appendix

### 11.1 DB Seeding / Initial State
- Three payment method records created at DB init: `{ type: cash, is_enabled: true }`, `{ type: card, is_enabled: false }`, `{ type: upi, is_enabled: false }`.
- At least one admin user seeded for development: `admin@cafe.com` / `Admin@123`.
- Sample categories, products, and a floor plan recommended for demo purposes.

### 11.2 Glossary

| Term | Definition |
|---|---|
| POS | Point of Sale — the system and terminal used to process orders and payments. |
| KDS | Kitchen Display System — a screen in the kitchen that shows incoming orders. |
| Draft | An order that has been started but not yet paid or cancelled. |
| Session | A working period of POS operation, opened and closed by the admin. |
| Promotion | An automated discount that applies when quantity or order total thresholds are met. |
| Coupon | A manual discount code entered by the employee at the POS. |
| UPI | Unified Payments Interface — Indian digital payment standard using a VPA like name@bank. |
| JWT | JSON Web Token — a signed token used for stateless authentication. |
| Soft-delete | Setting is_active/is_archived to false rather than removing the DB record. |
| Snapshot pricing | Copying the current product price into the order line at order time, so price changes do not affect past orders. |

### 11.3 Out of Scope
- Inventory / stock level tracking.
- Multi-branch or multi-location support.
- Customer loyalty points or rewards programmes.
- Online ordering or delivery integrations.
- Native mobile applications (iOS/Android).
- Integration with external accounting systems.

### 11.4 Future Enhancements (Post-MVP)
- Inventory management with low-stock alerts.
- Modifier/add-on support for products (e.g. "extra shot of espresso").
- Split-bill functionality.
- Real-time customer-facing display showing their order total.
- Offline mode with local caching and sync when reconnected.