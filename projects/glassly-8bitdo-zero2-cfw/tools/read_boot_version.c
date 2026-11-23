/* One read-only query using the pinned vendor updater's packet format.
 * No erase/write-memory/reset commands, command-line addresses or retries.
 * Compile: clang -Wall -Wextra -Werror tools/read_boot_version.c
 *          -framework IOKit -framework CoreFoundation -o build/read_boot_version
 * Usage: build/read_boot_version USB_LOCATION_ID version|identity|app-header|rom-header|boot-entry|radio-id|radio-clock|address-space-check
 *        build/read_boot_version USB_LOCATION_ID app-image OUTPUT_FILE
 *        build/read_boot_version USB_LOCATION_ID arm-rom-api OUTPUT_FILE
 *        build/read_boot_version USB_LOCATION_ID arm-rom-prefix OUTPUT_FILE
 * The required location must come from the observed controller's USB registry.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/hid/IOHIDManager.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int received;
static unsigned expected_command;
static unsigned expected_bytes;
static uint32_t expected_address;
static FILE *image;
static uint16_t crc16(const uint8_t *data, unsigned size) {
    uint16_t crc = 0xffff; /* vendor 0x10009b70, polynomial table at 0x101aee94 */
    for (unsigned i=0; i<size; ++i) {
        crc ^= data[i];
        for (unsigned bit=0; bit<8; ++bit) crc = (crc >> 1) ^ ((crc & 1) ? 0xa001 : 0);
    }
    return crc;
}
static uint32_t le32(const uint8_t *p) {
    return p[0] | ((uint32_t)p[1]<<8) | ((uint32_t)p[2]<<16) | ((uint32_t)p[3]<<24);
}
static void put32(uint8_t *p, uint32_t value) {
    for (unsigned i=0; i<4; ++i) p[i] = (uint8_t)(value >> (i*8));
}
static const uint8_t descriptor[] = {
    0x05,0x8c,0x09,0x01,0xa1,0x01,0x09,0x03,0x15,0x00,0x26,0x00,0xff,
    0x75,0x08,0x95,0x40,0x81,0x02,0x09,0x04,0x15,0x00,0x26,0x00,0xff,
    0x75,0x08,0x95,0x40,0x91,0x02,0xc0
};
/* Captured by inspect_updater.py executing constructor 0x100091c0, PID 9018.
 * Command 5, read four bytes at 0x08014034. Empty payload CRC is 0xffff.
 * Windows adds a report-ID zero byte; IOHIDDeviceSetReport takes ID separately.
 */
static const uint8_t version_query[64] = {
    0x05,0x05,0,0,0,0x04,0,0xff,0xff,0x04,0,0,0,0x34,0x40,0x01,0x08
};
static const uint8_t identity_query[64] = {
    0x05,0x08,0,0,0,0x02,0,0xff,0xff,0x02
};
/* Address is the pinned Zero 2 Yichip section's entry, not a guessed location. */
static const uint8_t app_header_query[64] = {
    0x05,0x05,0,0,0,0x20,0,0xff,0xff,0x20,0,0,0,0,0x80,0x01,0x01
};
/* Pinned YC3121 SDK: BT_REV at 0xc8000, BT_STEP at 0xc8001.
 * Read only these two identification bytes, not adjacent control registers. */
static const uint8_t radio_id_query[64] = {
    0x05,0x05,0,0,0,0x02,0,0xff,0xff,0x02,0,0,0,0,0x80,0x0c,0
};
/* SYSCTRL_CLK_CLS from pinned SDK/datasheet; bit 13 gates the BT clock. */
static const uint8_t radio_clock_query[64] = {
    0x05,0x05,0,0,0,0x04,0,0xff,0xff,0x04,0,0,0,0x6c,0x85,0x0f,0
};

static void dump(const char *label, const uint8_t *data, CFIndex length) {
    printf("%s=", label);
    for (CFIndex i=0; i<length; ++i) printf("%02x", data[i]);
    putchar('\n');
    fflush(stdout);
}

