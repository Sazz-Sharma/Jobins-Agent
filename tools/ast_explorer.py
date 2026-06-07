"""
ASTCodeMapExplorer — Custom structural code analysis tool.

Uses Python's native `ast` module to scan code files and return ONLY a map of:
  - Classes (with bases, decorators)
  - Function/method signatures (with decorators, arguments, return annotations)
  - Docstrings
  - Corresponding line numbers

Completely strips out implementation bodies, producing a concise structural
outline. A 5,000-line file gets distilled down to a ~20-line functional map.

ADVERSARIAL DEFENSE: Prevents massive files from drowning the agent's context
window. The agent can safely inventory any codebase without pulling thousands
of lines of raw source code into the prompt.
"""

from __future__ import annotations

import ast
import os


class ASTCodeMapExplorer:
    """
    Structural code parser that produces a concise map of a Python file's
    public interface — classes, functions, signatures, docstrings, and
    line numbers — without any implementation details.
    """

    name = "ast_code_map_explorer"
    description = (
        "Analyze a Python file's structure without reading its full source code. "
        "Input: absolute or relative path to a .py file. "
        "Output: a structural map showing classes, function signatures, docstrings, "
        "and line numbers — with all implementation bodies stripped out. "
        "Use this to safely inventory large codebases without context overflow."
    )

    def run(self, file_path: str) -> str:
        """Execute the AST exploration on the given file path."""
        file_path = file_path.strip().strip("'\"")

        # ── Validation ───────────────────────────────────────────────
        if not os.path.exists(file_path):
            return f"ERROR: File not found: {file_path}"

        if not file_path.endswith(".py"):
            return f"ERROR: ASTCodeMapExplorer only supports Python (.py) files. Got: {file_path}"

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        except PermissionError:
            return f"ERROR: Permission denied reading {file_path}"
        except OSError as e:
            return f"ERROR: Could not read file {file_path}: {e}"

        # ── Parse AST ────────────────────────────────────────────────
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as e:
            return f"ERROR: Syntax error in {file_path} at line {e.lineno}: {e.msg}"

        # ── Build structural map ─────────────────────────────────────
        lines = []
        lines.append(f"═══ AST Code Map: {os.path.basename(file_path)} ═══")
        lines.append(f"File: {file_path}")
        lines.append(f"Total lines: {len(source.splitlines())}")
        lines.append("")

        # Module-level docstring
        module_doc = ast.get_docstring(tree)
        if module_doc:
            doc_preview = module_doc[:200] + ("..." if len(module_doc) > 200 else "")
            lines.append(f'Module Docstring: """{doc_preview}"""')
            lines.append("")

        # Top-level imports (condensed)
        imports = self._extract_imports(tree)
        if imports:
            lines.append(f"Imports: {', '.join(imports[:15])}")
            if len(imports) > 15:
                lines.append(f"  ... and {len(imports) - 15} more imports")
            lines.append("")

        # Top-level constants/assignments
        constants = self._extract_constants(tree)
        if constants:
            lines.append("Constants/Globals:")
            for c in constants[:10]:
                lines.append(f"  L{c['line']:>4}: {c['name']}")
            lines.append("")

        # Functions and classes
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                lines.extend(self._format_function(node, indent=0))
                lines.append("")
            elif isinstance(node, ast.ClassDef):
                lines.extend(self._format_class(node, indent=0))
                lines.append("")

        if len(lines) <= 4:
            lines.append("(No classes or functions found in this file)")

        return "\n".join(lines)

    # ── Private helpers ──────────────────────────────────────────────────

    def _extract_imports(self, tree: ast.AST) -> list[str]:
        """Extract import names (condensed)."""
        imports = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}")
        return imports

    def _extract_constants(self, tree: ast.AST) -> list[dict]:
        """Extract top-level assignments (constants/globals)."""
        constants = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        constants.append({"name": target.id, "line": node.lineno})
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                constants.append({"name": node.target.id, "line": node.lineno})
        return constants

    def _format_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, indent: int = 0
    ) -> list[str]:
        """Format a function definition as a structural outline."""
        prefix = "  " * indent
        is_async = isinstance(node, ast.AsyncFunctionDef)
        keyword = "async def" if is_async else "def"

        # Build signature
        args = self._format_args(node.args)
        returns = ""
        if node.returns:
            try:
                returns = f" -> {ast.unparse(node.returns)}"
            except Exception:
                returns = " -> ..."

        # Decorators
        decorators = []
        for dec in node.decorator_list:
            try:
                decorators.append(f"{prefix}  @{ast.unparse(dec)}")
            except Exception:
                decorators.append(f"{prefix}  @<decorator>")

        lines = []
        for dec in decorators:
            lines.append(dec)

        end_line = node.end_lineno or node.lineno
        lines.append(f"{prefix}  L{node.lineno}-{end_line}: {keyword} {node.name}({args}){returns}")

        # Docstring
        docstring = ast.get_docstring(node)
        if docstring:
            doc_preview = docstring[:150] + ("..." if len(docstring) > 150 else "")
            lines.append(f'{prefix}    """{doc_preview}"""')

        return lines

    def _format_class(self, node: ast.ClassDef, indent: int = 0) -> list[str]:
        """Format a class definition with its methods."""
        prefix = "  " * indent

        # Class header
        bases = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except Exception:
                bases.append("?")

        base_str = f"({', '.join(bases)})" if bases else ""

        # Decorators
        lines = []
        for dec in node.decorator_list:
            try:
                lines.append(f"{prefix}  @{ast.unparse(dec)}")
            except Exception:
                lines.append(f"{prefix}  @<decorator>")

        end_line = node.end_lineno or node.lineno
        lines.append(f"{prefix}  L{node.lineno}-{end_line}: class {node.name}{base_str}:")

        # Class docstring
        docstring = ast.get_docstring(node)
        if docstring:
            doc_preview = docstring[:150] + ("..." if len(docstring) > 150 else "")
            lines.append(f'{prefix}    """{doc_preview}"""')

        # Class-level attributes
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        lines.append(f"{prefix}    L{child.lineno}: {target.id} = ...")
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                try:
                    ann = ast.unparse(child.annotation)
                except Exception:
                    ann = "..."
                lines.append(f"{prefix}    L{child.lineno}: {child.target.id}: {ann}")

        # Methods
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                lines.extend(self._format_function(child, indent=indent + 1))
            elif isinstance(child, ast.ClassDef):
                lines.extend(self._format_class(child, indent=indent + 1))

        return lines

    def _format_args(self, args: ast.arguments) -> str:
        """Format function arguments into a signature string."""
        parts = []

        # Positional-only args
        for arg in args.posonlyargs:
            parts.append(self._format_single_arg(arg))
        if args.posonlyargs:
            parts.append("/")

        # Regular args
        num_defaults = len(args.defaults)
        num_args = len(args.args)
        for i, arg in enumerate(args.args):
            default_idx = i - (num_args - num_defaults)
            if default_idx >= 0:
                parts.append(f"{self._format_single_arg(arg)}=...")
            else:
                parts.append(self._format_single_arg(arg))

        # *args
        if args.vararg:
            parts.append(f"*{self._format_single_arg(args.vararg)}")
        elif args.kwonlyargs:
            parts.append("*")

        # Keyword-only args
        for i, arg in enumerate(args.kwonlyargs):
            default = args.kw_defaults[i] if i < len(args.kw_defaults) else None
            if default is not None:
                parts.append(f"{self._format_single_arg(arg)}=...")
            else:
                parts.append(self._format_single_arg(arg))

        # **kwargs
        if args.kwarg:
            parts.append(f"**{self._format_single_arg(args.kwarg)}")

        return ", ".join(parts)

    def _format_single_arg(self, arg: ast.arg) -> str:
        """Format a single argument with optional type annotation."""
        if arg.annotation:
            try:
                return f"{arg.arg}: {ast.unparse(arg.annotation)}"
            except Exception:
                return f"{arg.arg}: ..."
        return arg.arg
