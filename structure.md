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