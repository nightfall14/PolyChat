all: server

server: server.c
	gcc -o server server.c -Wall -Wextra

run-server: server
	./server

run-client:
	cd src/polychat && uv run client.py

test:
	cd src/polychat && uv run test.py

clean:
	rm -f server
