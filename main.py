from dotenv import load_dotenv
import os
import openai

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

print("✅ API 키:", openai.api_key)


from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "GO!비서 FastAPI 백엔드"}