#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>

#define MSG_CHAT 1
#define MSG_JOIN 2
#define CONNECTING 3
#define READY 4
#define MSG_FILE_START 5
#define MSG_FILE_CHUNK 6
#define MSG_FILE_END 7
#define CHUNK_SIZE 65536
#define MAX_PAYLOAD_SIZE 65590

int sendall(int s, void *buf, uint32_t *len);
int recv_exact(int s, void *buf, uint32_t n);
void send_frame(int s, uint8_t type, void *payload, uint32_t len);
int recv_frame(int s, void **buf, uint8_t *type, uint32_t *len);

#endif
