#!/bin/bash

# Start Django development server

echo "Starting Django backend server..."
echo "API will be available at http://localhost:8000"
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run migrations
python manage.py migrate

# Start server
python manage.py runserver

