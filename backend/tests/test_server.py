"""最小化 main.py 测试"""
import sys
sys.path.insert(0, '.')

print("Starting minimal server test...")

from fastapi import FastAPI
app = FastAPI()

@app.get("/test")
def test():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    print("Starting uvicorn on port 8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
