/*
** server.c -- a multiperson chat server
*/

#include <arpa/inet.h>
#include <endian.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

#define PORT "9034" // Port we're listening on
#define MAX_EVENTS 10
#define MAX_FDS 1024
#define CHUNK_SIZE 65536
#define MSG_CHAT 1
#define MSG_JOIN 2
#define CONNECTING 3
#define READY 4
#define MSG_FILE_START 5
#define MSG_FILE_CHUNK 6
#define MSG_FILE_END 7

struct Client {
  int fd;
  char usrname[40];
  int state;
  int transfer_dest_fd;
};

int sendall(int s, void *buf, uint32_t *len) {
  uint32_t total = 0;        // Total bytes sent
  uint32_t bytesleft = *len; // Bytes left to send
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
  uint32_t total = 0;
  uint32_t bytesleft = n;
  int rcvd;

  while (total < n) {
    rcvd = recv(s, buf + total, bytesleft, 0);

    if (rcvd == -1 || rcvd == 0) {
      break;
    }

    total += rcvd;
    bytesleft -= rcvd;
  }
  return (rcvd == -1 || rcvd == 0) ? -1 : 0;
}

void send_frame(int s, uint8_t type, void *payload, uint32_t len) {
  uint8_t header[5];
  uint32_t head_len = 5;
  uint32_t net_len = htonl(len);

  // creates the header
  header[0] = type;
  memcpy(header + 1, &(net_len), sizeof(net_len));

  if (sendall(s, header, &(head_len)) == -1 ||
      sendall(s, payload, &(len)) == -1) {
    perror("send\n");
  }
}

int recv_frame(int s, void **buf, uint8_t *type, uint32_t *len) {
  uint8_t header[5];
  uint32_t net_len;
  uint32_t HEADER_LEN = 5;

  if (recv_exact(s, header, HEADER_LEN) == -1) {
    return -1;
  }

  *type = header[0];
  memcpy(&(net_len), header + 1, 4);
  *len = ntohl(net_len);
  *buf = malloc(*len);
  if (*buf == NULL) {
    return -1;
  }

  if (recv_exact(s, *buf, *len) == -1) {
    free(*buf);
    return -1;
  }
  return 0;
}

