"""Decode a captured Daly 0x98 response; never opens a port or writes settings."""
from datetime import datetime, timezone

VOLTAGE_CODES = ('cell_high_l1', 'cell_high_l2', 'cell_low_l1', 'cell_low_l2',
                 'pack_high_l1', 'pack_high_l2', 'pack_low_l1', 'pack_low_l2')

def decode_alarm_status(data):
    if not isinstance(data, (bytes, bytearray)) or len(data) != 8:
        raise ValueError('Expected eight-byte Daly 0x98 payload')
    codes = []
    for byte, value in enumerate(data):
        for bit in range(8):
            if value & (1 << bit):
                code = VOLTAGE_CODES[bit] if byte == 0 else (
                    {4: 'soc_high_l1', 5: 'soc_high_l2', 6: 'soc_low_l1', 7: 'soc_low_l2'}.get(bit)
                    if byte == 2 else None)
                codes.append(code or f'byte_{byte}_bit_{bit}')
    return {'alarm_codes': codes, 'raw_payload_hex': bytes(data).hex(),
            'source_command': '0x98', 'decoder_version': 1,
            'sampled_at': datetime.now(timezone.utc).isoformat()}

def alarm_text(status):
    labels = {'cell_high_l1': 'Cell voltage high (warning)',
              'cell_high_l2': 'Cell overvoltage protection',
              'cell_low_l1': 'Cell voltage low (warning)',
              'cell_low_l2': 'Cell undervoltage protection',
              'pack_high_l1': 'Pack voltage high (warning)',
              'pack_high_l2': 'Pack overvoltage protection',
              'pack_low_l1': 'Pack voltage low (warning)',
              'pack_low_l2': 'Pack undervoltage protection',
              'soc_high_l1': 'SOC high (warning)', 'soc_high_l2': 'SOC high (level 2)',
              'soc_low_l1': 'SOC low (warning)', 'soc_low_l2': 'SOC low (level 2)'}
    return '; '.join(labels.get(code, 'BMS fault ' + code) for code in status['alarm_codes']) or 'No alarms'
