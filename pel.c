/*
 * Packet Encryption Layer (PEL) for Tiny SHell
 * Migrated to Monocypher (X25519, Ed25519, ChaCha20-Poly1305, BLAKE2b)
 * Adheres to Barr-C:2018 coding standards.
 */

#include <sys/types.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <fcntl.h>
#include <string.h>
#include <stdint.h>

#include "pel.h"
#include "monocypher.h"
#include "monocypher-ed25519.h"

int32_t pel_errno = PEL_UNDEFINED_ERROR;

struct pel_context
{
    uint8_t key[32];
    uint8_t nonce_base[16];
    uint64_t seq_num;
};

static struct pel_context send_ctx;
static struct pel_context recv_ctx;

static uint8_t buffer[BUFSIZE + 18];

/* Internal function prototypes */
static int pel_get_random(uint8_t *buf, size_t len);
static int pel_send_all(int s, const void *buf, size_t len, int flags);
static int pel_recv_all(int s, void *buf, size_t len, int flags);

/*
 * Securely fill buffer with cryptographically secure random bytes.
 */
static int pel_get_random(uint8_t *buf, size_t len)
{
#if defined(SYS_getrandom)
    ssize_t ret = syscall(SYS_getrandom, buf, len, 0);
    if (ret == (ssize_t)len)
    {
        return 0;
    }
#endif

    int fd = open("/dev/urandom", O_RDONLY);
    if (fd >= 0)
    {
        size_t total = 0;
        while (total < len)
        {
            ssize_t n = read(fd, buf + total, len - total);
            if (n <= 0)
            {
                close(fd);
                return -1;
            }
            total += (size_t)n;
        }
        close(fd);
        return 0;
    }

    return -1;
}

/*
 * Reliable send loop for streaming sockets.
 */
static int pel_send_all(int s, const void *buf, size_t len, int flags)
{
    size_t sum = 0;
    const uint8_t *offset = (const uint8_t *)buf;

    while (sum < len)
    {
        ssize_t n = send(s, offset, len - sum, flags);
        if (n < 0)
        {
            pel_errno = PEL_SYSTEM_ERROR;
            return PEL_FAILURE;
        }

        sum += (size_t)n;
        offset += n;
    }

    pel_errno = PEL_UNDEFINED_ERROR;
    return PEL_SUCCESS;
}

/*
 * Reliable receive loop for streaming sockets.
 */
static int pel_recv_all(int s, void *buf, size_t len, int flags)
{
    size_t sum = 0;
    uint8_t *offset = (uint8_t *)buf;

    while (sum < len)
    {
        ssize_t n = recv(s, offset, len - sum, flags);
        if (n == 0)
        {
            pel_errno = PEL_CONN_CLOSED;
            return PEL_FAILURE;
        }
        if (n < 0)
        {
            pel_errno = PEL_SYSTEM_ERROR;
            return PEL_FAILURE;
        }

        sum += (size_t)n;
        offset += n;
    }

    pel_errno = PEL_UNDEFINED_ERROR;
    return PEL_SUCCESS;
}

/*
 * Client-side session handshake:
 * 1. Recv Msg1 from Server: s_epk (32B) || n_s (16B) = 48B
 * 2. Generate client ephemeral keypair (c_esk, c_epk)
 * 3. Sign transcript: s_epk (32B) || c_epk (32B) || n_s (16B) = 80B
 * 4. Send Msg2 to Server: c_epk (32B) || sig (64B) = 96B
 * 5. Compute ECDH shared secret & derive directional ChaCha20-Poly1305 keys.
 */
