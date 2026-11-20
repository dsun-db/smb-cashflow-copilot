"""SMB Cash-Flow Copilot - FastAPI backend + single-page console (Databricks App)."""
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import backend

app = FastAPI(title="SMB Cash-Flow Copilot")
HERE = os.path.dirname(__file__)


class Ask(BaseModel):
    account_id: str
    question: str


class Action(BaseModel):
    account_id: str
    agent_id: str
    action_type: str
    note: str = ""


class GenieAsk(BaseModel):
    question: str
    conversation_id: str | None = None


@app.get("/api/health")
def api_health():
    return backend.health()


@app.get("/api/agents")
def api_agents():
    return backend.agents()


@app.get("/api/portfolio")
def api_portfolio(agent_id: str):
    return backend.portfolio(agent_id)


@app.get("/api/account/{account_id}")
def api_account(account_id: str):
    return backend.account(account_id)


@app.get("/api/search")
def api_search(q: str):
    return backend.similar_notes(q, k=6)


@app.post("/api/copilot")
def api_copilot(body: Ask):
    return backend.ask_copilot(body.account_id, body.question)


@app.post("/api/actions")
def api_action(body: Action):
    return backend.log_action(body.account_id, body.agent_id, body.action_type, body.note)


@app.post("/api/genie")
def api_genie(body: GenieAsk):
    return backend.ask_genie(body.question, body.conversation_id)


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
