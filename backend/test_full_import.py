"""测试导入链"""
import sys
sys.path.insert(0, '.')

print("1. config")
import config
print("   OK")

print("2. tools")
import tools
print("   OK")

print("3. regular_graph")
import regular_graph
print("   OK")

print("4. hitl_graph")
import hitl_graph
print("   OK")

print("5. multi_agent")
import multi_agent
print("   OK")

print("6. rag_graph")
import rag_graph
print("   OK")

print("7. customer_service")
import customer_service
print("   OK")

print("8. agent")
import agent
print("   OK")

print("9. main")
import main
print("   OK")

print("\nAll imports successful!")
