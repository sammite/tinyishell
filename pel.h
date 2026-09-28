#ifndef _PEL_H
#define _PEL_H

#include <stdint.h>
#include <stddef.h>

#define BUFSIZE 4096    /* maximum message length */

#define PEL_SUCCESS 1
#define PEL_FAILURE 0

#define PEL_SYSTEM_ERROR        -1
#define PEL_CONN_CLOSED         -2
#define PEL_WRONG_CHALLENGE     -3
#define PEL_BAD_MSG_LENGTH      -4
#define PEL_CORRUPTED_DATA      -5
#define PEL_UNDEFINED_ERROR     -6

extern int32_t pel_errno;

/**
 * \brief Performs client-side cryptographic session handshake.
 *
 * Receives the server's ephemeral public key and nonce, derives the developer's
 * Ed25519 signing key from the provided 32-byte seed, signs the session transcript,
 * transmits authentication data, and negotiates directional XChaCha20-Poly1305 keys.
 *
 * \note Session state uses static file-scope contexts and is not thread-safe.
 *
 * \param[in] server Connected server socket descriptor.
 * \param[in] dev_seed 32-byte Ed25519 developer private seed.
 * \return PEL_SUCCESS (1) on successful handshake, PEL_FAILURE (0) on failure.
 */
int pel_client_init( int server, const uint8_t dev_seed[32] );

/**
 * \brief Performs server-side cryptographic session handshake.
 *
 * Generates an ephemeral keypair and nonce, transmits server hello, receives
 * client authentication, verifies the Ed25519 signature against the developer
 * public key, derives directional XChaCha20-Poly1305 keys, and transmits
 * server confirmation.
 *
 * \note Session state uses static file-scope contexts and is not thread-safe.
 *
 * \param[in] client Connected client socket descriptor.
 * \param[in] dev_pk 32-byte Ed25519 developer public key.
 * \return PEL_SUCCESS (1) on successful handshake, PEL_FAILURE (0) on failure.
 */
int pel_server_init( int client, const uint8_t dev_pk[32] );

/**
 * \brief Transmits an authenticated and encrypted message over a socket.
 *
 * Frames the message with a 16-bit big-endian length prefix and 16-byte Poly1305
 * MAC tag using XChaCha20-Poly1305 AEAD. Nonce incorporates an incrementing
 * 64-bit sequence counter to prevent replay attacks.
 *
 * \param[in] sockfd Socket file descriptor.
 * \param[in] msg Pointer to payload data buffer to encrypt and send.
 * \param[in] length Number of bytes in payload (0 <= length <= BUFSIZE).
 * \return PEL_SUCCESS (1) on success, PEL_FAILURE (0) on network or protocol error.
 */
int pel_send_msg( int sockfd, const unsigned char *msg, int length );

/**
 * \brief Receives and decrypts an authenticated message from a socket.
 *
 * Reads wire framing (length header, Poly1305 tag, and ciphertext), verifies
 * cryptographic authentication tag, and decrypts the payload into the caller-provided
 * buffer. Nonce incorporates an incrementing 64-bit sequence counter.
 *
 * \note msg buffer must have an allocated capacity of at least BUFSIZE bytes.
 *
 * \param[in]  sockfd Socket file descriptor.
 * \param[out] msg Pointer to output buffer to receive decrypted payload (>= BUFSIZE).
 * \param[out] length Pointer to integer storing the number of bytes decrypted.
 * \return PEL_SUCCESS (1) on success, PEL_FAILURE (0) on authentication failure or EOF.
 */
int pel_recv_msg( int sockfd, unsigned char *msg, int *length );

#endif /* _PEL_H */
