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
	uv run client

# Bonus: Quickly compile and run your C backend!
server:
	@echo "Compiling the C server..."
	gcc app_server/*.c -o app_server/server

run-server:
	@echo "Starting PolyChat Server..."
	./app_server/server

clean:
	@echo "Cleaning up compiled files..."
	rm -f ./app_server/server
