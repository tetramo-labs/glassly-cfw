"""Fixed storage preflight queries; no arbitrary RAM/key/bus access or writes."""
import re
import struct
import zlib
from memomind_flash_read import (FlashReadClient, FlashReadError,
                                FlashReadProtocolError, DIAGNOSTIC_PROFILE, FULL_STORE_PROFILE, CANARY_PROFILE)

DIAGNOSTIC_PROFILES = (DIAGNOSTIC_PROFILE, FULL_STORE_PROFILE, CANARY_PROFILE)

TOPOLOGY_LIMITS = {
    'consistent': 1, 'xip0Initialized': 1, 'xip1Initialized': 1,
    'xip0Driver': 3, 'xip1Driver': 3,
    'xip0QuadConfigured': 1, 'xip1QuadConfigured': 1,
    'xip1ProbeValid': 1, 'xip1LegacyId': 65535, 'sharedC8ProbeValid': 1,
    'generalSpiBackendKnown': 1, 'generalSpiReady': 1,
    'generalSpiMutexPresent': 1, 'generalSpiSemaphorePresent': 1,
    'generalSpi0Configured': 3, 'generalSpiPinsMatch': 1,
    'cus8ContextPresent': 1, 'cus8ValidatedPackageState': 255,
}

def _identity(result):
    if (not isinstance(result,dict) or result.get('glassly')!='flash-read'
            or type(result.get('abi')) is not int or result['abi']!=1 or result.get('result')!='ok'):
        raise FlashReadProtocolError('Unexpected diagnostic identity')

def validate_topology(result):
    _identity(result)
    if set(result) != {'glassly', 'abi', 'result', 'diagnostic', *TOPOLOGY_LIMITS}:
        raise FlashReadProtocolError('Unexpected topology fields')
    if result['diagnostic'] != 'topology':
        raise FlashReadProtocolError('Unexpected diagnostic type')
    for key, maximum in TOPOLOGY_LIMITS.items():
        if type(result[key]) is not int or not 0 <= result[key] <= maximum:
            raise FlashReadProtocolError('Invalid topology field: ' + key)
    if ((not result['xip1ProbeValid'] and result['xip1LegacyId']) or
            (result['xip1ProbeValid'] and result['xip1Driver'] != 1)):
        raise FlashReadProtocolError('Legacy ID lacks a valid device-specific probe')
    # consistent=0 is recorded evidence, never silently promoted to a preflight pass.

def validate_badmap(result):
    _identity(result)
    keys={'glassly','abi','result','diagnostic','kvStatus','actualLength','recordState','mapHex','recordHex'}
    if set(result)!=keys or result['diagnostic']!='badmap':
        raise FlashReadProtocolError('Unexpected badmap fields')
    for key in ('kvStatus','actualLength'):
        if type(result[key]) is not int or not 0<=result[key]<=0xffffffff:
            raise FlashReadProtocolError('Invalid badmap field: '+key)
    state=result['recordState'];status=result['kvStatus'];length=result['actualLength']
    for key in ('mapHex','recordHex'):
        if not isinstance(result[key],str) or re.fullmatch('[0-9a-f]*',result[key]) is None:
            raise FlashReadProtocolError('Invalid badmap hex')
    if state=='present':
        if status!=0 or length!=116 or len(result['recordHex'])!=232 or len(result['mapHex'])!=192:
            raise FlashReadProtocolError('Invalid present-record envelope')
        raw=bytes.fromhex(result['recordHex']);bitmap=bytes.fromhex(result['mapHex'])
        if (struct.unpack('<4I',raw[:16])!=(0x474d4231,1,0x01500000,0x00300000)
                or raw[16:112]!=bitmap or bitmap[:2]!=bytes(2)
                or zlib.crc32(raw[:112])!=struct.unpack('<I',raw[112:])[0]):
            raise FlashReadProtocolError('Badmap record failed independent integrity/identity check')
    elif state=='absent':
        if status!=7 or length!=0 or result['recordHex'] or result['mapHex']!='00'*96:
            raise FlashReadProtocolError('Invalid native-default absence envelope')
    elif state in ('invalid','unavailable'):
        if result['mapHex'] or result['recordHex'] or (status!=0 if state=='invalid' else status in (0,7)):
            raise FlashReadProtocolError('Invalid failed-record envelope')
    else:
        raise FlashReadProtocolError('Unknown badmap record state')

def tail_unavailable_map(result):
    validate_badmap(result)
    if result['recordState'] not in ('present','absent'):
        raise FlashReadError('No validated effective physical badmap is available')
    return bytes.fromhex(result['mapHex'])[64:96]

class StorageDiagnosticClient(FlashReadClient):
    def __init__(self, transport, *, timeout=10, profile=DIAGNOSTIC_PROFILE):
        if profile not in DIAGNOSTIC_PROFILES:
            raise ValueError("Profile does not expose storage diagnostics")
        super().__init__(transport, timeout=timeout, profile=profile)

    def topology(self):
        if not self.verified:
            raise FlashReadError('Query and verify the diagnostic profile first')
        return self._request(b'\x02', validate_topology)

    def badmap(self):
        if not self.verified:
            raise FlashReadError('Query and verify the diagnostic profile first')
        return self._request(b'\x03', validate_badmap)
