/*
** server.c -- a multiperson chat server
*/
#include "network.h"
#include "protocol.h"
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <unistd.h>

#define MAX_EVENTS 10
#define MAX_FDS 1024

struct Client {
  int fd;
  char usrname[40];
  int state;
  int transfer_dest_fd;
};

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

void route_frame(int *client_count, int *client_fds, int listener,
                 int sender_fd, struct Client *clts, void *msg, uint8_t type,
                 uint32_t len) {
  for (int j = 0; j < *client_count; j++) {
    int dest_fd = client_fds[j];
    if (dest_fd != listener && dest_fd != sender_fd &&
        clts[dest_fd].state == READY) {
      send_frame(dest_fd, type, msg, len);
    }
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
  struct sockaddr_storage remoteaddr; // Client address
  char remoteIP[INET6_ADDRSTRLEN];
  char msg[70];
  socklen_t addrlen = sizeof(remoteaddr);

  getpeername(sender_fd, (struct sockaddr *)&remoteaddr, &addrlen);

  if (nbytes == -1 || nbytes == -2) {
    // Connection closed
    if (nbytes == -2) {
      printf("Malicious user: %s(%s) trying to send payload of length(%d).",
             clts[sender_fd].usrname,
             inet_ntop2(&remoteaddr, remoteIP, sizeof remoteIP), len);
      snprintf(msg, sizeof(msg), "%s removed from the chat",
               clts[sender_fd].usrname);
      route_frame(client_count, client_fds, listener, sender_fd, clts, msg,
                  MSG_JOIN, strlen(msg));
    } else {
      printf("pollserver: %s hung up\n", clts[sender_fd].usrname);
      snprintf(msg, sizeof(msg), "%s left the chat", clts[sender_fd].usrname);
      route_frame(client_count, client_fds, listener, sender_fd, clts, msg,
                  MSG_JOIN, strlen(msg));
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
      snprintf(msg, sizeof(msg), "%s joined the chat", clts[sender_fd].usrname);
      route_frame(client_count, client_fds, listener, sender_fd, clts, msg,
                  MSG_JOIN, strlen(msg));
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
          route_frame(client_count, client_fds, listener, sender_fd, clts, buf,
                      type, len);
        } else {
          send_frame((clts)[sender_fd].transfer_dest_fd, type, buf, len);
        }
        free(f_name);
        break;
      }

      case MSG_FILE_END:
      case MSG_FILE_CHUNK:
        if (clts[sender_fd].transfer_dest_fd == -2) {
          // Send to everyone!
          route_frame(client_count, client_fds, listener, sender_fd, clts, buf,
                      type, len);
        } else {
          send_frame((clts)[sender_fd].transfer_dest_fd, type, buf, len);
        }
        break;

      case MSG_CHAT: {
        // We got some good data from a client
        // Send to everyone!
        uint32_t tot_len = strlen(clts[sender_fd].usrname) + 2 + len;
        char *char_buf = malloc(tot_len);
        snprintf(char_buf, tot_len, "%s: ", clts[sender_fd].usrname);
        int prefix_len = strlen(clts[sender_fd].usrname) + 2;
        memcpy(char_buf + prefix_len, buf, len);
        route_frame(client_count, client_fds, listener, sender_fd, clts,
                    char_buf, type, tot_len);
        free(char_buf);
        break;
      }
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
