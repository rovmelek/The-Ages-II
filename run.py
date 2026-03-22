"""Entry point: launch the game server with uvicorn."""
import uvicorn
from server.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "server.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