static void input(void *context, IOReturn result, void *sender,
                  IOHIDReportType type, uint32_t report_id,
                  uint8_t *report, CFIndex length) {
    (void)context; (void)sender;
    printf("input_result=0x%08x type=%d report_id=%u length=%ld\n",
           (unsigned)result, (int)type, report_id, (long)length);
    if (result != kIOReturnSuccess || length < 0 || length > 64) return;
    dump("response", report, length);
    /* ReadHid strips Windows' report-ID byte. The observed protocol reply
     * itself starts with 00 05; keep the vendor's data offset 18 unchanged. */
    if (type == kIOHIDReportTypeInput && report_id == 0 && length >= 18 &&
        report[0] == 0 && report[1] == 5 &&
        report[4] == expected_command && report[5] == 0) {
        unsigned status = report[2] | ((unsigned)report[3] << 8);
        printf("protocol_status=%u\n", status);
        received = status ? -1 : 1;
        unsigned payload_bytes = report[6] | ((unsigned)report[7]<<8);
        if (!status &&
            (payload_bytes < expected_bytes || payload_bytes > 46 ||
             length < (CFIndex)(18 + payload_bytes) ||
             crc16(report+18, payload_bytes) != (report[8] | ((unsigned)report[9]<<8)) ||
             (expected_command == 5 &&
              (payload_bytes != expected_bytes || le32(report+10) != expected_bytes ||
               le32(report+14) != expected_address)))) {
            fprintf(stderr, "Read response length/address/CRC mismatch\n");
            received = -1;
        }
        if (received == 1 && length >= (CFIndex)(18 + expected_bytes)) {
            dump("query_data", report+18, expected_bytes);
            if (image && fwrite(report+18, 1, expected_bytes, image) != expected_bytes) received = -1;
        } else if (!status) received = -1;
    }
}

static void match_number(CFMutableDictionaryRef dict, CFStringRef key, int32_t value) {
    CFNumberRef number = CFNumberCreate(kCFAllocatorDefault, kCFNumberSInt32Type, &value);
    CFDictionarySetValue(dict, key, number);
    CFRelease(number);
}

