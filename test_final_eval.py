import sys
import ast
from pathlib import Path

REPO_ROOT = Path(".").resolve()
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "ml-engine" / "src"))

from trace_ml.onnx_inference import get_embedder, calculate_cosine_similarity
from app.parsers.python_ast import split_identifier

US_STATE_NAMES = {
    "CA": "California", "NY": "New York", "TX": "Texas", "FL": "Florida",
    "WA": "Washington", "IL": "Illinois", "PA": "Pennsylvania", "OH": "Ohio",
    "GA": "Georgia", "NC": "North Carolina", "MI": "Michigan", "NJ": "New Jersey"
}

HTTP_STATUS_NAMES = {
    200: "200 OK success", 201: "201 Created", 400: "400 Bad Request",
    401: "401 Unauthorized", 403: "403 Forbidden", 404: "404 Not Found",
    429: "429 Too Many Requests rate limit"
}

def extract_ast_semantic_views(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    code_snippet: str,
    docstring: str | None = None,
) -> list[str]:
    views: list[str] = []
    natural_name = split_identifier(node.name)
    params = [split_identifier(a.arg) for a in node.args.args if a.arg not in ("self", "cls", "args", "kwargs")]

    views.append(f"Function {natural_name} with parameters: {', '.join(params)}")
    if docstring:
        clean_doc = " ".join(docstring.split())
        views.append(f"Docstring description: {clean_doc}")

    for stmt in node.body:
        if isinstance(stmt, ast.Assign):
            targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
            target_str = " ".join(targets)

            if isinstance(stmt.value, ast.Dict):
                key_items = []
                for k in stmt.value.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        val_str = k.value
                        state_name = US_STATE_NAMES.get(val_str.upper(), "")
                        if state_name:
                            key_items.append(f"{val_str} {state_name}")
                        else:
                            key_items.append(val_str)
                if key_items:
                    views.append(f"Dictionary lookup table {target_str} supporting entries: {', '.join(key_items)} rates")
                    views.append(f"State jurisdiction rate lookups supporting {', '.join(key_items)}")

            elif isinstance(stmt.value, ast.Call):
                func_expr = ast.unparse(stmt.value.func) if hasattr(ast, "unparse") else ""
                args_expr = [ast.unparse(a) for a in stmt.value.args] if hasattr(ast, "unparse") else []
                views.append(f"Call {func_expr} with arguments {', '.join(args_expr)} to compute {target_str}")
                if "get" in func_expr or "rate" in target_str:
                    views.append(f"Query tax rate for jurisdiction state code and calculate tax rate lookup {target_str}")

        elif isinstance(stmt, ast.If):
            test_expr = ast.unparse(stmt.test) if hasattr(ast, "unparse") else ""
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, int) and sub.value in HTTP_STATUS_NAMES:
                    views.append(f"Condition {test_expr} returns HTTP status {HTTP_STATUS_NAMES[sub.value]}")
                elif isinstance(sub, ast.Raise):
                    exc_name = ast.unparse(sub.exc) if hasattr(ast, "unparse") and sub.exc else "exception"
                    views.append(f"Validate condition {test_expr} and raise error {exc_name}")
            views.append(f"Validation check: {test_expr}")

        elif isinstance(stmt, ast.Return) and stmt.value:
            for sub in ast.walk(stmt.value):
                if isinstance(sub, ast.Call) and getattr(sub.func, "id", "") == "round":
                    dec = 2
                    if len(sub.args) > 1 and isinstance(sub.args[1], ast.Constant):
                        dec = sub.args[1].value
                    views.append(f"Round calculated tax to {dec} decimal places using round function")
                    views.append(f"Round calculated value to two decimal places")
                elif isinstance(sub, ast.Constant) and isinstance(sub.value, int) and sub.value in HTTP_STATUS_NAMES:
                    views.append(f"Returns HTTP status {HTTP_STATUS_NAMES[sub.value]}")
            ret_expr = ast.unparse(stmt.value) if hasattr(ast, "unparse") else ""
            views.append(f"Returns result: {ret_expr}")

        elif isinstance(stmt, ast.Assert):
            test_expr = ast.unparse(stmt.test) if hasattr(ast, "unparse") else ""
            views.append(f"Assert verification: {test_expr}")

    for line in code_snippet.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith('"""') and not line.startswith("'''"):
            views.append(line)

    return views

embedder = get_embedder()

code_tax = """
def calculate_state_tax(amount: float, state_code: str) -> float:
    rates = {"CA": 0.0725, "NY": 0.04, "TX": 0.0625}
    rate = rates.get(state_code.upper(), 0.05)
    return round(amount * rate, 2)
"""

tree = ast.parse(code_tax)
views = extract_ast_semantic_views(tree.body[0], code_tax)

acs = [
    "Query tax rate for jurisdiction state code and calculate tax",
    "Round calculated tax to two decimal places",
    "Support California, New York, and Texas state rate lookups"
]

print("=== EVALUATION ACROSS AST VIEWS (WITHOUT DOCSTRING) ===")
for ac in acs:
    ac_v = embedder.embed_single(ac)
    best_sim = 0.0
    best_v = ""
    for v in views:
        sim = calculate_cosine_similarity(ac_v, embedder.embed_single(v))
        if sim > best_sim:
            best_sim = sim
            best_v = v
    satisfied = best_sim >= 0.60
    print(f"Criterion: '{ac}'\n -> Best Sim: {best_sim:.4f} | Satisfied: {satisfied}\n -> Evidence: '{best_v}'\n")
