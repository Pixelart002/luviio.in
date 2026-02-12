from fastapi.middleware.cors import CORSMiddleware

def setup_cors(app):
    # 🌍 Production + Preview Domains
    origins = [
        "https://luviio.in",
        "https://www.luviio.in",
        "https://auth.luviio.in",
        "https://luviio-qgo2xbkon-pixelart002s-projects.vercel.app" # Preview URL
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        # 🛡️ UNPOLY HEADERS: Inko allow karna mandatory hai
        allow_headers=[
            "*", 
            "X-Up-Target", 
            "X-Up-Fragment", 
            "X-Up-Validate", 
            "X-Up-Context",
            "X-Up-Mode"
        ],
        # 📣 EXPOSE: Taaki frontend redirect ko detect kar sake
        expose_headers=["X-Up-Location", "X-Up-Method", "X-Up-Target"]
    )