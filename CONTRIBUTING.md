# Contributing to YT Merge Pro

Thanks for your interest in contributing! Here's how you can help.

## Getting Started

1. **Fork** the repository
2. **Clone** your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/yt-merge-pro.git
   cd yt-merge-pro
   ```
3. **Create a branch** for your feature or fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Development Guidelines

- **Code style** — Follow PEP 8. Use meaningful variable names and add docstrings to functions/classes.
- **Modularity** — Keep the separation of concerns: `engine.py` for logic, `gui/` for interface, `utils.py` for helpers.
- **Thread safety** — Any state shared between the GUI and engine threads must use locks or `self.after()`.
- **No new dependencies** unless absolutely necessary. Discuss in an issue first.

## Making Changes

1. Make your changes in small, focused commits
2. Test the application manually — verify the GUI launches and the pipeline works
3. Run a quick import check:
   ```bash
   python -c "from yt_merge.engine import MergeEngine; print('OK')"
   ```

## Submitting a Pull Request

1. **Push** your branch to your fork
2. Open a **Pull Request** against the `main` branch
3. Describe what you changed and why
4. Link any related issues

## Reporting Bugs

Open an issue with:
- Steps to reproduce
- Expected behavior
- Actual behavior
- Your OS and Python version
- Full error traceback (if any)

## Feature Requests

Open an issue with the `enhancement` label. Describe the feature, why it's useful, and any implementation ideas you have.

---

Thank you for helping make YT Merge Pro better!
