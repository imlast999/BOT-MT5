#!/usr/bin/env python3
"""
MT5 Discord Trading Bot Setup Script
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def check_python_version():
    """Check if Python version is 3.9 or higher"""
    if sys.version_info < (3, 9):
        print("❌ Python 3.9 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version}")
    return True

def install_requirements():
    """Install required packages"""
    print("📦 Installing required packages...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Requirements installed successfully")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install requirements")
        return False

def setup_env_file():
    """Setup environment file"""
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if env_file.exists():
        print("⚠️  .env file already exists")
        response = input("Do you want to overwrite it? (y/N): ")
        if response.lower() != 'y':
            print("📝 Please configure .env manually")
            return True
    
    if env_example.exists():
        shutil.copy(env_example, env_file)
        print("✅ Created .env file from template")
        print("📝 Please edit .env file with your configuration")
        return True
    else:
        print("❌ .env.example not found")
        return False

def check_mt5():
    """Check if MT5 is available"""
    try:
        import MetaTrader5 as mt5
        print("✅ MetaTrader5 package available")
        return True
    except ImportError:
        print("❌ MetaTrader5 package not found")
        print("💡 Install with: pip install MetaTrader5")
        return False

def main():
    """Main setup function"""
    print("🚀 MT5 Discord Trading Bot Setup")
    print("=" * 40)
    
    # Check Python version
    if not check_python_version():
        return False
    
    # Install requirements
    if not install_requirements():
        return False
    
    # Check MT5
    if not check_mt5():
        print("⚠️  MT5 package missing, but continuing...")
    
    # Setup environment file
    if not setup_env_file():
        return False
    
    print("\n🎉 Setup completed!")
    print("\n📋 Next steps:")
    print("1. Edit .env file with your Discord bot token and settings")
    print("2. Install and configure MetaTrader 5")
    print("3. Create a #signals channel in your Discord server")
    print("4. Run: python bot.py")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)