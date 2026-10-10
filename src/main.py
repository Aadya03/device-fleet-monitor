"""Entry point: `python -m src.main` boots the server on :8000."""
import uvicorn

from src.api import create_app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
