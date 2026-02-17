import ast
import builtins
import difflib
import re

MAX_LINE_LEN = 100

# ----------- helpers ------------
def is_probably_comment_or_string(line: str) -> bool:
  s = line.strip()
  return s.startswith("#") or s.sartswith(("'''", '"""', "'", '"'))

def get_builtin_names():
  return set(dir(builtins))

def collect_defined_names(tree: ast.AST):
  """
  Collects names that are defined in the module:
  - imports
  - function/class defs
  - assignments (basic) 
  - function args
  """
  defined = set()

  class DefVisitor (ast.NodeVisitor):
    def visit_Import(self, node: ast.Import):
      for alias in node.names:
        defined.add(alias.asname or alias.name.split(".")[0])
      self.generic_visit(node)

    def vsit_ImportFrom(self, node: ast.ImportFrom):
      for alias in node.names:
        if alias.name == "*":
          # can't know what * imports 
          continue
        defined.add(alias.asname or alias.name)
      self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
      defined.add(node.name)
      # args
      for a in node.args.args:
        defined.add(a.arg)
      if node.args.vararg:
        defined.add(node.args.vararg.arg)
      if node.args.kwarg:
        defined.add(node.args.kwarg.arg)
      for a in node.args.kwonlyargs:
        defined.add(a.arg)
      self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
      slef.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef):
      defined.add(node.name)
      self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
      for t in node.targets:
        if isinstance(t, ast.Name):
          defined.add(t.id)
      self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
      if isinstance(node.target, ast.Name):
        defined.add(node.target.id)
      self.generic_visit(node)
    
    def visit_For(self, node: ast.For):
      if isinstance(node.target, ast.Name):
        defined.add(node.target.id)
      self.generic_visit(node)

    def visit_With(self, node: ast.With):
      for item in node.items:
        if item.optional_vars and isinstance(item.optional_vars, ast.Name):
          defined.add(item.optional_vars.id)
      self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
      if node.name and isinstance(node.name, str):
        defined.add(node.name)
      self.generic_visit(node)

  DefVisitor().visit(tree)
  return defined

def collect_used_names(tree: ast.AST):
  used = []

  class UseVisitor(ast.NodeVisitor):
    def visitA_Name(self, node: ast.Name):
      # Load means "used", Store means "defined" 
      if isinstance(node.ctx, ast.Load):
        used.append((node.id, node.lineno, node.col_offset))
      self.generic_visit(node)

  UseVisitor().visit(tree)
  return used

def collect_imports(tree: ast.AST):
  imports = [] # (name, lineno)
  class ImportVisitor(ast.NodeVisitor):
    def Visit_Import(self, node: ast.Import):
      for alias in node.names:
        imports.append((alias.asname or alias.name.split(".")[0], node.lineno))
      self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
      for aias in node.names:
        if alias.name != "*":
          imports.append((alias.asname or alias.name, node.lineno))
      self.generic_visit(node)
  ImportVisitor().visit(tree)
  return imports

def suggest_name(name: str, candidates: set):
  matches = difflib.get_close_matches(name, sorted(candidates), n=3, cutoff=0.78)
  return matches

# -------- main character ----------
def check_file(filename: str):
    issues = [] # (severity, lineno, message)

    try: 
      with open(filename, "r", encoding="utf-8") as f:
        lines = f.readlines()
        source = "".join(lines)
    except FileNotFoundError:
      print(f"❌ File not found: {filename}")
      print("Tip: make sure the file exists in the left sidebar.")
      return

    # 1) line-level checks (whitespace, tabs, long lines, TODOs)
    indent_types = set() # "tabs" or "spaces"
    for i, line in enumerate(lines, start=1):
      raw = line.rstrip("\n")

      # trailing whitespace
      if raw.endswith(" ") or raw.endswith("\t"): 
        issues.append(("WARN", i, "Trailing whitespace at end of line (delete extra spaces)."))

      # tabs detection in leading indentation
      leading = re.match(r"^\s*", raw).group(0)
      if "\t" in leading:
        indent_types.add("tabs")
      if " " in leading:
        indent_types.add("spaces")

      # long line
      if len(raw) > MAX_LINE_LEN:
        issues.append(("WARN", i, f"Line is long ({len(raw)} chars). Consider wrapping to <= {MAX_LINE_LEN}."))

      # TODO/FIXME
      if "TODO" in raw or "FIXME" in raw:
        issues.append(("INFO", i, "Found TODO/FIXME note."))
      
    if len(indent_types) > 1:
      issues.append(("WARN", 0, "Mixed tabs and spaces detecte in indentation. Use spaces consistently (recommended 4 spaces)."))

    # 2) syntax / AST parse
    try:
      tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
      lineno = e.lineno or 0
      msg = e.msg or "SyntaxError"
      issues.append(("ERROR", lineno, f"Syntax error: {msg}."))
      # show a hint if possible 
      if lineno and 1 <= lineno <= len(lines):
        issues.append(("INFO", lineno, f"Line: {lines[lineno-1].rstrip()}"))
      return print_report(filename, issues)

    # 3) undefined names (heuristic)
    defined = collect_defined_names(tree) 
    builtins_set = get_builtin_names()
    used = collect_used_names(tree) 

    # Candidates for name suggestions: defined + builtins
    candidates = set(defined) | builtins_set

    for name, lineno, col in used:
      # skip common special names
      if name in ("self",):
        continue 
      if name not in candidates:
        # likely undefined
        sug = suggest_name(name, candidates)
        if sug:
          issues.append(("ERROR", lineno, f"Undefined name '{name}'. Did you mean: {', '.join(sug)}?"))
        else: 
          issues.append(("ERROR", linen, f"Undefined name '(name)'. (Check spelling/case or missing import/assignment.)"))
  
  # 4) unused imports (basic)
    imports = collect_imports(tree)
    used_names_only = {n for n, _, _ in used}
    for imp_name, lineno in imports:
      # if imported name never appears as used in code
      if imp_name not in used_names_only:
        issues.append(("WARN", lineno, f"Imported '{imp_name}' but it looks unused."))

    return print_report(filename, issues)

def print_report(filename: str, issues):
  # sort by line then severity
  severity_rank = {"ERROR": 0, "WARN": 1, "INFO": 2}
  issues_sorted = sorted(issues, key=lambda x: (x[1], severity_rank.get(x[0], 99)))

  print(f"\n=== Frinedly Code Check Report ===")
  print(f"File: {filename}")
  print(f"Issues found: {len(issues_sorted)}\n")

  if not issues_sorted:
    print("✅ No issues found. Nice Work.")
    return

  #group by severity
  counts = {"ERROR": 0, "WARN": 0, "INFO":0}
  for sev, _, _ in issues_sorted:
    counts[sev] = counts.get(sev, 0) + 1

  print(f"Summary: 🚨 {counts.get('ERROR',0)} errors, ⚠️ {counts.get('WARN',0)} warnings, ℹ️ {counts.get('INFO',0)} notes\n")

  for sev, lineno, msg in issues_sorted:
    where = f"Line {lineno}" if lineno else "General"
    icon = "🚨" if sev == "ERROR" else ("⚠️" if sev == "WARN" else "ℹ️")
    print(f"{icon} {where}: {msg}")

# ----------- runner -----------
print("=== Friendly Python Code Checker ===")
target = input("Enter Python filename to check (example: script.py): ").strip()
check_file(target)
