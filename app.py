
import ast
import io
import json
import tokenize
import zipfile
from pathlib import PurePosixPath

import graphviz
import streamlit as st


# -------------------- CONFIGURATION --------------------

MAX_ZIP_SIZE = 20 * 1024 * 1024
MAX_FILES = 1000
MAX_SOURCE_SIZE = 50 * 1024 * 1024
MAX_FILE_SIZE = 2 * 1024 * 1024


# -------------------- PAGE SETUP --------------------

st.set_page_config(
    page_title="CodeXray | Python Project Analyzer",
    page_icon="🔍",
    layout="wide",
)

st.title("🔍 CodeXray")
st.subheader("Understand Any Python Project Visually")
st.write(
    "Upload a Python project ZIP to explore its code, "
    "inspect code quality, visualize dependencies, "
    "and explain code in simple English."
)


# -------------------- ZIP FILE READER --------------------

def load_python_files(upload):
    if upload.size > MAX_ZIP_SIZE:
        raise ValueError("ZIP file is too large. Maximum size is 20 MB.")

    files = {}
    total_size = 0

    with zipfile.ZipFile(io.BytesIO(upload.getvalue())) as archive:
        entries = [
            item for item in archive.infolist()
            if not item.is_dir()
        ]

        if len(entries) > MAX_FILES:
            raise ValueError(
                f"The ZIP contains too many files. Maximum: {MAX_FILES}."
            )

        for item in entries:
            path = PurePosixPath(item.filename)

            # Ignore unsafe paths and non-Python files.
            if path.is_absolute() or ".." in path.parts:
                continue

            if not item.filename.lower().endswith(".py"):
                continue

            if item.file_size > MAX_FILE_SIZE:
                continue

            if item.file_size > 0 and item.compress_size == 0:
                continue

            if (
                item.compress_size > 0
                and item.file_size / item.compress_size > 200
            ):
                continue

            total_size += item.file_size

            if total_size > MAX_SOURCE_SIZE:
                raise ValueError(
                    "The total Python source size exceeds 50 MB."
                )

            try:
                raw = archive.read(item)
                source = raw.decode("utf-8-sig")
            except (UnicodeDecodeError, RuntimeError, OSError):
                continue

            files[path.as_posix()] = source

    if not files:
        raise ValueError(
            "No readable Python (.py) files were found in this ZIP."
        )

    return files


# -------------------- PYTHON PARSER --------------------

def parse_python(source):
    try:
        tree = ast.parse(source)
        return tree, None
    except SyntaxError as error:
        return None, (
            f"Line {error.lineno}: {error.msg}"
            if error.lineno
            else error.msg
        )


# -------------------- CODE QUALITY ANALYSIS --------------------

def analyze_python(source):
    tree, syntax_error = parse_python(source)

    if syntax_error:
        return {
            "syntax_error": syntax_error,
            "functions": [],
            "classes": [],
            "imports": [],
            "issues": [],
        }

    functions = []
    classes = []
    imports = []
    issues = []
    lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            functions.append({
                "name": node.name,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "args": [
                    arg.arg for arg in node.args.args
                ],
                "async": isinstance(node, ast.AsyncFunctionDef),
            })

            start = node.lineno
            end = getattr(node, "end_lineno", start)

            if end - start + 1 > 50:
                issues.append({
                    "type": "Long function",
                    "line": start,
                    "message": (
                        f"Function '{node.name}' is longer than 50 lines."
                    ),
                })

        elif isinstance(node, ast.ClassDef):
            classes.append({
                "name": node.name,
                "line": node.lineno,
                "methods": [
                    child.name
                    for child in node.body
                    if isinstance(
                        child,
                        (ast.FunctionDef, ast.AsyncFunctionDef),
                    )
                ],
            })

        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    "module": alias.name,
                    "name": alias.asname or alias.name.split(".")[0],
                    "line": node.lineno,
                })

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""

            for alias in node.names:
                if alias.name != "*":
                    imports.append({
                        "module": module,
                        "name": alias.asname or alias.name,
                        "line": node.lineno,
                    })

    for number, line in enumerate(lines, start=1):
        if len(line) > 100:
            issues.append({
                "type": "Long line",
                "line": number,
                "message": (
                    f"Line {number} contains {len(line)} characters."
                ),
            })

    # A lightweight heuristic, not a complete unused-import detector.
    try:
        tokens = [
            token.string
            for token in tokenize.generate_tokens(
                io.StringIO(source).readline
            )
            if token.type == tokenize.NAME
        ]

        for item in imports:
            if tokens.count(item["name"]) <= 1:
                issues.append({
                    "type": "Possible unused import",
                    "line": item["line"],
                    "message": (
                        f"Import '{item['name']}' may be unused. "
                        "Check it manually."
                    ),
                })
    except (tokenize.TokenError, IndentationError):
        pass

    return {
        "syntax_error": None,
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "issues": issues,
    }


