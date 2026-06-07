#!/bin/bash
set -e

echo "🚀 Starting JoBins Agent Setup..."

# 1. Create .env if missing
if [ ! -f .env ]; then
    echo "📄 Creating .env file from template..."
    cp .env.example .env
fi

# 2. Check and prompt for GROQ API KEY
if grep -q "your_api_key_here" .env || ! grep -q "GROQ_API_KEY=" .env; then
    echo ""
    echo "🔑 Groq API Key is missing or set to default."
    echo "Get your free API key at: https://console.groq.com/keys"
    read -p "Please paste your GROQ_API_KEY: " api_key
    echo ""
    # Inject it into the .env file cleanly
    sed -i "s|GROQ_API_KEY=.*|GROQ_API_KEY=$api_key|" .env
    echo "✅ API Key successfully saved to .env!"
fi

# 3. Check for Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker isn't installed or running! Please install Docker to continue."
    exit 1
fi

echo "🐳 Building Docker container..."
# Build quietly to reduce terminal clutter
docker compose build -q

# 4. Run the container
if [ -z "$1" ]; then
    echo "ℹ️ No task provided. Starting in interactive mode..."
    echo "========================================================="
    docker compose run --rm agent
else
    echo "🎯 Running Task: $1"
    echo "========================================================="
    docker compose run --rm agent --task "$1"
fi