int pel_client_init(int server, const char *key)
{
    uint8_t dev_seed[32];
    uint8_t dev_sk[64];
    uint8_t dev_pk[32];
    uint8_t s_epk[32];
    uint8_t n_s[16];
    uint8_t c_esk[32];
    uint8_t c_epk[32];
    uint8_t transcript[80];
    uint8_t sig[64];
    uint8_t msg1[48];
    uint8_t msg2[96];
    uint8_t k_shared[32];
    int ret;

    if (key == NULL)
    {
        pel_errno = PEL_SYSTEM_ERROR;
        return PEL_FAILURE;
    }

    /* Derive developer Ed25519 keypair from secret/passphrase */
    crypto_blake2b(dev_seed, 32, (const uint8_t *)key, strlen(key));
    crypto_ed25519_key_pair(dev_sk, dev_pk, dev_seed);
    crypto_wipe(dev_seed, sizeof(dev_seed));

    /* Receive Server Hello: s_epk (32 bytes) || n_s (16 bytes) = 48 bytes */
    ret = pel_recv_all(server, msg1, 48, 0);
    if (ret != PEL_SUCCESS)
    {
        crypto_wipe(dev_sk, sizeof(dev_sk));
        return PEL_FAILURE;
    }
    memcpy(s_epk, msg1, 32);
    memcpy(n_s, msg1 + 32, 16);

    /* Generate client ephemeral keypair (c_esk, c_epk) */
    if (pel_get_random(c_esk, 32) != 0)
    {
        crypto_wipe(dev_sk, sizeof(dev_sk));
        pel_errno = PEL_SYSTEM_ERROR;
        return PEL_FAILURE;
    }
    crypto_x25519_public_key(c_epk, c_esk);

    /* Construct transcript: s_epk (32) || c_epk (32) || n_s (16) */
    memcpy(transcript, s_epk, 32);
    memcpy(transcript + 32, c_epk, 32);
    memcpy(transcript + 64, n_s, 16);

    /* Sign transcript */
    crypto_ed25519_sign(sig, dev_sk, transcript, sizeof(transcript));
    crypto_wipe(dev_sk, sizeof(dev_sk));

    /* Send Client Auth: c_epk (32 bytes) || sig (64 bytes) = 96 bytes */
    memcpy(msg2, c_epk, 32);
    memcpy(msg2 + 32, sig, 64);
    ret = pel_send_all(server, msg2, 96, 0);
    if (ret != PEL_SUCCESS)
    {
        crypto_wipe(c_esk, sizeof(c_esk));
        return PEL_FAILURE;
    }

    /* Compute ECDH shared secret */
    crypto_x25519(k_shared, c_esk, s_epk);
    crypto_wipe(c_esk, sizeof(c_esk));

    /* Derive symmetric keys and nonces for client (c2s = send, s2c = recv) */
    crypto_blake2b_keyed(send_ctx.key, 32, k_shared, 32,
                         (const uint8_t *)"c2s", 3);
    crypto_blake2b_keyed(recv_ctx.key, 32, k_shared, 32,
                         (const uint8_t *)"s2c", 3);
    crypto_blake2b_keyed(send_ctx.nonce_base, 16, k_shared, 32,
                         (const uint8_t *)"nc2s", 4);
    crypto_blake2b_keyed(recv_ctx.nonce_base, 16, k_shared, 32,
                         (const uint8_t *)"ns2c", 4);
    send_ctx.seq_num = 0;
    recv_ctx.seq_num = 0;

    /* Receive Server Confirmation (Msg 3): 16 bytes */
    uint8_t s_confirm[16];
    uint8_t expected_confirm[16];
    crypto_blake2b_keyed(expected_confirm, 16, k_shared, 32,
                         (const uint8_t *)"server-ok", 9);
    crypto_wipe(k_shared, sizeof(k_shared));

    ret = pel_recv_all(server, s_confirm, 16, 0);
    if (ret != PEL_SUCCESS)
    {
        pel_errno = PEL_WRONG_CHALLENGE;
        return PEL_FAILURE;
    }

    if (crypto_verify16(s_confirm, expected_confirm) != 0)
    {
        pel_errno = PEL_WRONG_CHALLENGE;
        return PEL_FAILURE;
    }

    pel_errno = PEL_UNDEFINED_ERROR;
    return PEL_SUCCESS;
}

/*
 * Server-side session handshake:
 * 1. Generate server ephemeral keypair (s_esk, s_epk) and server nonce n_s
 * 2. Send Msg1 to Client: s_epk (32B) || n_s (16B) = 48B
 * 3. Recv Msg2 from Client: c_epk (32B) || sig (64B) = 96B
 * 4. Verify client Ed25519 signature against developer public key
 * 5. Compute ECDH shared secret & derive directional ChaCha20-Poly1305 keys.
 */
