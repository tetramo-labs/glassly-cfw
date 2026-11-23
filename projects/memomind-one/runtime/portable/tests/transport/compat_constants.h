/* Test-only original G2 constant names. */
#define CFW_MESSAGE_SID 0xf0u
#define CFW_MESSAGE_LEFT 1u
#define CFW_MESSAGE_RIGHT 2u
#define CFW_MESSAGE_BOTH (CFW_MESSAGE_LEFT | CFW_MESSAGE_RIGHT)
#define CFW_MESSAGE_ACK 1u
#define CFW_MESSAGE_NACK 3u
#define CFW_MESSAGE_REPLY 5u /* revision 38: object-cache reply, sent before the ACK */
#define CFW_MESSAGE_COMPRESSED 4u
#define CFW_MESSAGE_RESET_CONTEXT 8u
#define CFW_MESSAGE_MAX 65535u
#define CFW_MESSAGE_RESET 0x80u
#define CFW_MESSAGE_END 0x40u
#define CFW_ACK_HISTORY 3u
#define CFW_ACK_ENTRY_SIZE 7u /* stream, ordinal LE16, size LE16, CRC LE16 */
#define CFW_REPLY_HDR_SIZE 5u /* kind, stream, ordinal LE16, lens */
#define CFW_REPLY_MAX_SIZE 255u
#define CFW_NACK_FLAGS    1u   /* record flags/lens bits inconsistent with the stream */
#define CFW_NACK_CONTEXT  2u   /* compressed record without a valid inflate context */
#define CFW_NACK_INFLATE  3u   /* decode buffer allocation or inflate failed */
#define CFW_NACK_CRC      4u   /* decoded CRC-16 mismatch */
#define CFW_NACK_HANDLER  5u   /* image_dispatch refused the message (see worker_fail_mode) */
#define CFW_ACK_SIZE 9u
#define CFW_ACK_MAX_SIZE 30u
#define cfw_message_crc mm_transport_crc