# -------------------- DEPENDENCY GRAPH --------------------

def build_graph(files):
    graph = graphviz.Digraph()
    graph.attr(rankdir="LR")
    graph.attr("node", shape="box", style="rounded")

    module_names = {}

    for path in files:
        parts = PurePosixPath(path).with_suffix("").parts

        if parts and parts[-1] == "__init__":
            parts = parts[:-1]

        module = ".".join(parts)

        if module:
            module_names[module] = path

    for path in files:
        graph.node(path)

    for path, source in files.items():
        tree, error = parse_python(source)

        if error:
            continue

        current_parts = list(
            PurePosixPath(path).with_suffix("").parts
        )

        if current_parts and current_parts[-1] == "__init__":
            current_parts = current_parts[:-1]

        current_module = ".".join(current_parts)
        current_package = (
            current_module
            if path.endswith("__init__.py")
            else current_module.rpartition(".")[0]
        )

        for node in ast.walk(tree):
            targets = []

            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]

            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    package_parts = current_package.split(".")
                    remove_count = node.level - 1

                    if remove_count <= len(package_parts):
                        base = package_parts[:len(package_parts) - remove_count]
                    else:
                        base = []

                    if node.module:
                        base.extend(node.module.split("."))

                    base_module = ".".join(part for part in base if part)
                else:
                    base_module = node.module or ""

                targets = [base_module] if base_module else []

            for target in targets:
                if target in module_names:
                    graph.edge(path, module_names[target])

                else:
                    # Also handle imports from a package submodule.
                    matches = [
                        module for module in module_names
                        if target.startswith(module + ".")
                    ]

                    if matches:
                        best_match = max(matches, key=len)
                        graph.edge(path, module_names[best_match])

    return graph


# -------------------- FREE CODE EXPLAINER --------------------