int pel_server_init(int client, const char *key)
{
    uint8_t dev_seed[32];
    uint8_t dev_sk[64];
    uint8_t dev_pk[32];
    uint8_t s_esk[32];
    uint8_t s_epk[32];
    uint8_t n_s[16];
    uint8_t c_epk[32];
    uint8_t transcript[80];
    uint8_t sig[64];
    uint8_t msg1[48];
    uint8_t msg2[96];
    uint8_t k_shared[32];
    int ret;

    if (key == NULL)
    {
        pel_errno = PEL_SYSTEM_ERROR;
        return PEL_FAILURE;
    }

    /* Derive developer public key from secret/passphrase */
    crypto_blake2b(dev_seed, 32, (const uint8_t *)key, strlen(key));
    crypto_ed25519_key_pair(dev_sk, dev_pk, dev_seed);
    crypto_wipe(dev_seed, sizeof(dev_seed));
    crypto_wipe(dev_sk, sizeof(dev_sk)); /* Server never keeps private key */

    /* Generate server ephemeral keypair (s_esk, s_epk) and server nonce n_s */
    if (pel_get_random(s_esk, 32) != 0 || pel_get_random(n_s, 16) != 0)
    {
        pel_errno = PEL_SYSTEM_ERROR;
        return PEL_FAILURE;
    }
    crypto_x25519_public_key(s_epk, s_esk);

    /* Send Server Hello: s_epk (32 bytes) || n_s (16 bytes) = 48 bytes */
    memcpy(msg1, s_epk, 32);
    memcpy(msg1 + 32, n_s, 16);
    ret = pel_send_all(client, msg1, 48, 0);
    if (ret != PEL_SUCCESS)
    {
        crypto_wipe(s_esk, sizeof(s_esk));
        return PEL_FAILURE;
    }

    /* Receive Client Auth: c_epk (32 bytes) || sig (64 bytes) = 96 bytes */
    ret = pel_recv_all(client, msg2, 96, 0);
    if (ret != PEL_SUCCESS)
    {
        crypto_wipe(s_esk, sizeof(s_esk));
        return PEL_FAILURE;
    }
    memcpy(c_epk, msg2, 32);
    memcpy(sig, msg2 + 32, 64);

    /* Construct transcript: s_epk (32) || c_epk (32) || n_s (16) */
    memcpy(transcript, s_epk, 32);
    memcpy(transcript + 32, c_epk, 32);
    memcpy(transcript + 64, n_s, 16);

    /* Verify signature against developer public key */
    if (crypto_ed25519_check(sig, dev_pk, transcript, sizeof(transcript)) != 0)
    {
        crypto_wipe(s_esk, sizeof(s_esk));
        pel_errno = PEL_WRONG_CHALLENGE;
        return PEL_FAILURE;
    }

    /* Compute ECDH shared secret */
    crypto_x25519(k_shared, s_esk, c_epk);
    crypto_wipe(s_esk, sizeof(s_esk));

    /* Derive symmetric keys and nonces for server (s2c = send, c2s = recv) */
    crypto_blake2b_keyed(send_ctx.key, 32, k_shared, 32,
                         (const uint8_t *)"s2c", 3);
    crypto_blake2b_keyed(recv_ctx.key, 32, k_shared, 32,
                         (const uint8_t *)"c2s", 3);
    crypto_blake2b_keyed(send_ctx.nonce_base, 16, k_shared, 32,
                         (const uint8_t *)"ns2c", 4);
    crypto_blake2b_keyed(recv_ctx.nonce_base, 16, k_shared, 32,
                         (const uint8_t *)"nc2s", 4);
    send_ctx.seq_num = 0;
    recv_ctx.seq_num = 0;

    /* Send Server Confirmation (Msg 3): 16 bytes */
    uint8_t s_confirm[16];
    crypto_blake2b_keyed(s_confirm, 16, k_shared, 32,
                         (const uint8_t *)"server-ok", 9);
    crypto_wipe(k_shared, sizeof(k_shared));

    ret = pel_send_all(client, s_confirm, 16, 0);
    if (ret != PEL_SUCCESS)
    {
        return PEL_FAILURE;
    }

    pel_errno = PEL_UNDEFINED_ERROR;
    return PEL_SUCCESS;
}

