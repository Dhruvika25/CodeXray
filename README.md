# CodeXray
# 🔍 CodeXray — Understand Any Python Project Visually

CodeXray is a beginner-friendly Python project analyzer built with Streamlit. It helps developers explore Python projects, understand their structure, identify basic code quality issues, and visualize dependencies.

## ✨ Features

- 📂 **Project Upload:** Upload a ZIP file containing Python source files.
- 📊 **Project Overview:** View Python file count, lines of code, functions, and classes.
- 🗂️ **Python File Explorer:** Select and inspect individual Python files.
- 💡 **Code Explainer:** Get rule-based explanations of functions, classes, imports, and common Python statements.
- 🛠️ **Code Quality Checks:** Flag long functions, long lines, possible unused imports, and syntax errors.
- 🕸️ **Dependency Graph:** Visualize recognized imports between project files.
- 📥 **JSON Report:** Download a report containing analysis results.

## 🧰 Tech Stack

- Python
- Streamlit
- Python AST (Abstract Syntax Tree)
- Graphviz

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd CodeXray
```

Replace `YOUR_GITHUB_REPOSITORY_URL` with your repository's actual Git URL.

### 2. Create a virtual environment (optional)

```bash
python -m venv .venv
```

Activate it on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

Graphviz must also be installed on your computer and available on your system PATH if you want to render dependency graphs locally.

### 4. Run the application

```bash
python -m streamlit run app.py
```

Open the local URL shown in your terminal, usually `http://localhost:8501`.

## 📝 How to Use

1. Start CodeXray.
2. Upload a ZIP file containing a Python project.
3. Click **Analyze Project**.
4. Explore the project's files and code quality results.
5. Click **Explain This File** to view the rule-based explanation.
6. Explore the dependency graph and download the JSON report.

## ⚠️ Limitations

- The Code Explainer uses predefined rules, not a large language model. It does not provide fully conversational AI explanations.
- Unused-import detection is heuristic and may produce false positives.
- Dependency graphs show only imports that CodeXray can recognize between files in the uploaded project.
- CodeXray analyzes source files without intentionally executing them. However, ZIP parsing and source analysis should not be treated as a security sandbox.

## 🔮 Future Improvements

- AI-powered explanations
- More advanced static analysis
- Improved dependency visualization
- Online deployment
- More detailed project reports

## 👩‍💻 Author

Created as a Python project to make code exploration easier for beginners.

---

⭐ If you find this project useful, consider giving the repository a star!
