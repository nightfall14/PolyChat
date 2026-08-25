.PHONY: all setup run server run-server clean

# This is the default target that runs when someone just types 'make'
all: run

# 1. Checks if 'uv' is installed, and syncs dependencies
setup:
	@echo "Checking dependencies..."
	@command -v uv >/dev/null 2>&1 || { echo >&2 "Error: 'uv' is not installed. Please install it via: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
	uv sync

# 2. Runs the Textual UI client
run: setup
	@echo "Starting PolyChat Client..."
	uv run client 192.168.43.141 9034

# Bonus: Quickly compile and run your C backend!
server:
	@echo "Compiling the C server..."
	gcc app_server/*.c -o app_server/server

run-server:
	@echo "Starting PolyChat Server..."
	./app_server/server

update:
	@echo "🔍 Checking for updates..."
	@git fetch
	@if [ "$$(git rev-parse HEAD)" = "$$(git rev-parse @{u})" ]; then \
		echo "✨ You are already on the latest version!"; \
	else \
		echo "📥 New version found! Pulling changes..."; \
		git pull; \
		echo "📦 Syncing dependencies with uv..."; \
		uv sync; \
		echo "✅ Update complete!"; \
	fi

clean:
	@echo "Cleaning up compiled files..."
	rm -f ./app_server/server
