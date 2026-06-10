"""测试导入链"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("1. config")
from core import config
print("   OK")

print("2. tools")
from core import tools
print("   OK")

print("3. regular_graph")
from graphs import regular_graph
print("   OK")

print("4. hitl_graph")
from graphs import hitl_graph
print("   OK")

print("5. multi_agent")
from graphs import multi_agent
print("   OK")

print("6. rag_graph")
from graphs import rag_graph
print("   OK")

print("7. customer_service")
from graphs import customer_service
print("   OK")

print("8. agent")
import agent
print("   OK")

print("9. main")
import main
print("   OK")

print("\nAll imports successful!")
