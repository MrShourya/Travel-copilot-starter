from fastapi import FastAPI

app = FastAPI(title="Travel Copilot API")


@app.get("/health")
def health():
    return {"status": "ok"}