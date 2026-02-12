from fastapi.middleware.cors import CORSMiddleware

def setup_cors(app):
    # 🌍 ALLOWED ORIGINS: Production + Preview URLs
    origins = [
        "https://luviio.in",
        "https://www.luviio.in",
        "https://auth.luviio.in",
        "https://luviio-qgo2xbkon-pixelart002s-projects.vercel.app" # Current Vercel Preview
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        # 🛡️ UNPOLY HEADERS: Inko allow karna zaroori hai
        allow_headers=[
            "*", 
            "X-Up-Target", 
            "X-Up-Fragment", 
            "X-Up-Validate", 
            "X-Up-Context",
            "X-Up-Mode"
        ],
        # 📣 EXPOSE HEADERS: Inke bina Unpoly redirect nahi samajh pata
        expose_headers=[
            "X-Up-Location", 
            "X-Up-Method", 
            "X-Up-Target",
            "X-Up-Fragment"
        ]
    )