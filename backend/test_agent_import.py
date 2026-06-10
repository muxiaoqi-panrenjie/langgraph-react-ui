"""测试 agent.py 导入"""
import sys
sys.path.insert(0, '.')

print("1. Importing config...")
from config import message_content_to_text
print("   OK")

print("2. Importing tools...")
from tools import regular_tools, hitl_tools, hitl_tools_by_name
print("   OK")

print("3. Importing regular_graph...")
from regular_graph import graph
print("   OK")

print("4. Importing hitl_graph...")
from hitl_graph import hitl_graph
print("   OK")

print("5. Importing multi_agent...")
from multi_agent import multi_agent_graph, music_tools, invoice_tools
print("   OK")

print("6. Importing rag_graph...")
from rag_graph import rag_graph
print("   OK")

print("7. Importing customer_service...")
from customer_service import customer_service_graph
print("   OK")

print("\nAll agent imports successful!")
