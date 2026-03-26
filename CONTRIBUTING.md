# Contributing to Chaeshin

[한국어](docs/ko/CONTRIBUTING.md)

Thank you for your interest in contributing to Chaeshin!

## Getting Started

### Development Setup

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras        # recommended
# or: pip install -e ".[dev]"
```

### Running Tests

```bash
make test          # Full test suite
make test-unit     # Unit tests only
make lint          # Linting
```

## How to Contribute

### Opening Issues

- **Bug reports**: Include reproduction steps
- **Feature requests**: Describe the use case and expected behavior
- **Questions**: Use the Discussion tab

### Pull Requests

1. Create an issue first, or comment on an existing issue to indicate your intent
2. Fork and create a branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Commit your changes:
   ```bash
   git commit -m "feat: add new tool type support"
   ```
4. Add tests and make sure they pass:
   ```bash
   make test
   ```
5. Open a PR

### Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Adding/modifying tests
- `refactor:` Code refactoring
- `chore:` Build/config changes

### Examples

```
feat: add VectorDB adapter for CaseStore
fix: prevent infinite loop in graph executor
docs: add health detective example
test: add edge condition evaluation tests
```

## Code Style

- Python 3.10+
- Use type hints
- Docstrings in English or Korean (mixing is fine)
- Function/class names in English; comments/docs can be in Korean

## Good Areas to Contribute

### Beginner-Friendly (good first issue)

- Add new domain examples (health, education, coding, etc.)
- Documentation translation (Korean ↔ English)
- Expand test coverage

### Intermediate

- CaseStore VectorDB adapters (Weaviate, Pinecone, ChromaDB)
- New condition evaluation operators
- React UI components

### Advanced

- LLM-based graph replanning optimization
- Distributed graph execution (parallel node execution)
- Benchmark framework

## Code of Conduct

All participants should treat each other with respect and maintain constructive dialogue. Discrimination, harassment, and derogatory remarks are not tolerated.

## Questions?

- GitHub Issues
- GitHub Discussions
- contact@geohyeon.com
