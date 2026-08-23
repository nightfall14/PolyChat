
#ifndef NETWORK_H
#define NETWORK_H

#include <stdio.h>

const char *inet_ntop2(void *addr, char *buf, size_t size);
int get_listener_socket(void);

#endif