void change_tdf_of_sendfd(struct Client *clts, char *name, int client_count,
                          int sender_fd, int *client_fds) {
  if (strcmp("all", name) == 0) {
    clts[sender_fd].transfer_dest_fd = -2;
  } else {
    for (int i = 0; i < client_count; i++) {
      if (strcmp(clts[client_fds[i]].usrname, name) == 0) {
        (clts)[sender_fd].transfer_dest_fd = (clts)[client_fds[i]].fd;
        break;
      }
    }
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
 * Handle incoming connections.
 */
void handle_new_connection(int listener, int epollfd, struct Client *clts,
                           int *client_count, int *client_fds) {
  struct sockaddr_storage remoteaddr; // Client address
  socklen_t addrlen;
  int newfd; // Newly accept()ed socket descriptor
  char remoteIP[INET6_ADDRSTRLEN];

  addrlen = sizeof remoteaddr;
  newfd = accept(listener, (struct sockaddr *)&remoteaddr, &addrlen);

  if (newfd == -1) {
    perror("accept");
  } else {
    struct epoll_event new_ev;
    new_ev.data.fd = newfd;
    new_ev.events = EPOLLIN;
    client_fds[*client_count] = newfd;
    clts[newfd].fd = newfd;
    clts[newfd].state = CONNECTING;
    clts[newfd].transfer_dest_fd = -1;
    epoll_ctl(epollfd, EPOLL_CTL_ADD, newfd, &new_ev);
    (*client_count)++;
    printf("pollserver: new connection from %s on socket %d\n",
           inet_ntop2(&remoteaddr, remoteIP, sizeof remoteIP), newfd);
  }
}

/*
 * Handle regular client data or client hangups.
 */
void handle_client_data(int listener, int epfd, struct epoll_event *event,
                        int sender_fd, struct Client *clts, int *client_count,
                        int *client_fds) {
  uint8_t *buf; // Buffer for client data
  uint8_t type;
  uint32_t len;
  int nbytes = recv_frame(sender_fd, (void *)&buf, &(type), &(len));

  if (nbytes == -1) {
    // Connection closed
    printf("pollserver: %s hung up\n", clts[sender_fd].usrname);
    char msg[70];
    snprintf(msg, sizeof(msg), "%s left the chat", clts[sender_fd].usrname);
    for (int j = 0; j < *client_count; j++) {
      int dest_fd = client_fds[j];
      if (dest_fd != listener && dest_fd != sender_fd &&
          clts[dest_fd].state == READY) {
        send_frame(dest_fd, MSG_JOIN, msg, strlen(msg));
      }
    }
    close(sender_fd); // Bye!
    epoll_ctl(epfd, EPOLL_CTL_DEL, sender_fd, event);
    for (int i = 0; i < *client_count; i++) {
      if (client_fds[i] == sender_fd) {
        client_fds[i] = client_fds[*client_count - 1];
        (*client_count)--;
      }
    }

  } else {
    if (clts[sender_fd].state == CONNECTING && len <= 39) {
      memcpy(clts[sender_fd].usrname, buf, len);
      clts[sender_fd].usrname[len] = '\0';
      clts[sender_fd].state = READY;
      printf("pollserver: %s is now ready\n", clts[sender_fd].usrname);

      char msg[70];
      snprintf(msg, sizeof(msg), "%s joined the chat", clts[sender_fd].usrname);
      for (int j = 0; j < *client_count; j++) {
        int dest_fd = client_fds[j];
        if (dest_fd != listener && dest_fd != sender_fd &&
            clts[dest_fd].state == READY) {
          send_frame(dest_fd, type, msg, strlen(msg));
        }
      }
    } else if (clts[sender_fd].state == READY) {

      switch (type) {
      case MSG_FILE_START: {
        // uint64_t f_size_net;
        // uint64_t f_size;
        char recipient[40];
        uint32_t f_name_len;
        char *f_name;

        // memcpy(&(f_size_net), buf, 8);
        // f_size = be64toh(f_size_net);
        f_name_len = len - 48;
        memcpy(recipient, buf + 8, 40);
        recipient[39] = '\0';
        f_name = malloc(f_name_len + 1);
        memcpy(f_name, buf + 48, f_name_len);
        f_name[f_name_len] = '\0';

        change_tdf_of_sendfd(clts, recipient, *client_count, sender_fd,
                             client_fds);

        if (clts[sender_fd].transfer_dest_fd == -2) {
          // Send to everyone!
          for (int j = 0; j < *client_count; j++) {
            int dest_fd = client_fds[j];

            // Except the listener and ourselves
            if (dest_fd != listener && dest_fd != sender_fd &&
                clts[dest_fd].state == READY) {
              send_frame(dest_fd, type, buf, len);
            }
          }
        } else {
          send_frame((clts)[sender_fd].transfer_dest_fd, type, buf, len);
        }
        free(f_name);
        break;
      }

      case MSG_FILE_CHUNK:
        if (clts[sender_fd].transfer_dest_fd == -2) {
          // Send to everyone!
          for (int j = 0; j < *client_count; j++) {
            int dest_fd = client_fds[j];

            // Except the listener and ourselves
            if (dest_fd != listener && dest_fd != sender_fd &&
                clts[dest_fd].state == READY) {
              send_frame(dest_fd, type, buf, len);
            }
          }
        } else {
          send_frame((clts)[sender_fd].transfer_dest_fd, type, buf, len);
        }
        break;

      case MSG_FILE_END:
        if (clts[sender_fd].transfer_dest_fd == -2) {
          // Send to everyone!
          for (int j = 0; j < *client_count; j++) {
            int dest_fd = client_fds[j];

            // Except the listener and ourselves
            if (dest_fd != listener && dest_fd != sender_fd &&
                clts[dest_fd].state == READY) {
              send_frame(dest_fd, type, buf, len);
            }
          }
        } else {
          send_frame((clts)[sender_fd].transfer_dest_fd, type, buf, len);
        }
        clts[sender_fd].transfer_dest_fd = -1;
        break;

      case MSG_CHAT:
        // We got some good data from a client
        // Send to everyone!
        for (int j = 0; j < *client_count; j++) {
          int dest_fd = client_fds[j];

          // Except the listener and ourselves
          if (dest_fd != listener && dest_fd != sender_fd &&
              clts[dest_fd].state == READY) {
            send_frame(dest_fd, type, buf, len);
          }
        }
        break;
      }
    }
    free(buf);
  }
}
/*
 * Process all existing connections.
 */
void process_connections(int listener, struct epoll_event *events, int nfds,
                         struct Client *clts, int epfd, int *client_count,
                         int *client_fds) {
  for (int i = 0; i < nfds; i++) {
    if (events[i].data.fd == listener) {
      handle_new_connection(listener, epfd, clts, client_count, client_fds);
    } else {
      // handle_client_data
      handle_client_data(listener, epfd, events, events[i].data.fd, clts,
                         client_count, client_fds);
    }
  }
}
/*
 *Main: create a listener and connection set, loop forever processing
 * connections.
 */
int main(void) {
  int listener, nfds, epollfd; // Listening socket descriptor
  struct epoll_event ev, events[MAX_EVENTS];
  int client_fds[MAX_FDS];
  int client_count = 0;

  epollfd = epoll_create1(0);
  if (epollfd == -1) {
    perror("epoll create");
    exit(EXIT_FAILURE);
  }

  struct Client *clts = malloc(sizeof *clts * MAX_FDS);

  // Set up and get a listening socket
  listener = get_listener_socket();

  if (listener == -1) {
    fprintf(stderr, "error getting listening socket\n");
    exit(EXIT_FAILURE);
  }

  // Add the listener to set
  // Report ready to read on incoming connection
  ev.data.fd = listener;
  ev.events = EPOLLIN;
  clts[listener].fd = listener;
  client_fds[0] = listener;
  if (epoll_ctl(epollfd, EPOLL_CTL_ADD, listener, &ev) == -1) {
    perror("epoll_ctl: listener");
    exit(EXIT_FAILURE);
  }
  client_count = 1;
  puts("pollserver: waiting for connections...");

  // Main loop
  for (;;) {
    nfds = epoll_wait(epollfd, events, MAX_EVENTS, -1);

    if (nfds == -1) {
      perror("epoll_wait");
      exit(EXIT_FAILURE);
    }
    // Run through connections looking for data to read
    process_connections(listener, events, nfds, clts, epollfd, &client_count,
                        client_fds);
  }

  return 0;
}
