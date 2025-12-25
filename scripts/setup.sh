#!/bin/bash

# Setup script for CarbonLens

set -e

echo "🌍 CarbonLens Setup Script"
echo "=========================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ Dependencies installed"

# Create .env file if it doesn't exist
echo ""
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "✓ .env file created (please update with your API keys)"
else
    echo "✓ .env file already exists"
fi

# Create data directory
echo ""
echo "Creating data directory..."
mkdir -p data
echo "✓ Data directory created"

# Download OWID data
echo ""
read -p "Download OWID CO2 data now? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Downloading OWID CO2 data..."
    python scripts/download_owid_data.py
fi

# Django setup
echo ""
echo "Running Django migrations..."
python manage.py migrate
echo "✓ Django migrations completed"

# Create superuser (optional)
echo ""
read -p "Create Django superuser? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    python manage.py createsuperuser
fi

echo ""
echo "=========================="
echo "✓ Setup complete!"
echo ""
echo "To start the application:"
echo "  1. Activate virtual environment: source venv/bin/activate"
echo "  2. Start Django: python manage.py runserver"
echo ""
echo "Or use Docker:"
echo "  docker-compose up"
echo ""

