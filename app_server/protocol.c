#include "protocol.h"
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int sendall(int s, void *buf, uint32_t *len) {
  uint32_t total = 0;        // Total bytes sent
  uint32_t bytesleft = *len; // Bytes left to send
  int n;

  while (total < *len) {
    n = send(s, (uint8_t *)buf + total, bytesleft, 0);

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
    rcvd = recv(s, (uint8_t *)buf + total, bytesleft, 0);

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
  if (*len > MAX_PAYLOAD_SIZE) {
    return -2;
  }
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
