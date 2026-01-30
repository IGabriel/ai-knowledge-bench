#!/bin/bash
# Validation script to check repository structure and setup

set -e

echo "🔍 AI Knowledge Bench - Repository Validation"
echo "=============================================="
echo ""

# Check directory structure
echo "📁 Checking directory structure..."
required_dirs=(
    "apps/web_api"
    "apps/worker_ingest"
    "packages/core"
    "packages/eval"
    "deploy"
    "docs"
    "eval"
    "alembic"
    "tests"
)

all_exist=true
for dir in "${required_dirs[@]}"; do
    if [ -d "$dir" ]; then
        echo "  ✅ $dir"
    else
        echo "  ❌ $dir (missing)"
        all_exist=false
    fi
done

echo ""

# Check key files
echo "📄 Checking key files..."
required_files=(
    "README.md"
    "requirements.txt"
    "pyproject.toml"
    ".env.example"
    "alembic.ini"
    "deploy/docker-compose.yml"
    "eval/golden_set_v1.jsonl"
    "Makefile"
    "start.sh"
)

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ $file"
    else
        echo "  ❌ $file (missing)"
        all_exist=false
    fi
done

echo ""

# Check Python files
echo "🐍 Checking Python modules..."
python_modules=(
    "packages/core/config.py"
    "packages/core/database.py"
    "packages/core/loaders.py"
    "packages/core/chunking.py"
    "packages/core/embeddings.py"
    "packages/core/retrieval.py"
    "packages/core/kafka_utils.py"
    "packages/core/vllm_client.py"
    "apps/web_api/main.py"
    "apps/worker_ingest/main.py"
    "packages/eval/run.py"
)

for module in "${python_modules[@]}"; do
    if [ -f "$module" ]; then
        echo "  ✅ $module"
    else
        echo "  ❌ $module (missing)"
        all_exist=false
    fi
done

echo ""

# Check Docker setup
echo "🐳 Checking Docker configuration..."
if command -v docker &> /dev/null; then
    echo "  ✅ Docker is installed"
    if docker ps &> /dev/null; then
        echo "  ✅ Docker is running"
    else
        echo "  ⚠️  Docker is installed but not running"
    fi
else
    echo "  ⚠️  Docker is not installed (required for Docker Compose setup)"
fi

if command -v docker-compose &> /dev/null || docker compose version &> /dev/null 2>&1; then
    echo "  ✅ Docker Compose is available"
else
    echo "  ⚠️  Docker Compose is not available"
fi

echo ""

# Summary
echo "="*60
if [ "$all_exist" = true ]; then
    echo "✅ All required files and directories are present!"
    echo ""
    echo "📚 Next Steps:"
    echo "   1. Install dependencies:"
    echo "      pip install -r requirements.txt"
    echo ""
    echo "   2. Start the services:"
    echo "      ./start.sh"
    echo "      OR"
    echo "      make dev"
    echo ""
    echo "   3. Set up vLLM (see README.md for instructions)"
    echo ""
    echo "   4. Access the UI at http://localhost:8080"
    echo ""
    echo "For detailed instructions, see README.md"
else
    echo "❌ Some files or directories are missing"
    echo "   Please check the errors above"
fi
echo "="*60
