#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORTABLE_DIR="$SCRIPT_DIR/portable"
DATA_DIR="$SCRIPT_DIR/data"

echo "========================================"
echo "  Hermes Portable - Setup"
echo "========================================"
echo ""

# Detect OS
OS="$(uname -s)"
ARCH="$(uname -m)"
case "$OS" in
    Darwin)  PLATFORM="macos" ;;
    Linux)   PLATFORM="linux" ;;
    *)       echo "ERROR: Unsupported OS: $OS"; exit 1 ;;
esac

case "$ARCH" in
    x86_64|amd64)  ARCH_SUFFIX="x86_64" ;;
    arm64|aarch64) ARCH_SUFFIX="aarch64" ;;
    *)             echo "ERROR: Unsupported architecture: $ARCH"; exit 1 ;;
esac

echo "Detected: $PLATFORM ($ARCH_SUFFIX)"

# Create directories
mkdir -p "$PORTABLE_DIR" "$DATA_DIR"/{sessions,skills,logs,memories,cron,plugins}

# Step 1: Download uv
echo ""
echo "[1/5] Downloading uv package manager..."
UV_PATH="$PORTABLE_DIR/uv"
if [ ! -f "$UV_PATH" ]; then
    if [ "$PLATFORM" = "macos" ]; then
        UV_URL="https://github.com/astral-sh/uv/releases/latest/download/uv-${ARCH_SUFFIX}-apple-darwin.tar.gz"
    else
        UV_URL="https://github.com/astral-sh/uv/releases/latest/download/uv-${ARCH_SUFFIX}-unknown-linux-gnu.tar.gz"
    fi
    
    curl -L "$UV_URL" -o "$PORTABLE_DIR/uv.tar.gz"
    tar -xzf "$PORTABLE_DIR/uv.tar.gz" -C "$PORTABLE_DIR/"
    # uv tarball extracts to a directory, find the binary
    find "$PORTABLE_DIR" -name "uv" -type f -path "*/bin/*" -exec mv {} "$UV_PATH" \;
    chmod +x "$UV_PATH"
    rm -f "$PORTABLE_DIR/uv.tar.gz"
    # Clean up extracted directory
    find "$PORTABLE_DIR" -maxdepth 1 -type d -name "uv-*" -exec rm -rf {} \; 2>/dev/null || true
    echo "uv downloaded successfully."
else
    echo "uv already exists, skipping."
fi

# Step 2: Install Python
echo ""
echo "[2/5] Installing portable Python..."
PYTHON_DIR="$PORTABLE_DIR/python"
UV_PYTHON_INSTALL_DIR="$PYTHON_DIR" "$UV_PATH" python install 3.12 --install-dir "$PYTHON_DIR" || true
echo "Python installed."

# Find the installed Python
PYTHON_BIN=$(find "$PYTHON_DIR" -name "python3.12" -type f 2>/dev/null | head -1)
if [ -z "$PYTHON_BIN" ]; then
    PYTHON_BIN=$(find "$PYTHON_DIR" -name "python3" -type f 2>/dev/null | head -1)
fi
if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: Could not find Python binary in $PYTHON_DIR"
    exit 1
fi
echo "Found Python: $PYTHON_BIN"

# Step 3: Clone hermes-agent
echo ""
echo "[3/5] Downloading hermes-agent..."
HERMES_SRC="$PORTABLE_DIR/hermes-agent"
if [ ! -d "$HERMES_SRC" ]; then
    git clone --depth 1 https://github.com/NousResearch/hermes-agent.git "$HERMES_SRC"
    echo "hermes-agent cloned successfully."
else
    echo "hermes-agent already exists, updating..."
    cd "$HERMES_SRC"
    git pull --ff-only 2>/dev/null || echo "Update skipped (local changes or offline)."
    cd "$SCRIPT_DIR"
fi

# Step 4: Create virtual environment and install dependencies
echo ""
echo "[4/5] Creating virtual environment and installing dependencies..."
VENV_DIR="$PORTABLE_DIR/venv"
"$UV_PATH" venv "$VENV_DIR" --python "$PYTHON_BIN"

# Install hermes with extras
echo "Installing hermes-agent (this may take a few minutes)..."
if "$UV_PATH" pip install -e "$HERMES_SRC[all]" --python "$VENV_DIR/bin/python" 2>/dev/null; then
    echo "All extras installed."
else
    echo "Warning: 'all' extras failed, trying core + common extras..."
    "$UV_PATH" pip install -e "$HERMES_SRC[cron,messaging,cli,mcp]" --python "$VENV_DIR/bin/python"
fi
echo "Dependencies installed successfully."

# Step 5: Create default config
echo ""
echo "[5/5] Setting up configuration..."
if [ ! -f "$DATA_DIR/.env" ]; then
    cat > "$DATA_DIR/.env" << 'EOF'
# Hermes Portable - Environment Variables
# Add your API keys here

# OPENROUTER_API_KEY=your_key_here
# ANTHROPIC_API_KEY=your_key_here
# OPENAI_API_KEY=your_key_here
EOF
    echo "Created default .env file."
fi

if [ ! -f "$DATA_DIR/config.yaml" ]; then
    cat > "$DATA_DIR/config.yaml" << 'EOF'
# Hermes Portable Configuration
model:
  default: "openrouter/anthropic/claude-sonnet-4"
  provider: "openrouter"

terminal:
  backend: "local"
  timeout: 180

compression:
  enabled: true
  threshold: 0.50
  target_ratio: 0.20

display:
  skin: "default"
  tool_progress: true
  show_cost: true
EOF
    echo "Created default config.yaml."
fi

echo ""
echo "========================================"
echo "  Setup Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Edit data/.env to add your API keys"
echo "  2. Run ./start.sh to launch Hermes"
echo ""