/*
 * Send an authenticated and encrypted message using ChaCha20-Poly1305 AEAD.
 * Wire format:
 * [0..1]   = length (big-endian 16-bit)
 * [2..17]  = Poly1305 MAC tag (16 bytes)
 * [18..]   = ChaCha20 ciphertext (length bytes)
 */
int pel_send_msg(int sockfd, const unsigned char *msg, int length)
{
    uint8_t nonce[24];
    uint8_t ad[10];
    int ret;
    int i;

    if (length < 0 || length > BUFSIZE)
    {
        pel_errno = PEL_BAD_MSG_LENGTH;
        return PEL_FAILURE;
    }

    buffer[0] = (uint8_t)((length >> 8) & 0xFF);
    buffer[1] = (uint8_t)(length & 0xFF);

    /* Construct 24-byte nonce: 16 bytes base || 8 bytes seq_num (big-endian) */
    memcpy(nonce, send_ctx.nonce_base, 16);
    for (i = 0; i < 8; i++)
    {
        nonce[16 + i] = (uint8_t)((send_ctx.seq_num >> (56 - (8 * i))) & 0xFF);
    }

    /* Associated Data: 2 bytes length || 8 bytes seq_num */
    ad[0] = buffer[0];
    ad[1] = buffer[1];
    memcpy(ad + 2, nonce + 16, 8);

    /* Encrypt payload and compute MAC */
    crypto_aead_lock(&buffer[18], &buffer[2], send_ctx.key, nonce,
                     ad, sizeof(ad), (const uint8_t *)msg, (size_t)length);

    send_ctx.seq_num++;

    ret = pel_send_all(sockfd, buffer, (size_t)(length + 18), 0);
    if (ret != PEL_SUCCESS)
    {
        return PEL_FAILURE;
    }

    pel_errno = PEL_UNDEFINED_ERROR;
    return PEL_SUCCESS;
}

/*
 * Receive and decrypt an authenticated message using ChaCha20-Poly1305 AEAD.
 */
int pel_recv_msg(int sockfd, unsigned char *msg, int *length)
{
    uint8_t nonce[24];
    uint8_t ad[10];
    int payload_len;
    int ret;
    int i;

    /* Read 2 bytes for payload length */
    ret = pel_recv_all(sockfd, buffer, 2, 0);
    if (ret != PEL_SUCCESS)
    {
        return PEL_FAILURE;
    }

    payload_len = ((int)buffer[0] << 8) | (int)buffer[1];
    if (payload_len < 0 || payload_len > BUFSIZE)
    {
        pel_errno = PEL_BAD_MSG_LENGTH;
        return PEL_FAILURE;
    }

    /* Read MAC tag (16 bytes) and ciphertext (payload_len bytes) */
    if (payload_len + 16 > 0)
    {
        ret = pel_recv_all(sockfd, &buffer[2], (size_t)(payload_len + 16), 0);
        if (ret != PEL_SUCCESS)
        {
            return PEL_FAILURE;
        }
    }

    /* Construct 24-byte nonce: 16 bytes base || 8 bytes seq_num (big-endian) */
    memcpy(nonce, recv_ctx.nonce_base, 16);
    for (i = 0; i < 8; i++)
    {
        nonce[16 + i] = (uint8_t)((recv_ctx.seq_num >> (56 - (8 * i))) & 0xFF);
    }

    /* Associated Data: 2 bytes length || 8 bytes seq_num */
    ad[0] = buffer[0];
    ad[1] = buffer[1];
    memcpy(ad + 2, nonce + 16, 8);

    /* Decrypt ciphertext and verify MAC */
    if (crypto_aead_unlock((uint8_t *)msg, &buffer[2], recv_ctx.key, nonce,
                           ad, sizeof(ad), &buffer[18],
                           (size_t)payload_len) != 0)
    {
        pel_errno = PEL_CORRUPTED_DATA;
        return PEL_FAILURE;
    }

    recv_ctx.seq_num++;
    *length = payload_len;
    pel_errno = PEL_UNDEFINED_ERROR;
    return PEL_SUCCESS;
}
