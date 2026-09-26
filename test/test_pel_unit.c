/*
 * C Unit Tests for Packet Encryption Layer (PEL) with Monocypher.
 * Tests handshake, integrity checks, tamper rejection, and protocol edge cases.
 * Adheres to Barr-C:2018 coding standards.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/wait.h>

#include "pel.h"
#include "monocypher.h"
#include "monocypher-ed25519.h"

#define TEST_ASSERT(cond)                                                      \
    do                                                                         \
    {                                                                          \
        if (!(cond))                                                           \
        {                                                                      \
            fprintf(stderr, "TEST ASSERTION FAILED: %s (%s:%d)\n",             \
                    #cond, __FILE__, __LINE__);                                \
            exit(1);                                                           \
        }                                                                      \
    } while (0)

/* Forward declarations */
static void test_pel_happy_path(void);
static void test_pel_mismatched_keys(void);
static void test_pel_tampered_ciphertext(void);
static void test_pel_tampered_tag(void);
static void test_pel_oversized_packet(void);

/*
 * Test 1: Happy path - complete handshake and bidirectional data transfer.
 */
static void test_pel_happy_path(void)
{
    int32_t sv[2];
    pid_t pid;

    TEST_ASSERT(socketpair(AF_UNIX, SOCK_STREAM, 0, sv) == 0);

    pid = fork();
    TEST_ASSERT(pid >= 0);

    if (pid == 0)
    {
        /* Client child */
        const char *client_msg = "Client message payload.";
        uint8_t rx_buf[BUFSIZE];
        int32_t rx_len = 0;
        int32_t ret;

        close(sv[0]);

        ret = pel_client_init(sv[1], "shared_secret_123");
        TEST_ASSERT(ret == PEL_SUCCESS);

        ret = pel_send_msg(sv[1], (uint8_t *)client_msg,
                           (int32_t)strlen(client_msg));
        TEST_ASSERT(ret == PEL_SUCCESS);

        ret = pel_recv_msg(sv[1], rx_buf, &rx_len);
        TEST_ASSERT(ret == PEL_SUCCESS);
        TEST_ASSERT(rx_len == 23);
        TEST_ASSERT(memcmp(rx_buf, "Server response payload", 23) == 0);

        close(sv[1]);
        _exit(0);
    }
    else
    {
        /* Server parent */
        const char *server_msg = "Server response payload";
        uint8_t rx_buf[BUFSIZE];
        int32_t rx_len = 0;
        int32_t status;
        int32_t ret;

        close(sv[1]);

        ret = pel_server_init(sv[0], "shared_secret_123");
        TEST_ASSERT(ret == PEL_SUCCESS);

        ret = pel_recv_msg(sv[0], rx_buf, &rx_len);
        TEST_ASSERT(ret == PEL_SUCCESS);
        TEST_ASSERT(rx_len == 23);
        TEST_ASSERT(memcmp(rx_buf, "Client message payload.", 23) == 0);

        ret = pel_send_msg(sv[0], (uint8_t *)server_msg,
                           (int32_t)strlen(server_msg));
        TEST_ASSERT(ret == PEL_SUCCESS);

        close(sv[0]);
        waitpid(pid, &status, 0);
        TEST_ASSERT(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    }
}

/*
 * Test 2: Mismatched keys - server must reject client signature.
 */
static void test_pel_mismatched_keys(void)
{
    int32_t sv[2];
    pid_t pid;

    TEST_ASSERT(socketpair(AF_UNIX, SOCK_STREAM, 0, sv) == 0);

    pid = fork();
    TEST_ASSERT(pid >= 0);

    if (pid == 0)
    {
        /* Client child with WRONG key */
        int32_t ret;
        close(sv[0]);

        ret = pel_client_init(sv[1], "wrong_secret");
        TEST_ASSERT(ret == PEL_FAILURE);
        TEST_ASSERT(pel_errno == PEL_WRONG_CHALLENGE);

        close(sv[1]);
        _exit(0);
    }
    else
    {
        /* Server parent with EXPECTED key */
        int32_t status;
        int32_t ret;
        close(sv[1]);

        ret = pel_server_init(sv[0], "correct_secret");
        TEST_ASSERT(ret == PEL_FAILURE);
        TEST_ASSERT(pel_errno == PEL_WRONG_CHALLENGE);

        close(sv[0]);
        waitpid(pid, &status, 0);
        TEST_ASSERT(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    }
}

/*
 * Test 3: Wire tampering - bit flip in ciphertext causes PEL_CORRUPTED_DATA.
 */
static void test_pel_tampered_ciphertext(void)
{
    int32_t sv[2];
    pid_t pid;

    TEST_ASSERT(socketpair(AF_UNIX, SOCK_STREAM, 0, sv) == 0);

    pid = fork();
    TEST_ASSERT(pid >= 0);

    if (pid == 0)
    {
        /* Client child: handshakes, then manually injects tampered packet */
        int32_t ret;
        uint8_t packet[18 + 10];
        ssize_t w;
        close(sv[0]);

        ret = pel_client_init(sv[1], "secret_tamper");
        TEST_ASSERT(ret == PEL_SUCCESS);

        /* Send valid packet first */
        ret = pel_send_msg(sv[1], (uint8_t *)"0123456789", 10);
        TEST_ASSERT(ret == PEL_SUCCESS);

        /* 2B length (10), 16B tag, 10B ciphertext */
        packet[0] = 0x00;
        packet[1] = 0x0A;
        memset(packet + 2, 0xAA, 16);  /* Bogus tag */
        memset(packet + 18, 0x55, 10); /* Bogus ciphertext */
        w = write(sv[1], packet, sizeof(packet));
        TEST_ASSERT(w == (ssize_t)sizeof(packet));

        close(sv[1]);
        _exit(0);
    }
    else
    {
        /* Server parent: receives valid packet, fails on corrupted packet */
        uint8_t rx_buf[BUFSIZE];
        int32_t rx_len = 0;
        int32_t status;
        int32_t ret;

        close(sv[1]);

        ret = pel_server_init(sv[0], "secret_tamper");
        TEST_ASSERT(ret == PEL_SUCCESS);

        /* 1st packet must succeed */
        ret = pel_recv_msg(sv[0], rx_buf, &rx_len);
        TEST_ASSERT(ret == PEL_SUCCESS);

        /* 2nd packet has corrupted tag -> must fail with PEL_CORRUPTED_DATA */
        ret = pel_recv_msg(sv[0], rx_buf, &rx_len);
        TEST_ASSERT(ret == PEL_FAILURE);
        TEST_ASSERT(pel_errno == PEL_CORRUPTED_DATA);

        close(sv[0]);
        waitpid(pid, &status, 0);
        TEST_ASSERT(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    }
}

/*
 * Test 4: Wire tampering - corrupted Poly1305 MAC tag.
 */
static void test_pel_tampered_tag(void)
{
    int32_t sv[2];
    pid_t pid;

    TEST_ASSERT(socketpair(AF_UNIX, SOCK_STREAM, 0, sv) == 0);

    pid = fork();
    TEST_ASSERT(pid >= 0);

    if (pid == 0)
    {
        int32_t ret;
        uint8_t raw_frame[18 + 5];
        ssize_t w;
        close(sv[0]);

        ret = pel_client_init(sv[1], "secret_tag");
        TEST_ASSERT(ret == PEL_SUCCESS);

        /* Construct frame declaring 5 bytes with invalid MAC */
        raw_frame[0] = 0x00;
        raw_frame[1] = 0x05;
        memset(raw_frame + 2, 0xFF, 16);
        memcpy(raw_frame + 18, "hello", 5);
        w = write(sv[1], raw_frame, sizeof(raw_frame));
        TEST_ASSERT(w == (ssize_t)sizeof(raw_frame));

        close(sv[1]);
        _exit(0);
    }
    else
    {
        uint8_t rx_buf[BUFSIZE];
        int32_t rx_len = 0;
        int32_t status;
        int32_t ret;

        close(sv[1]);

        ret = pel_server_init(sv[0], "secret_tag");
        TEST_ASSERT(ret == PEL_SUCCESS);

        ret = pel_recv_msg(sv[0], rx_buf, &rx_len);
        TEST_ASSERT(ret == PEL_FAILURE);
        TEST_ASSERT(pel_errno == PEL_CORRUPTED_DATA);

        close(sv[0]);
        waitpid(pid, &status, 0);
        TEST_ASSERT(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    }
}

/*
 * Test 5: Oversized packet header (> 4096 bytes) must be rejected.
 */
static void test_pel_oversized_packet(void)
{
    int32_t sv[2];
    pid_t pid;

    TEST_ASSERT(socketpair(AF_UNIX, SOCK_STREAM, 0, sv) == 0);

    pid = fork();
    TEST_ASSERT(pid >= 0);

    if (pid == 0)
    {
        int32_t ret;
        uint8_t oversized_header[2];
        ssize_t w;
        close(sv[0]);

        ret = pel_client_init(sv[1], "secret_size");
        TEST_ASSERT(ret == PEL_SUCCESS);

        /* Send header declaring 5000 bytes (> BUFSIZE 4096) */
        oversized_header[0] = (uint8_t)(5000 >> 8);
        oversized_header[1] = (uint8_t)(5000 & 0xFF);
        w = write(sv[1], oversized_header, 2);
        TEST_ASSERT(w == 2);

        close(sv[1]);
        _exit(0);
    }
    else
    {
        uint8_t rx_buf[BUFSIZE];
        int32_t rx_len = 0;
        int32_t status;
        int32_t ret;

        close(sv[1]);

        ret = pel_server_init(sv[0], "secret_size");
        TEST_ASSERT(ret == PEL_SUCCESS);

        ret = pel_recv_msg(sv[0], rx_buf, &rx_len);
        TEST_ASSERT(ret == PEL_FAILURE);
        TEST_ASSERT(pel_errno == PEL_BAD_MSG_LENGTH);

        close(sv[0]);
        waitpid(pid, &status, 0);
        TEST_ASSERT(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    }
}

int32_t main(void)
{
    printf("[RUNNING] test_pel_happy_path...\n");
    test_pel_happy_path();
    printf("[PASSED]  test_pel_happy_path\n");

    printf("[RUNNING] test_pel_mismatched_keys...\n");
    test_pel_mismatched_keys();
    printf("[PASSED]  test_pel_mismatched_keys\n");

    printf("[RUNNING] test_pel_tampered_ciphertext...\n");
    test_pel_tampered_ciphertext();
    printf("[PASSED]  test_pel_tampered_ciphertext\n");

    printf("[RUNNING] test_pel_tampered_tag...\n");
    test_pel_tampered_tag();
    printf("[PASSED]  test_pel_tampered_tag\n");

    printf("[RUNNING] test_pel_oversized_packet...\n");
    test_pel_oversized_packet();
    printf("[PASSED]  test_pel_oversized_packet\n");

    printf("\nAll PEL C cryptographic unit tests passed successfully!\n");
    return 0;
}