def explain_python(source, filename):
    tree, syntax_error = parse_python(source)

    if syntax_error:
        return (
            f"### ⚠️ Syntax problem\n\n"
            f"I couldn't fully understand this file because of "
            f"a Python syntax error: **{syntax_error}**.\n\n"
            "Fix the syntax error and analyze the file again."
        )

    lines = source.splitlines()
    functions = []
    classes = []
    imports = []
    variables = []
    returns = 0
    conditions = 0
    loops = 0
    exceptions = 0

    for node in ast.walk(tree):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            functions.append(node)

        elif isinstance(node, ast.ClassDef):
            classes.append(node)

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(node)

        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            variables.append(node)

        elif isinstance(node, ast.Return):
            returns += 1

        elif isinstance(node, (ast.If, ast.IfExp)):
            conditions += 1

        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            loops += 1

        elif isinstance(node, (ast.Try, ast.ExceptHandler)):
            exceptions += 1

    report = [
        f"### 📘 Explanation of `{filename}`",
        "",
        "#### 1. What this file contains",
        "",
    ]

    if classes:
        report.append(
            f"- **{len(classes)} class(es):** "
            + ", ".join(f"`{item.name}`" for item in classes[:15])
        )

    if functions:
        report.append(
            f"- **{len(functions)} function(s):** "
            + ", ".join(f"`{item.name}()`" for item in functions[:20])
        )

    if imports:
        report.append(
            f"- **{len(imports)} import statement(s):** "
            "These bring in modules or names defined elsewhere."
        )

    if not classes and not functions:
        report.append(
            "- This file mainly contains top-level statements "
            "rather than class or function definitions."
        )

    report.extend([
        "",
        "#### 2. How the code is structured",
        "",
        f"- **Variables and assignments:** {len(variables)}",
        f"- **Conditions:** {conditions}",
        f"- **Loops:** {loops}",
        f"- **Return statements:** {returns}",
        f"- **Exception-handling constructs:** {exceptions}",
    ])

    report.extend(["", "#### 3. Function explanations", ""])

    if functions:
        for function in functions[:20]:
            args = [
                arg.arg for arg in function.args.args
            ]

            kind = (
                "asynchronous function"
                if isinstance(function, ast.AsyncFunctionDef)
                else "function"
            )

            report.append(f"**`{function.name}()`**")

            if args:
                report.append(
                    f"- Parameters: {', '.join(f'`{arg}`' for arg in args)}."
                )
            else:
                report.append("- Parameters: none.")

            report.append(
                f"- Defined around line {function.lineno}."
            )

            docstring = ast.get_docstring(function)

            if docstring:
                report.append(f"- Description: {docstring.strip()}")

            else:
                report.append(
                    f"- This {kind} contains the operations written "
                    "in its body. Read those statements to determine "
                    "its exact behavior."
                )

            report.append("")

        if len(functions) > 20:
            report.append(
                f"*Showing 20 of {len(functions)} functions.*"
            )
    else:
        report.append("No functions were found.")

    report.extend(["", "#### 4. Class explanations", ""])

    if classes:
        for cls in classes[:15]:
            methods = [
                node.name for node in cls.body
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef)
                )
            ]

            report.append(f"**`{cls.name}`**")

            if methods:
                report.append(
                    "- Methods: "
                    + ", ".join(f"`{name}()`" for name in methods)
                    + "."
                )
            else:
                report.append("- No directly defined methods were found.")

            docstring = ast.get_docstring(cls)

            if docstring:
                report.append(f"- Description: {docstring.strip()}")

            report.append("")
    else:
        report.append("No classes were found.")

    report.extend(["", "#### 5. Important statements", ""])

    important_keywords = {
        "print": "Displays information on the screen.",
        "input": "Reads input from the user.",
        "open": "Opens a file or file-like resource.",
        "range": "Creates a sequence of numbers, often for loops.",
        "len": "Returns the number of items in an object.",
        "return": "Sends a result back from a function.",
        "yield": "Produces a value from a generator.",
        "raise": "Raises an exception.",
        "assert": "Checks a condition and raises an error if it is false.",
    }

    found_keywords = set()

    try:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                else:
                    continue

                if name in important_keywords:
                    found_keywords.add(name)

    except Exception:
        pass

    if found_keywords:
        for name in sorted(found_keywords):
            report.append(
                f"- **`{name}`:** {important_keywords[name]}"
            )
    else:
        report.append(
            "No common built-in operations were detected by this simple scan."
        )

    report.extend([
        "",
        "#### 6. Read the code line by line",
        "",
    ])

    shown_lines = [
        (number, line)
        for number, line in enumerate(lines, start=1)
        if line.strip()
    ]

    if not shown_lines:
        report.append("This file is empty.")
    else:
        for number, line in shown_lines[:80]:
            stripped = line.strip()

            if stripped.startswith("#"):
                explanation = "A comment for human readers."
            elif stripped.startswith(("import ", "from ")):
                explanation = "Imports code or names from a module."
            elif stripped.startswith("class "):
                explanation = "Defines a class."
            elif stripped.startswith("async def "):
                explanation = "Defines an asynchronous function."
            elif stripped.startswith("def "):
                explanation = "Defines a function."
            elif stripped.startswith("return"):
                explanation = "Returns a value from the current function."
            elif stripped.startswith("if ") or stripped.startswith("elif "):
                explanation = "Checks a condition."
            elif stripped == "else:":
                explanation = "Runs when the preceding condition is not met."
            elif stripped.startswith(("for ", "async for ")):
                explanation = "Starts a loop over items."
            elif stripped.startswith("while "):
                explanation = "Repeats while a condition is true."
            elif stripped.startswith("try:"):
                explanation = "Starts a block for handling exceptions."
            elif stripped.startswith(("except", "finally:")):
                explanation = "Handles an exception or performs cleanup."
            elif stripped.startswith("raise "):
                explanation = "Raises an exception."
            elif stripped.startswith("pass"):
                explanation = "Does nothing; acts as a placeholder."
            elif stripped.startswith("break"):
                explanation = "Exits the current loop."
            elif stripped.startswith("continue"):
                explanation = "Skips to the next loop iteration."
            elif stripped.startswith("print("):
                explanation = "Displays output."
            elif "=" in stripped and "==" not in stripped:
                explanation = "May assign a value to a variable."
            else:
                explanation = (
                    "Executes a Python statement or expression; "
                    "its exact effect depends on the surrounding code."
                )

            report.append(
                f"- **Line {number}:** `{stripped[:180]}`  \n"
                f"  {explanation}"
            )

        if len(shown_lines) > 80:
            report.append(
                f"\n*Showing 80 of {len(shown_lines)} non-empty lines.*"
            )

    report.extend([
        "",
        "---",
        "**Note:** This explainer uses Python's syntax tree and simple "
        "rules. It does not execute your code, and its explanations "
        "are not a substitute for understanding the full program.",
    ])

    return "\n".join(report)


# -------------------- SESSION STATE --------------------

if "project_files" not in st.session_state:
    st.session_state.project_files = None

if "project_name" not in st.session_state:
    st.session_state.project_name = ""


# -------------------- UPLOAD PROJECT --------------------

st.header("📂 Upload your Python project")

uploaded_file = st.file_uploader(
    "Choose a ZIP file containing Python files",
    type=["zip"],
)

