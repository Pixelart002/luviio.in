Ye final hai  luviio/
│
├── app.py
├── .env.example
├── requirements.txt
├── Procfile
├── README.md
│
├── app/
│
│   ├── api/
│   │   ├── middlewares/
│   │   │   ├── cors.py
│   │   │   ├── logger.py
│   │   │   └── security.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── admin_dto.py
│   │   │   ├── auth_dto.py
│   │   │   ├── cart_dto.py
│   │   │   ├── order_dto.py
│   │   │   ├── payment_dto.py
│   │   │   ├── product_dto.py
│   │   │   ├── push_dto.py
│   │   │   └── user_dto.py
│   │   │
│   │   └── v1/
│   │       ├── routers/
│   │       │   ├── admin_verify.py
│   │       │   ├── auth.py
│   │       │   ├── cart.py
│   │       │   ├── inventory.py
│   │       │   ├── orders.py
│   │       │   ├── payments.py
│   │       │   ├── products.py
│   │       │   ├── push.py
│   │       │   └── users.py
│   │       │
│   │       ├── app.py
│   │       └── health.py
│
│   ├── core/
│   │   ├── config.py
│   │   ├── dependencies.py
│   │   ├── exceptions.py
│   │   ├── logger.py
│   │   ├── monitoring.py
│   │   ├── queue.py
│   │   ├── rate_limit.py
│   │   ├── security.py
│   │   ├── setup_middlewares.py
│   │   └── supabase.py
│
│   ├── constants/
│   │   ├── roles.py
│   │   ├── permissions.py
│   │   ├── status.py
│   │   ├── messages.py
│   │   ├── regex.py
│   │   ├── cache_keys.py
│   │   ├── headers.py
│   │   └── event_names.py
│
│   ├── enums/
│   │   ├── roles.py
│   │   ├── order_status.py
│   │   ├── payment_status.py
│   │   ├── notification.py
│   │   └── stock_status.py
│
│   ├── permissions/
│   │   ├── base.py
│   │   ├── admin.py
│   │   ├── products.py
│   │   ├── orders.py
│   │   ├── users.py
│   │   └── payments.py
│
│   ├── policies/
│   │   ├── admin_policy.py
│   │   ├── product_policy.py
│   │   ├── order_policy.py
│   │   ├── payment_policy.py
│   │   ├── user_policy.py
│   │   └── support_policy.py
│
│   ├── integrations/
│   │   ├── email/
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   └── resend_impl.py
│   │   │
│   │   ├── payments/
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   └── stripe_impl.py
│   │   │
│   │   ├── push/
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   └── webpush_impl.py
│   │   │
│   │   └── storage/
│   │       ├── base.py
│   │       ├── registry.py
│   │       └── supabase_impl.py
│
│   ├── repositories/
│   │   ├── base_repo.py
│   │   ├── admin_repo.py
│   │   ├── auth_repo.py
│   │   ├── cart_repo.py
│   │   ├── order_repo.py
│   │   ├── payment_repo.py
│   │   ├── product_repo.py
│   │   ├── push_repo.py
│   │   └── user_repo.py
│
│   ├── services/
│   │   ├── auth/
│   │   │   └── service.py
│   │   │
│   │   ├── users/
│   │   │   └── service.py
│   │   │
│   │   ├── admin/
│   │   │   └── service.py
│   │   │
│   │   ├── products/
│   │   │   ├── service.py
│   │   │   ├── pricing.py
│   │   │   ├── stock.py
│   │   │   ├── image.py
│   │   │   └── search.py
│   │   │
│   │   ├── cart/
│   │   │   └── service.py
│   │   │
│   │   ├── orders/
│   │   │   ├── service.py
│   │   │   ├── invoice.py
│   │   │   ├── fulfillment.py
│   │   │   └── tracking.py
│   │   │
│   │   ├── payments/
│   │   │   ├── service.py
│   │   │   ├── refunds.py
│   │   │   └── webhooks.py
│   │   │
│   │   ├── notifications/
│   │   │   ├── email.py
│   │   │   └── push.py
│   │   │
│   │   └── events/
│   │       └── publisher.py
│
│   ├── events/
│   │   ├── dispatcher.py
│   │   └── handlers/
│   │       ├── order.py
│   │       ├── payment.py
│   │       ├── push.py
│   │       ├── registration.py
│   │       └── user.py
│
│   ├── cron/
│   │   ├── scheduler.py
│   │   ├── registry.py
│   │   └── tasks/
│   │       ├── order_tasks.py
│   │       ├── cleanup.py
│   │       ├── notifications.py
│   │       └── reports.py
│
│   ├── utils/
│   │   ├── pagination.py
│   │   ├── response.py
│   │   ├── formatter.py
│   │   ├── validators.py
│   │   ├── slug.py
│   │   ├── crypto.py
│   │   └── documents/
│   │       ├── fonts/
│   │       └── pdf_invoice.py
│
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── api/
│
│   ├── docs/
│   │   ├── architecture.md
│   │   ├── api.md
│   │   ├── deployment.md
│   │   ├── security.md
│   │   └── database.md
│
│   └── migrations/
│
└── .gitignore 