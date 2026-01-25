#!/bin/bash

# Whisk Installer Script
# Downloads and installs Whisk grocery list sync tool

set -e

WHISK_DIR="$HOME/.whisk"
WHISK_REPO="https://github.com/aarons22/whisk.git"
INSTALL_DIR="/usr/local/bin"
VERSION="latest"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "Don't run this script as root"
   exit 1
fi

# Check for Python 3.10+
check_python() {
    if command -v python3 &> /dev/null; then
        python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        python_major=$(echo $python_version | cut -d. -f1)
        python_minor=$(echo $python_version | cut -d. -f2)

        if [[ $python_major -eq 3 && $python_minor -ge 10 ]]; then
            print_success "Python $python_version found"
            return 0
        else
            print_error "Python 3.10+ required, found $python_version"
            return 1
        fi
    else
        print_error "Python 3 not found. Please install Python 3.10+ first"
        return 1
    fi
}

# Install Python dependencies
install_dependencies() {
    print_status "Installing Python dependencies..."

    if ! python3 -m pip --version &> /dev/null; then
        print_error "pip not found. Please install pip first"
        exit 1
    fi

    cd "$WHISK_DIR"
    python3 -m pip install --user -e . || {
        print_error "Failed to install dependencies"
        exit 1
    }
}

# Create symlink
create_symlink() {
    print_status "Creating symlink..."

    # Try system install first
    if [[ -w "$INSTALL_DIR" ]]; then
        sudo ln -sf "$WHISK_DIR/bin/whisk" "$INSTALL_DIR/whisk" 2>/dev/null || true
    fi

    # Create user bin directory if needed
    mkdir -p "$HOME/.local/bin"
    ln -sf "$WHISK_DIR/bin/whisk" "$HOME/.local/bin/whisk"

    # Add to PATH if not already there
    add_to_path "$HOME/.local/bin"
}

add_to_path() {
    local bin_dir="$1"
    local shell_rc=""

    # Detect shell
    if [[ $SHELL == *"zsh"* ]]; then
        shell_rc="$HOME/.zshrc"
    elif [[ $SHELL == *"bash"* ]]; then
        shell_rc="$HOME/.bashrc"
    fi

    if [[ -n "$shell_rc" ]]; then
        if ! grep -q "$bin_dir" "$shell_rc" 2>/dev/null; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$shell_rc"
            print_warning "Added $bin_dir to PATH in $shell_rc"
            print_warning "Run 'source $shell_rc' or restart your terminal"
        fi
    fi
}

# Main installation
main() {
    echo "🥄 Whisk Installer"
    echo "=================="
    echo

    # Check prerequisites
    check_python || exit 1

    # Check for git
    if ! command -v git &> /dev/null; then
        print_error "Git is required but not installed"
        exit 1
    fi

    # Remove existing installation
    if [[ -d "$WHISK_DIR" ]]; then
        print_status "Removing existing installation..."
        rm -rf "$WHISK_DIR"
    fi

    # Clone repository
    print_status "Downloading Whisk..."
    git clone "$WHISK_REPO" "$WHISK_DIR" || {
        print_error "Failed to download Whisk"
        exit 1
    }

    # Install dependencies
    install_dependencies

    # Create launcher script
    mkdir -p "$WHISK_DIR/bin"
    cat > "$WHISK_DIR/bin/whisk" << 'EOF'
#!/bin/bash
# Whisk launcher script
cd "$(dirname "$0")/.."
exec python3 -m whisk "$@"
EOF
    chmod +x "$WHISK_DIR/bin/whisk"

    # Create symlink
    create_symlink

    print_success "Whisk installed successfully!"
    echo
    echo "Quick Start:"
    echo "  whisk setup     # Run interactive setup"
    echo "  whisk sync      # One-time sync"
    echo "  whisk start     # Start background daemon"
    echo
    echo "If 'whisk' command not found, add ~/.local/bin to your PATH:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
}

main "$@"