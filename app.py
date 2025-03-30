import asyncio
import logging
import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gitsummarize.auth.key_manager import KeyGroup, KeyManager
from gitsummarize.clients.openai import OpenAIClient
from gitsummarize.clients.supabase import SupabaseClient
from src.gitsummarize.clients.github import GithubClient
from src.gitsummarize.clients.google_genai import GoogleGenAI

load_dotenv()

logger = logging.getLogger(__name__)

gh = GithubClient(os.getenv("GITHUB_TOKEN"))
openai = OpenAIClient(os.getenv("OPENAI_API_KEY"))
supabase = SupabaseClient(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ADMIN_KEY"))

key_manager = KeyManager()
key_manager.add_key(KeyGroup.GEMINI, os.getenv("GEMINI_API_KEY"))
key_manager.add_key(KeyGroup.GEMINI, os.getenv("GEMINI_API_KEY_2"))
key_manager.add_key(KeyGroup.GEMINI, os.getenv("GEMINI_API_KEY_3"))

app = FastAPI()


class SummarizeRequest(BaseModel):
    repo_url: str


@app.post("/summarize")
async def summarize(request: SummarizeRequest):
    if not _validate_repo_url(request.repo_url):
        raise HTTPException(status_code=400, detail="Invalid GitHub URL")
    logger.info(f"Summarizing repository: {request.repo_url}")

    directory_structure = await gh.get_directory_structure_from_url(request.repo_url)
    all_content = await gh.get_all_content_from_url(request.repo_url)
    google_genai = GoogleGenAI(key_manager.get_key(KeyGroup.GEMINI))

    try:
        client = GoogleGenAI(key_manager.get_key(KeyGroup.GEMINI))
        business_summary = await client.get_business_summary(
            directory_structure, all_content
        )
        client = GoogleGenAI(key_manager.get_key(KeyGroup.GEMINI))
        technical_documentation = await client.get_technical_documentation(
            directory_structure, all_content
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    supabase.insert_repo_summary(
        request.repo_url, business_summary, technical_documentation
    )

    return JSONResponse(content={"message": "Repository summarized successfully"})


def _validate_repo_url(repo_url: str) -> bool:
    return repo_url.startswith("https://github.com/")


@app.post("/summarize-local")
async def summarize_store_local(request: SummarizeRequest):
    if not _validate_repo_url(request.repo_url):
        raise HTTPException(status_code=400, detail="Invalid GitHub URL")
    logger.info(f"Summarizing repository: {request.repo_url}")

    directory_structure = await gh.get_directory_structure_from_url(request.repo_url)
    all_content = await gh.get_all_content_from_url(request.repo_url)

    business_summary, technical_documentation = await asyncio.gather(
        openai.get_business_summary(directory_structure, all_content),
        openai.get_technical_documentation(directory_structure, all_content),
    )

    with open("tmp/openai/business_summary.txt", "w") as f:
        f.write(business_summary)
    with open("tmp/openai/technical_documentation.txt", "w") as f:
        f.write(technical_documentation)
