# Contributing to AI Knowledge Bench

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers and help them get started
- Focus on constructive feedback
- Assume good intentions

## Getting Started

### Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/IGabriel/ai-knowledge-bench.git
   cd ai-knowledge-bench
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -e ".[dev]"
   ```

3. **Set up pre-commit hooks** (optional):
   ```bash
   pip install pre-commit
   pre-commit install
   ```

4. **Start services**:
   ```bash
   ./start.sh
   ```

### Development Workflow

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**:
   - Write clean, readable code
   - Follow existing code style
   - Add docstrings to functions/classes
   - Update documentation if needed

3. **Test your changes**:
   ```bash
   # Run linters
   black .
   ruff check .
   
   # Run tests (if available)
   pytest
   ```

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Brief description of changes"
   ```

5. **Push and create PR**:
   ```bash
   git push origin feature/your-feature-name
   ```
   Then create a Pull Request on GitHub.

## Code Style

### Python

- Follow PEP 8 style guide
- Use type hints where appropriate
- Maximum line length: 100 characters
- Use Black for formatting
- Use Ruff for linting

Example:
```python
def process_document(
    document_id: str,
    chunk_size: int = 512,
    chunk_overlap: int = 128
) -> List[Chunk]:
    """
    Process a document into chunks.
    
    Args:
        document_id: UUID of the document
        chunk_size: Maximum characters per chunk
        chunk_overlap: Overlap between chunks
        
    Returns:
        List of Chunk objects
    """
    # Implementation here
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def function_name(param1: str, param2: int) -> bool:
    """
    Short description of the function.
    
    Longer description if needed, explaining the purpose,
    behavior, and any important details.
    
    Args:
        param1: Description of param1
        param2: Description of param2
        
    Returns:
        Description of return value
        
    Raises:
        ValueError: Description of when this is raised
    """
```

## Testing

### Writing Tests

- Place tests in `tests/` directory
- Use pytest for testing
- Aim for good coverage of critical paths
- Mock external dependencies (DB, Kafka, vLLM)

Example:
```python
import pytest
from packages.core.chunking import chunk_text

def test_chunk_text_basic():
    text = "This is a test. " * 100
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=20, source_ref="page=1")
    
    assert len(chunks) > 0
    assert all(len(chunk[0]) <= 120 for chunk in chunks)  # Allow some overflow
    assert all(chunk[1] == "page=1" for chunk in chunks)
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_chunking.py

# Run with coverage
pytest --cov=packages --cov-report=html
```

## Documentation

### When to Update Docs

- Adding new features
- Changing APIs or configuration
- Fixing bugs that affect usage
- Improving existing explanations

### Documentation Files

- `README.md`: User-facing documentation, quick start, usage
- `docs/design.md`: Architecture and design decisions
- Code docstrings: Function/class documentation
- API docs: Auto-generated from FastAPI

## Areas for Contribution

### High Priority

- [ ] Add comprehensive test suite
- [ ] Improve error handling and validation
- [ ] Add authentication and authorization
- [ ] Performance optimizations
- [ ] Better logging and monitoring

### Features

- [ ] More document loaders (CSV, JSON, etc.)
- [ ] Advanced chunking strategies (semantic, hierarchical)
- [ ] Support for more embedding models
- [ ] Query expansion and reformulation
- [ ] Result re-ranking with cross-encoder
- [ ] Multi-turn conversational context

### Documentation

- [ ] Video tutorials
- [ ] More examples and use cases
- [ ] Troubleshooting guides
- [ ] Performance tuning guide
- [ ] Deployment guide (AWS, GCP, Azure)

### DevOps

- [ ] CI/CD pipeline
- [ ] Kubernetes deployment
- [ ] Terraform/CloudFormation templates
- [ ] Monitoring dashboards (Grafana)
- [ ] Backup and restore procedures

## Pull Request Guidelines

### Before Submitting

- [ ] Code follows style guidelines
- [ ] Tests pass (if available)
- [ ] Documentation updated
- [ ] Commit messages are clear
- [ ] PR description explains changes

### PR Description Template

```markdown
## Description
Brief description of what this PR does.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
How has this been tested?

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests added/updated
```

## Release Process

(For maintainers)

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create git tag: `git tag v0.x.0`
4. Push tag: `git push origin v0.x.0`
5. Create GitHub release with notes

## Questions?

- Open an issue for bugs or feature requests
- Start a discussion for questions or ideas
- Reach out to maintainers for guidance

Thank you for contributing! 🎉
