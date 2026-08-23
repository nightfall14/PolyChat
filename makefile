all: server

server: ./app_server/server.c ./app_server/network.c ./app_server/protocol.c
	gcc -o server ./app_server/server.c ./app_server/network.c ./app_server/protocol.c -Wall -Wextra

run-server: server
	./app_server/server.c 

run-client:
	cd src/polychat && uv run client.py

test:
	cd src/polychat && uv run test.py

clean:
	rm -f server
