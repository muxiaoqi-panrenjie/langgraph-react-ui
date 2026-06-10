"""最小测试脚本：逐步导入检查问题"""
import sys
import os

# 确保 backend 目录在路径中
sys.path.insert(0, os.path.dirname(__file__))

print("Step 1: Importing os and sys...")
print("Step 2: Importing dotenv...")
from dotenv import load_dotenv
load_dotenv(override=True)
print("Step 3: Importing langgraph...")
from langgraph.graph.message import add_messages
print("Step 4: Importing langchain_core...")
from langchain_core.messages import BaseMessage
print("Step 5: Importing init_chat_model...")
from langchain.chat_models import init_chat_model
print("Step 6: Initializing model...")
try:
    model = init_chat_model("anthropic:qwen3.6-plus")
    print("Model initialized OK")
except Exception as e:
    print(f"Model init failed: {e}")
print("Done!")
