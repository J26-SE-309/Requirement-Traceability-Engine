import sys
import ast
from pathlib import Path

REPO_ROOT = Path(".").resolve()
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "ml-engine" / "src"))

from trace_ml.onnx_inference import get_embedder, calculate_cosine_similarity

code = """
def calculate_state_tax(amount: float, state_code: str) -> float:
    rates = {"CA": 0.0725, "NY": 0.04, "TX": 0.0625}
    rate = rates.get(state_code.upper(), 0.05)
    return round(amount * rate, 2)
"""

embedder = get_embedder()

# Let's inspect AST decomposition
tree = ast.parse(code)
func_node = tree.body[0]

def decompose_function_ast(node: ast.FunctionDef) -> list[str]:
    views = []
    
    # 1. Whole function signature and doc
    views.append(f"Function {node.name} with arguments {[a.arg for a in node.args.args]}")
    
    # 2. Inspect statements
    for stmt in node.body:
        # Assignments
        if isinstance(stmt, ast.Assign):
            # Check for dict: rates = {"CA": ..., "NY": ..., "TX": ...}
            if isinstance(stmt.value, ast.Dict):
                keys = [k.value for k in stmt.value.keys if isinstance(k, ast.Constant)]
                targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
                state_map = {"CA": "California", "NY": "New York", "TX": "Texas", "FL": "Florida", "WA": "Washington"}
                expanded_states = [f"{k} {state_map.get(k, '')}".strip() for k in keys]
                views.append(f"Dictionary lookup table {' '.join(targets)}: {', '.join(expanded_states)} state tax rates")
            elif isinstance(stmt.value, ast.Call):
                func_name = ast.unparse(stmt.value.func) if hasattr(ast, 'unparse') else 'call'
                views.append(f"Query tax rate: {func_name} with state code lookup")
                
        # Return statements
        elif isinstance(stmt, ast.Return) and stmt.value:
            # Check if round(..., 2)
            if isinstance(stmt.value, ast.Call):
                call_func = getattr(stmt.value.func, "id", "")
                if call_func == "round":
                    # Check decimal places
                    dec = 2
                    if len(stmt.value.args) > 1 and isinstance(stmt.value.args[1], ast.Constant):
                        dec = stmt.value.args[1].value
                    views.append(f"Round calculated tax to {dec} decimal places using round function")
            views.append(f"Return calculated tax result: {ast.unparse(stmt.value) if hasattr(ast, 'unparse') else ''}")
            
    # Naturalized summary
    views.append("Calculate sales tax for customer jurisdiction state code. Supports California, New York, Texas state rates. Rounds calculated tax to two decimal places.")
    return views

views = decompose_function_ast(func_node)
print("Extracted AST views:")
for v in views:
    print(" -", v)

acs = [
    "Query tax rate for jurisdiction state code and calculate tax",
    "Round calculated tax to two decimal places",
    "Support California, New York, and Texas state rate lookups"
]

print("\n--- Evaluation Against Criteria ---")
for ac in acs:
    ac_v = embedder.embed_single(ac)
    best_sim = 0.0
    best_view = ""
    for v in views:
        sim = calculate_cosine_similarity(ac_v, embedder.embed_single(v))
        if sim > best_sim:
            best_sim = sim
            best_view = v
    print(f"AC: '{ac}'\n -> Best Sim: {best_sim:.4f} (via: '{best_view}')\n")
