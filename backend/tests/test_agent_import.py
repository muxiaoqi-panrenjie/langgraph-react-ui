"""测试 agent.py 导入"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("1. Importing config...")
from core.config import message_content_to_text
print("   OK")

print("2. Importing tools...")
from core.tools import regular_tools, hitl_tools, hitl_tools_by_name
print("   OK")

print("3. Importing regular_graph...")
from graphs.regular_graph import graph
print("   OK")

print("4. Importing hitl_graph...")
from graphs.hitl_graph import hitl_graph
print("   OK")

print("5. Importing multi_agent...")
from graphs.multi_agent import multi_agent_graph, music_tools, invoice_tools
print("   OK")

print("6. Importing rag_graph...")
from graphs.rag_graph import rag_graph
print("   OK")

print("7. Importing customer_service...")
from graphs.customer_service import customer_service_graph
print("   OK")

print("\nAll agent imports successful!")
