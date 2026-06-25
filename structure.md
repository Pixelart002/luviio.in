

# 🚀 Luviio Backend — Enterprise Architecture

Welcome to the core backend of Luviio. This architecture is designed with **FAANG-level System Design** principles, strictly prioritizing **Role-Based Access Control (RBAC)**, **Separation of Concerns (SoC)**, and **Zero IDOR (Insecure Direct Object Reference) vulnerabilities**.

## 🏗️ Core Architectural Philosophy

1. **Strict URL Boundaries:** Routes are physically isolated by role (`admin`, `merchant`, `customer`, `staff`, `public`). A customer route will never share code with an admin route.
2. **Scoped Repositories:** Data access is strictly scoped at the database query level. For example, customer repositories automatically append `.eq("user_id", current_user)` to prevent data leakage.
3. **Registry Pattern (DI Container):** Repositories and external integrations are instantiated via a Dependency Registry, allowing for seamless mocking and preview environments.
4. **Event-Driven (Pub/Sub):** Heavy, non-database tasks (e.g., sending emails, webhooks) are decoupled using an Event Registry to ensure blazing-fast API response times.

---

## 📂 Vectorized Folder Structure

```text
app/
├── api/v1/                     # 🚀 ROLE-BASED ROUTING (Strict URL Boundaries)
│   ├── admin/                  # God Mode
│   │   └── routes/
│   │       ├── dashboard.py
│   │       ├── catalog.py      
│   │       └── users.py
│   ├── merchant/               # B2B Wholesale
│   │   └── routes/
│   │       ├── catalog.py      
│   │       └── bulk_cart.py
│   ├── staff/                  # Internal Employees
│   │   └── routes/
│   │       └── orders.py       
│   ├── customer/               # B2C Retail (Normal Users)
│   │   └── routes/
│   │       ├── profile.py
│   │       ├── cart.py
│   │       └── orders.py       
│   └── public/                 # Unauthenticated
│       └── routes/
│           ├── auth.py         
│           ├── catalog.py      
│           └── webhooks.py     
│
├── repositories/               # 💾 DATA LAYER (SoC + Registry Pattern)
│   ├── registry.py             # 🔌 Repo Registry (DI Container)
│   ├── interfaces/             
│   ├── admin/                  # No filters (Raw Access)
│   │   ├── product_repo.py
│   │   └── user_repo.py
│   ├── merchant/               # B2B specific logic & tier pricing
│   │   └── catalog_repo.py
│   ├── customer/               # STRICTLY scoped: .eq("user_id", current_user)
│   │   ├── order_repo.py
│   │   └── cart_repo.py
│   └── public/                 # STRICTLY scoped: .eq("is_active", True)
│       └── catalog_repo.py
│
├── dependencies/               # 🛡️ GUARDS & INJECTION
│   ├── auth.py                 # JWT Parsing & Session Validation
│   ├── roles.py                # RBAC Checkers (require_admin, require_merchant)
│   └── get_db.py               
│
├── services/                   # 🧠 BUSINESS LOGIC (No DB queries here)
│   ├── pricing_engine.py       # GST, Discounts, Wholesale logic
│   ├── image_processor.py      
│   └── email_service.py        
│
├── integrations/               # 🔗 EXTERNAL 3RD PARTY APIs
│   ├── payments/
│   │   ├── stripe_client.py
│   │   └── registry.py         # Support for multiple gateways
│   └── logistics/
│       └── shiprocket.py
│
├── events/                     # 📢 PUB/SUB EVENT ARCHITECTURE
│   ├── registry.py             # Event Bus Singleton
│   ├── schemas.py              # Event Definitions (e.g., OrderPaidEvent)
│   └── handlers/
│       ├── email_handlers.py
│       └── stock_handlers.py
│
├── cron/                       # ⏰ BACKGROUND SCHEDULER
│   ├── registry.py             # APScheduler initialization
│   └── tasks/
│       ├── order_tasks.py      # e.g., 24hr pending order expiration
│       └── reminder_tasks.py
│
├── core/                       # ⚙️ SYSTEM BOOTSTRAP
│   ├── config.py               # Environment Variables loading
│   ├── security.py             # Password Hashing & JWT Utils
│   └── supabase_client.py      # Database Connection Pooling
│
├── utils/                      # 🛠️ PURE HELPER FUNCTIONS
│   ├── formatters.py           
│   └── validators.py           
│
├── migrations/                 # 🗄️ DATABASE MIGRATIONS
│   └── versions/               
│
└── main.py                     # Application Entrypoint


# 🏗️ Project Architecture & Folder Structure

This project follows a highly scalable, **Domain-Driven Design (DDD)** and **Clean Architecture** tailored for an Enterprise E-commerce Backend (FastAPI + Supabase). It strictly enforces Separation of Concerns (SoC) and implements over 60+ industry-standard design patterns.

## 📂 Directory Tree

```text
luviio.in/
 ├── app/
 │    ├── api/                     # 🌐 API Presentation Layer (No Business Logic)
 │    │    ├── v1/                 # API Versioning Pattern
 │    │    │    └── routers/       # Controllers (auth.py, orders.py, cart.py, invoice.py)
 │    │    ├── schemas/            # DTO Pattern (Data Transfer Objects / Pydantic Models)
 │    │    └── middlewares/        # Chain of Responsibility (cors.py, security.py, logger.py)
 │    │
 │    ├── core/                    # ⚙️ Application Core & 12-Factor Configurations
 │    │    ├── config.py           # Environment variables (Single Source of Truth)
 │    │    ├── dependencies.py     # Dependency Injection (get_current_user, require_admin)
 │    │    └── exceptions.py       # Global Exception Handlers (Fail-Fast Principle)
 │    │
 │    ├── integrations/            # 🔌 External Services Layer (Registry & Adapter Patterns)
 │    │    ├── email/              # Email Service (base.py, resend_impl.py, registry.py)
 │    │    ├── payments/           # Payment Gateways (base.py, stripe_impl.py, registry.py)
 │    │    └── push/               # Push Notifications (registry.py, webpush_impl.py)
 │    │
 │    ├── repositories/            # 📦 Data Access Layer (Repository Pattern)
 │    │    ├── base.py             # Supabase Client Injection Base Class
 │    │    ├── admin_repo.py       # Admin queries & Analytics
 │    │    ├── cart_repo.py        # Cart & Cart Items logic
 │    │    ├── order_repo.py       # Orders & Transaction handling (Optimistic Locking)
 │    │    └── user_repo.py        # User profiles & authentication states
 │    │
 │    ├── services/                # 🧠 Business Logic Layer (Orchestration & Pub/Sub)
 │    │    ├── events.py           # Event-Driven Architecture (Event Bus, Observers)
 │    │    └── pricing.py          # Pricing Engine (Single Source of Truth for calculations)
 │    │
 │    ├── utils/                   # 🛠️ Pure Functions & Facades (Zero DB Dependencies)
 │    │    ├── documents/          
 │    │    │    ├── fonts/         # Custom TTF Fonts
 │    │    │    └── pdf_invoice.py # Facade Pattern (ReportLab PDF Generation)
 │    │    ├── image.py            # Image processing/compression
 │    │    ├── queue.py            # Async background tasks/workers
 │    │    └── stock.py            # Inventory math
 │    │
 │    └── main.py                  # 🚀 Application Entrypoint (FastAPI Bootstrap)
 │
 ├── .env.example                  # Environment template
 ├── app.sql                       # Database Schema & RLS Policies
 ├── Procfile                      # Deployment configuration (Render/Heroku)
 ├── requirements.txt              # Python Dependencies
 └── Readme.md                     # Documentation