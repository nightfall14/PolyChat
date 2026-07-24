/*
** pollserver.c -- a cheezy multiperson chat server
*/

#include <arpa/inet.h>
#include <netdb.h>
#include <netinet/in.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

#define PORT "9034" // Port we're listening on

int sendall(int s, void *buf, uint32_t *len) {
  int total = 0;        // Total bytes sent
  int bytesleft = *len; // Bytes left to send
  int n;

  while (total < *len) {
    n = send(s, buf + total, bytesleft, 0);

    if (n == -1) {
      break;
    }

    total += n;
    bytesleft -= n;
  }

  *len = total; // Return number of bytes actually sent

  return (n == -1) ? -1 : 0; // -1 on failure, 0 on success
}

int recv_exact(int s, void *buf, uint32_t n) {
  int total = 0;
  int bytesleft = n;
  int rcvd;
  while (total < n) {
    int rcvd = recv(s, buf + total, bytesleft, 0);

    if (rcvd == -1 || rcvd == 0) {
      break;
    }
    total += rcvd;
    bytesleft -= rcvd;
  }
  n = total;

  return (rcvd == -1) ? -1 : 0;
}

void send_frame(int s, uint8_t type, void *payload, uint32_t len) {

  uint8_t header[5];
  uint32_t head_len = 5;
  header[0] = type;
  uint32_t net_len = htonl(len);
  memcpy(header + 1, &(net_len), sizeof(net_len));
  printf("sendall-1\n");
  if (sendall(s, header, &(head_len)) == -1) {
    perror("send\n");
  }
  printf("sendall-2\n");
  if (sendall(s, payload, &(len)) == -1) {
    perror("send\n");
  }
}
/*
 * Convert socket to IP address string.
 * addr: struct sockaddr_in or struct sockaddr_in6
 */
const char *inet_ntop2(void *addr, char *buf, size_t size) {
  struct sockaddr_storage *sas = addr;
  struct sockaddr_in *sa4;
  struct sockaddr_in6 *sa6;
  void *src;

  switch (sas->ss_family) {
  case AF_INET:
    sa4 = addr;
    src = &(sa4->sin_addr);
    break;
  case AF_INET6:
    sa6 = addr;
    src = &(sa6->sin6_addr);
    break;
  default:
    return NULL;
  }

  return inet_ntop(sas->ss_family, src, buf, size);
}

/*
 * Return a listening socket.
 */
int get_listener_socket(void) {
  int listener; // Listening socket descriptor
  int yes = 1;  // For setsockopt() SO_REUSEADDR, below
  int rv;
  struct addrinfo hints, *ai, *p;

  // Get us a socket and bind it
  memset(&hints, 0, sizeof hints);
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_STREAM;
  hints.ai_flags = AI_PASSIVE;

  if ((rv = getaddrinfo(NULL, PORT, &hints, &ai)) != 0) {
    fprintf(stderr, "pollserver: %s\n", gai_strerror(rv));
    exit(1);
  }

  for (p = ai; p != NULL; p = p->ai_next) {
    listener = socket(p->ai_family, p->ai_socktype, p->ai_protocol);
    if (listener < 0) {
      continue;
    }

    // Lose the pesky "address already in use" error message
    setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(int));

    if (bind(listener, p->ai_addr, p->ai_addrlen) < 0) {
      close(listener);
      continue;
    }
    break;
  }

  // If we got here, it means we didn't get bound
  if (p == NULL) {
    return -1;
  }

  freeaddrinfo(ai); // All done with this

  // Listen
  if (listen(listener, 10) == -1) {
    return -1;
  }

  return listener;
}

/*
 * Add a new file descriptor to the set.
 */
void add_to_pfds(struct pollfd **pfds, int newfd, int *fd_count, int *fd_size) {
  // If we don't have room, add more space in the pfds array
  if (*fd_count == *fd_size) {
    *fd_size *= 2; // Double it
    *pfds = realloc(*pfds, sizeof(**pfds) * (*fd_size));
  }

  (*pfds)[*fd_count].fd = newfd;
  (*pfds)[*fd_count].events = POLLIN; // Check ready-to-read
  (*pfds)[*fd_count].revents = 0;

  (*fd_count)++;
}

