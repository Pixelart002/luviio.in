# api/main.py
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def home():
    return {"message": "Hello FastAPI!"}

@app.get("/pe")
async def pe():
    return {"message": "This is /pe route"}