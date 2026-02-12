from fastapi.middleware.cors import CORSMiddleware

def setup_cors(app):
    origins = [
        "https://luviio.in",
        "https://www.luviio.in",
        "https://auth.luviio.in",
        "https://luviio-qgo2xbkon-pixelart002s-projects.vercel.app"
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "X-Up-Target", "X-Up-Fragment", "X-Up-Location"],
        # 📣 EXPOSE: Frontend (Unpoly) ko in headers ko padhne do
        expose_headers=["X-Up-Location", "X-Up-Method", "X-Up-Target", "X-Up-Fragment"]
    )