int main(int argc, char **argv) {
    char *end = NULL;
    errno = 0;
    unsigned long location = argc >= 3 ? strtoul(argv[1], &end, 0) : 0;
    int rom_prefix = argc == 4 && !strcmp(argv[2], "arm-rom-prefix");
    int rom_bulk = argc == 4 && (!strcmp(argv[2], "arm-rom-api") || rom_prefix);
    int bulk = argc == 4 && (!strcmp(argv[2], "app-image") || rom_bulk);
    if ((!bulk && argc != 3) || errno || !end || end == argv[1] || *end || !location || location > UINT32_MAX ||
        (!bulk && strcmp(argv[2], "version") && strcmp(argv[2], "identity") &&
         strcmp(argv[2], "app-header") && strcmp(argv[2], "rom-header") &&
         strcmp(argv[2], "boot-entry") && strcmp(argv[2], "radio-id") &&
         strcmp(argv[2], "radio-clock") && strcmp(argv[2], "address-space-check"))) {
        fprintf(stderr, "Usage: %s USB_LOCATION_ID version|identity|app-header|rom-header|boot-entry|radio-id|radio-clock|address-space-check OR app-image|arm-rom-api|arm-rom-prefix OUTPUT_FILE\n", argv[0]);
        return 2;
    }
    expected_command = !strcmp(argv[2], "identity") ? 8 : 5;
    int radio_id = !strcmp(argv[2], "radio-id");
    int radio_clock = !strcmp(argv[2], "radio-clock");
    expected_bytes = expected_command == 8 || radio_id ? 2 :
        radio_clock || !strcmp(argv[2], "version") ? 4 : 32;
    /* INIT_OTP from pinned SDK/stock; flash boot entry from independently
     * captured ARM ROM BL instructions at 0x78c4 and 0x7904. */
    /* 0x20000 is documented RAM, but could be interpreted by the bootloader
     * as a flash offset alias of the already-captured 0x01020000 bytes. */
    expected_address = !strcmp(argv[2], "address-space-check") ? 0x20000 :
        radio_clock ? 0xf856c : radio_id ? 0xc8000 : !strcmp(argv[2], "boot-entry") ? 0x01000200 :
        !strcmp(argv[2], "rom-header") ? 0x442c :
        expected_bytes == 32 ? 0x01018000 : 0x08014034;
    const uint8_t *query = radio_clock ? radio_clock_query : radio_id ? radio_id_query : expected_command == 8 ? identity_query :
        expected_bytes == 32 ? app_header_query : version_query;
    CFMutableDictionaryRef match = CFDictionaryCreateMutable(kCFAllocatorDefault, 0,
        &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    match_number(match, CFSTR(kIOHIDVendorIDKey), 0x2dc8);
    match_number(match, CFSTR(kIOHIDProductIDKey), 0x3208);
    match_number(match, CFSTR(kIOHIDLocationIDKey), (int32_t)location);
    IOHIDManagerRef manager = IOHIDManagerCreate(kCFAllocatorDefault, kIOHIDOptionsTypeNone);
    IOHIDManagerSetDeviceMatching(manager, match);
    CFRelease(match);
    CFSetRef devices = IOHIDManagerCopyDevices(manager);
    if (!devices || CFSetGetCount(devices) != 1) {
        fprintf(stderr, "Expected exactly one matching bootloader at that USB location\n");
        if (devices) CFRelease(devices);
        CFRelease(manager);
        return 3;
    }
    IOHIDDeviceRef device;
    CFSetGetValues(devices, (const void **)&device);
    CFTypeRef product = IOHIDDeviceGetProperty(device, CFSTR(kIOHIDProductKey));
    CFTypeRef transport = IOHIDDeviceGetProperty(device, CFSTR(kIOHIDTransportKey));
    CFTypeRef desc = IOHIDDeviceGetProperty(device, CFSTR(kIOHIDReportDescriptorKey));
    if (!product || !CFEqual(product, CFSTR("8BitDo Boot")) ||
        !transport || !CFEqual(transport, CFSTR("USB")) ||
        !desc || CFGetTypeID(desc) != CFDataGetTypeID() ||
        CFDataGetLength(desc) != sizeof(descriptor) ||
        memcmp(CFDataGetBytePtr(desc), descriptor, sizeof(descriptor))) {
        fprintf(stderr, "Bootloader descriptor does not match observed device\n");
        CFRelease(devices); CFRelease(manager);
        return 4;
    }
    IOReturn status = IOHIDDeviceOpen(device, kIOHIDOptionsTypeNone);
    printf("open=0x%08x\n", (unsigned)status);
    if (status != kIOReturnSuccess) {
        CFRelease(devices); CFRelease(manager);
        return 5;
    }
    uint8_t incoming[64];
    IOHIDDeviceRegisterInputReportCallback(device, incoming, sizeof(incoming), input, NULL);
    IOHIDDeviceScheduleWithRunLoop(device, CFRunLoopGetCurrent(), kCFRunLoopDefaultMode);
    if (bulk) {
        image = fopen(argv[3], "wbx");
        if (!image) { perror("Create new readback file"); status = kIOReturnError; }
    }
    unsigned completed = 0;
    /* Application extent from stock header; API window covers SDK entries.
     * ARM ROM [0,0x8000) is documented in YC3121 (BT) V1.7, page 12.
     * A live read succeeded through 0x7f9f, then lost the boot connection.
     * Limit verification to that observed prefix; cause of exit is unknown.
     * None of these ranges includes peripheral space or the radio ROM. */
    uint32_t base = rom_prefix ? 0 : rom_bulk ? 0x4000 : 0x01018000;
    unsigned total = bulk ? (rom_prefix ? 0x7fa0 : rom_bulk ? 0x2000 : 0x11e00) : expected_bytes;
    while (status == kIOReturnSuccess && completed < total) {
        uint8_t packet[64]; memcpy(packet, query, 64);
        if (bulk) expected_address = base + completed;
        if (expected_command == 5) put32(packet+13, expected_address);
        received = 0;
        dump("request", packet, 64);
        status = IOHIDDeviceSetReport(device, kIOHIDReportTypeOutput, 0, packet, 64);
        printf("query_send=0x%08x\n", (unsigned)status);
        CFAbsoluteTime deadline = CFAbsoluteTimeGetCurrent() + 3.0;
        while (status == kIOReturnSuccess && !received && CFAbsoluteTimeGetCurrent() < deadline)
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.05, true);
        if (received != 1) break;
        completed += expected_bytes;
    }
    if (image && fclose(image)) { received = -1; perror("Close readback file"); }
    printf("completed_bytes=%u expected_bytes=%u\n", completed, total);
    IOHIDDeviceUnscheduleFromRunLoop(device, CFRunLoopGetCurrent(), kCFRunLoopDefaultMode);
    IOHIDDeviceClose(device, kIOHIDOptionsTypeNone);
    CFRelease(devices); CFRelease(manager);
    int success = received == 1 && completed == total && status == kIOReturnSuccess;
    printf("query_succeeded=%s\n", success ? "true" : "false");
    return success ? 0 : 6;
}
