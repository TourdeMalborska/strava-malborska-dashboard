from fastapi import FastAPI, Request

app = FastAPI()

@app.get("/api/strava/webhook")
async def strava_webhook_verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == "malborska123":
        return {"hub.challenge": challenge}

    return {"status": "ignored"}


@app.post("/api/strava/webhook")
async def strava_webhook_event(request: Request):
    body = await request.json()
    print("EVENT RECEIVED:", body)
    return {"status": "ok"}