if st.button("🔎 Analyze Project", type="primary"):
    if uploaded_file is None:
        st.warning("Please upload a ZIP file first.")
    else:
        try:
            files = load_python_files(uploaded_file)
            st.session_state.project_files = files
            st.session_state.project_name = uploaded_file.name
            st.success(f"Loaded {len(files)} Python file(s).")
        except (ValueError, OSError, RuntimeError, zipfile.BadZipFile) as error:
            st.error(f"Could not analyze this ZIP: {error}")
            st.session_state.project_files = None
        except Exception as error:
            st.error(f"Unexpected error: {error}")
            st.session_state.project_files = None


# -------------------- RESULTS --------------------

files = st.session_state.project_files

if files:
    st.divider()
    st.header("📊 Project Overview")

    total_lines = sum(
        len(source.splitlines()) for source in files.values()
    )

    all_analyses = {
        path: analyze_python(source)
        for path, source in files.items()
    }

    total_functions = sum(
        len(result["functions"])
        for result in all_analyses.values()
    )

    total_classes = sum(
        len(result["classes"])
        for result in all_analyses.values()
    )

    total_issues = sum(
        len(result["issues"])
        for result in all_analyses.values()
    )

    syntax_errors = sum(
        result["syntax_error"] is not None
        for result in all_analyses.values()
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Python Files", len(files))
    col2.metric("Lines of Code", total_lines)
    col3.metric("Functions", total_functions)
    col4.metric("Classes", total_classes)

    st.caption(
        f"Quality issues flagged: {total_issues} · "
        f"Files with syntax errors: {syntax_errors}"
    )

    # -------------------- FILE EXPLORER --------------------

    st.divider()
    st.header("🗂️ Python File Explorer")

    selected_file = st.selectbox(
        "Select a Python file",
        options=list(files.keys()),
    )

    source = files[selected_file]
    analysis = all_analyses[selected_file]

    st.code(source, language="python")

    # -------------------- CODE EXPLAINER --------------------

    st.divider()
    st.header("💡 Code Explainer")
    st.write(
        "Get a beginner-friendly explanation of the selected file "
        "without an API key."
    )

    if st.button("✨ Explain This File"):
        st.session_state["explanation_file"] = selected_file
        st.session_state["explanation_text"] = explain_python(
            source, selected_file
        )

    if (
        st.session_state.get("explanation_file") == selected_file
        and st.session_state.get("explanation_text")
    ):
        st.markdown(st.session_state["explanation_text"])

    # -------------------- QUALITY REPORT --------------------

    st.divider()
    st.header("🛠️ Code Quality Report")

    if analysis["syntax_error"]:
        st.error(f"Syntax error: {analysis['syntax_error']}")
    elif analysis["issues"]:
        for issue in analysis["issues"]:
            st.warning(
                f"**{issue['type']}** — {issue['message']} "
                f"(line {issue['line']})"
            )
    else:
        st.success("No issues were detected by the basic checks.")

    with st.expander("View detected functions"):
        if analysis["functions"]:
            st.dataframe(
                analysis["functions"],
                use_container_width=True,
            )
        else:
            st.write("No functions found.")

    with st.expander("View detected classes"):
        if analysis["classes"]:
            st.dataframe(
                analysis["classes"],
                use_container_width=True,
            )
        else:
            st.write("No classes found.")

    with st.expander("View detected imports"):
        if analysis["imports"]:
            st.dataframe(
                analysis["imports"],
                use_container_width=True,
            )
        else:
            st.write("No imports found.")

    # -------------------- DEPENDENCY GRAPH --------------------

    st.divider()
    st.header("🕸️ Dependency Graph")
    st.write(
        "Arrows show recognized imports between Python files "
        "inside your project."
    )

    try:
        dependency_graph = build_graph(files)
        st.graphviz_chart(dependency_graph)
    except Exception as error:
        st.warning(f"Could not generate the dependency graph: {error}")

    # -------------------- JSON REPORT --------------------

    st.divider()
    st.header("📥 Download Report")

    report = {
        "project": st.session_state.project_name,
        "summary": {
            "python_files": len(files),
            "lines_of_code": total_lines,
            "functions": total_functions,
            "classes": total_classes,
            "quality_issues": total_issues,
            "syntax_errors": syntax_errors,
        },
        "files": all_analyses,
    }

    st.download_button(
        "Download JSON Report",
        data=json.dumps(report, indent=2),
        file_name="codexray_report.json",
        mime="application/json",
    )

else:
    st.info(
        "Upload a ZIP containing Python files and click "
        "**Analyze Project** to get started."
    )

st.divider()
st.caption(
    "CodeXray | Beginner-friendly Python project analysis. "
    "Uploaded code is analyzed in memory and is not intentionally executed."
)