/*
 * Remove a file descriptor at a given index from the set.
 */
void del_from_pfds(struct pollfd pfds[], int i, int *fd_count) {
  // Copy the one from the end over this one
  pfds[i] = pfds[*fd_count - 1];
  (*fd_count)--;
}

/*
 * Handle incoming connections.
 */
void handle_new_connection(int listener, int *fd_count, int *fd_size,
                           struct pollfd **pfds) {
  struct sockaddr_storage remoteaddr; // Client address
  socklen_t addrlen;
  int newfd; // Newly accept()ed socket descriptor
  char remoteIP[INET6_ADDRSTRLEN];

  addrlen = sizeof remoteaddr;
  newfd = accept(listener, (struct sockaddr *)&remoteaddr, &addrlen);

  if (newfd == -1) {
    perror("accept");
  } else {
    add_to_pfds(pfds, newfd, fd_count, fd_size);
    printf("pollserver: new connection from %s on socket %d\n",
           inet_ntop2(&remoteaddr, remoteIP, sizeof remoteIP), newfd);
    send_frame(newfd, 1, (void *)"hello", 5);
    printf("sent data\n");
  }
}

/*
 * Handle regular client data or client hangups.
 */
void handle_client_data(int listener, int *fd_count, struct pollfd *pfds,
                        int *pfd_i) {
  char buf[256]; // Buffer for client data
  int nbytes = recv(pfds[*pfd_i].fd, buf, sizeof buf, 0);
  int sender_fd = pfds[*pfd_i].fd;

  if (nbytes <= 0) {
    // Got error or connection closed by client
    if (nbytes == 0) {
      // Connection closed
      printf("pollserver: socket %d hung up\n", sender_fd);
    } else {
      perror("recv");
    }

    close(pfds[*pfd_i].fd); // Bye!
    del_from_pfds(pfds, *pfd_i, fd_count);

    // reexamine the slot we just deleted
    (*pfd_i)--;

  } else {
    // We got some good data from a client
    // Send to everyone!
    for (int j = 0; j < *fd_count; j++) {
      int dest_fd = pfds[j].fd;

      // Except the listener and ourselves
      if (dest_fd != listener && dest_fd != sender_fd) {
        if (sendall(dest_fd, buf, &nbytes) == -1) {
          perror("send");
        }
      }
    }
  }
}

/*
 * Process all existing connections.
 */
void process_connections(int listener, int *fd_count, int *fd_size,
                         struct pollfd **pfds) {
  for (int i = 0; i < *fd_count; i++) {
    // Check if someone's ready to read
    if ((*pfds)[i].revents & (POLLIN | POLLHUP)) {
      // We got one!!
      if ((*pfds)[i].fd == listener) {
        // If we're the listener, it's a new connection
        handle_new_connection(listener, fd_count, fd_size, pfds);
      } else {
        // Otherwise we're just a regular client
        handle_client_data(listener, fd_count, *pfds, &i);
      }
    }
  }
}

/*
 * Main: create a listener and connection set, loop forever processing
 * connections.
 */
int main(void) {
  int listener; // Listening socket descriptor

  // Start off with room for 5 connections
  // (We'll realloc as necessary)
  int fd_size = 5;
  int fd_count = 0;
  struct pollfd *pfds = malloc(sizeof *pfds * fd_size);

  // Set up and get a listening socket
  listener = get_listener_socket();

  if (listener == -1) {
    fprintf(stderr, "error getting listening socket\n");
    exit(1);
  }

  // Add the listener to set;
  // Report ready to read on incoming connection
  pfds[0].fd = listener;
  pfds[0].events = POLLIN;
  fd_count = 1; // For the listener

  puts("pollserver: waiting for connections...");

  // Main loop
  for (;;) {
    int poll_count = poll(pfds, fd_count, -1);

    if (poll_count == -1) {
      perror("poll");
      exit(1);
    }

    // Run through connections looking for data to read
    process_connections(listener, &fd_count, &fd_size, &pfds);
  }

  free(pfds);
  return 0;
}
