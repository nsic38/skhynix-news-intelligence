@echo off
cd /d C:\Users\mjh05\skhynix-news-intelligence

set OLLAMA_MODEL=qwen3:4b

py update_news_ai.py

git add data/articles.json data/state.json

git diff --cached --quiet
if %errorlevel%==0 exit /b 0

git commit -m "auto newsroom update"
git push origin main
