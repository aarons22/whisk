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

    # Check for venv module
    if ! python3 -m venv --help &> /dev/null; then
        print_error "Python venv module not found. On Debian/Ubuntu, install with:"
        print_error "  sudo apt install python3-venv"
        exit 1
    fi

    cd "$WHISK_DIR"

    # Create virtual environment
    print_status "Creating virtual environment..."
    python3 -m venv venv || {
        print_error "Failed to create virtual environment"
        exit 1
    }

    # Activate virtual environment and install dependencies
    print_status "Installing dependencies in virtual environment..."
    source venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -e . || {
        print_error "Failed to install dependencies"
        exit 1
    }
    deactivate
}

# Create symlink
create_symlink() {
    print_status "Creating symlink..."

    # Create user bin directory if needed
    mkdir -p "$HOME/.local/bin"

    # Remove existing symlink/file if it exists
    if [[ -e "$HOME/.local/bin/whisk" ]]; then
        rm -f "$HOME/.local/bin/whisk"
        print_status "Removed existing whisk command"
    fi

    # Create new symlink
    ln -sf "$WHISK_DIR/bin/whisk" "$HOME/.local/bin/whisk"
    print_status "Created symlink: $HOME/.local/bin/whisk -> $WHISK_DIR/bin/whisk"

    # Try system install as well
    if [[ -w "$INSTALL_DIR" ]] && command -v sudo &> /dev/null; then
        sudo ln -sf "$WHISK_DIR/bin/whisk" "$INSTALL_DIR/whisk" 2>/dev/null || true
    fi

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

    # Create launcher script with hardcoded path
    cat > "$WHISK_DIR/bin/whisk" <<EOF
#!/bin/bash
# Whisk launcher script

# Hardcode the whisk directory path to avoid path resolution issues
WHISK_DIR="$WHISK_DIR"
# Path to the virtual environment Python
VENV_PYTHON="\$WHISK_DIR/venv/bin/python"

# Check if virtual environment exists
if [[ ! -f "\$VENV_PYTHON" ]]; then
    echo "Error: Virtual environment not found at \$VENV_PYTHON"
    echo "WHISK_DIR is set to: \$WHISK_DIR"
    echo "Contents of \$WHISK_DIR:"
    ls -la "\$WHISK_DIR" 2>/dev/null || echo "Directory does not exist"
    echo "Try reinstalling whisk with:"
    echo "  curl -sSL https://raw.githubusercontent.com/aarons22/whisk/main/install.sh | bash"
    exit 1
fi

# Change to whisk directory and run
cd "\$WHISK_DIR"
exec "\$VENV_PYTHON" -m whisk "\$@"
EOF
    chmod +x "$WHISK_DIR/bin/whisk"

    # Show what was actually written to the launcher script
    print_status "Created launcher script contents:"
    cat "$WHISK_DIR/bin/whisk"

    # Create symlink
    create_symlink

    # Verify installation
    print_status "Verifying installation..."
    print_status "Installation directory: $WHISK_DIR"

    if [[ -f "$WHISK_DIR/venv/bin/python" ]]; then
        print_success "Virtual environment created successfully"
    else
        print_error "Virtual environment missing at $WHISK_DIR/venv/bin/python"
        exit 1
    fi

    if [[ -f "$WHISK_DIR/bin/whisk" ]]; then
        print_success "Launcher script created successfully"
        print_status "Launcher script location: $WHISK_DIR/bin/whisk"
    else
        print_error "Launcher script missing at $WHISK_DIR/bin/whisk"
        exit 1
    fi

    if [[ -f "$HOME/.local/bin/whisk" ]]; then
        print_success "Symlink created successfully"
        print_status "Symlink: $HOME/.local/bin/whisk -> $(readlink "$HOME/.local/bin/whisk")"

        # Test the launcher script
        print_status "Testing launcher script..."
        if "$HOME/.local/bin/whisk" --version >/dev/null 2>&1; then
            print_success "Launcher script working correctly"
        else
            print_warning "Launcher script test failed - check the output above"
        fi
    else
        print_warning "Symlink not found at $HOME/.local/bin/whisk"
    fi

    print_success "Whisk installed successfully!"
    echo
    print_status "Installation uses a virtual environment in $WHISK_DIR/venv"
    print_status "This avoids conflicts with system Python packages"
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