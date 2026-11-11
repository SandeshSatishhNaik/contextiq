"""Start ContextIQ:  python run.py   →  http://localhost:8000

HOST and PORT come from the environment when set (Render sets PORT).
"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")), reload=False)
