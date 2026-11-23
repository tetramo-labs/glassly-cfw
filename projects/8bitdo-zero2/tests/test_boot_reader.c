/* No device enumeration/open/transfer: exercise the response parser directly. */
#define main boot_reader_main
#include "../tools/read_boot_version.c"
#undef main
#include <assert.h>

static void check(uint8_t *packet, unsigned length, int expected) {
    received = 0;
    input(NULL, kIOReturnSuccess, NULL, kIOHIDReportTypeInput, 0, packet, length);
    assert(received == expected);
}

int main(void) {
    assert(crc16((const uint8_t *)"123456789", 9) == 0x4b37);
    assert(crc16(NULL, 0) == 0xffff);
    uint8_t packet[64] = {0,5,0,0,5,0,32,0};
    expected_command = 5; expected_bytes = 32; expected_address = 0x01018000;
    put32(packet+10, 32); put32(packet+14, expected_address);
    for (unsigned i=0; i<32; ++i) packet[18+i] = (uint8_t)i;
    uint16_t crc = crc16(packet+18, 32); packet[8] = crc; packet[9] = crc >> 8;
    check(packet, 64, 1);
    packet[18] ^= 1; check(packet, 64, -1); packet[18] ^= 1;
    packet[14] ^= 1; check(packet, 64, -1); packet[14] ^= 1;
    packet[10] = 31; check(packet, 64, -1); packet[10] = 32;
    packet[6] = 47; check(packet, 64, -1); packet[6] = 32;
    check(packet, 49, -1); check(packet, 17, 0);
    packet[2] = 1; check(packet, 64, -1); packet[2] = 0;
    packet[4] = 8; check(packet, 64, 0);
    expected_command = 8; expected_bytes = 2;
    check(packet, 64, 1); /* Can receive more bytes than the identity word. */
    packet[8] ^= 1; check(packet, 64, -1);
    /* Narrow identification/register reads still require exact sizes and CRC. */
    for (unsigned n=2; n<=4; n+=2) {
        memset(packet, 0, sizeof(packet)); packet[1]=5; packet[4]=5; packet[6]=n;
        expected_command=5; expected_bytes=n; expected_address=n==2 ? 0xc8000 : 0xf856c;
        put32(packet+10,n); put32(packet+14,expected_address);
        memset(packet+18,0xff,n); /* Accepted transport bytes are not a valid chip identification claim. */
        crc=crc16(packet+18,n); packet[8]=crc; packet[9]=crc>>8;
        check(packet,64,1);
        check(packet,18+n-1,-1);
        packet[14]^=1; check(packet,64,-1);
    }
    puts("Boot response CRC, address, length, status and command checks passed; no hardware accessed.");
    return 0;
}
