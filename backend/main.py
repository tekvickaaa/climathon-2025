from typing import Optional

from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def read_root():
    return {"message": "Hello, FastAPI!"}


@app.get("/items/{item_id}")
async def read_item(item_id: int, q: Optional[str] = None):
    return {"item_id": item_id, "q": q}


if __name__ == "__main__":
    # When running directly from the `backend/` folder use: python main.py
    # or use uvicorn from the workspace root: uvicorn backend.main:app --reload
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
