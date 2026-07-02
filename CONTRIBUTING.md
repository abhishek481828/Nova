# Contributing to Nova

Thank you for your interest in contributing to Nova!

---

## Code of Conduct
By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Development Process

1.  **Fork the Repository**: Create a personal fork of the project on GitHub.
2.  **Clone & Configure**:
    ```bash
    git clone https://github.com/your-username/Nova.git
    cd Nova
    nix-shell # Or configure venv on standard Linux systems
    ```
3.  **Create a Branch**: Use a descriptive branch name:
    ```bash
    git checkout -b feature/your-awesome-feature
    ```
4.  **Run Tests**: Ensure all tests are passing before opening a pull request:
    ```bash
    nix-shell --run ".venv/bin/python -m pytest"
    ```
5.  **Open a Pull Request**: Submit your pull request to the main branch for review.
