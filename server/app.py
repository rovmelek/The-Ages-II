"""Minimal FastAPI application — full Game orchestrator comes in Story 1.8."""
from fastapi import FastAPI

from server.net.websocket import websocket_endpoint

app = FastAPI(title="The Ages II")
app.add_api_websocket_route("/ws/game", websocket_endpoint)
