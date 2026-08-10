all: server

server: server.c
	gcc -o server server.c -Wall -Wextra

clean:
	rm -f server
