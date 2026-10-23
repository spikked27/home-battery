"""Daly diagnostic decoder: captured protection frame and distinct voltage bits."""
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('alarm_decoder',Path(__file__).parents[1]/'bridge/daly_alarm_status.py')
decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)

@pytest.mark.parametrize('bit,code',enumerate(['cell_high_l1','cell_high_l2','cell_low_l1','cell_low_l2','pack_high_l1','pack_high_l2','pack_low_l1','pack_low_l2']))
def test_voltage_bits_have_distinct_meanings(bit,code):
    assert decoder.decode_alarm_status(bytes([1<<bit])+bytes(7))['alarm_codes']==[code]

def test_captured_cell_protection_is_not_soc_warning():
    result=decoder.decode_alarm_status(bytes.fromhex('0200000000000000'))
    assert result['alarm_codes']==['cell_high_l2']
    assert decoder.alarm_text(result)=='Cell overvoltage protection'

def test_unknown_fault_never_silently_cleared():
    assert decoder.decode_alarm_status(bytes(7)+b'\x80')['alarm_codes']==['byte_7_bit_7']

@pytest.mark.parametrize('payload',[False,b'',bytes(7),bytes(9)])
def test_malformed_response_rejected(payload):
    with pytest.raises(ValueError): decoder.decode_alarm_status(payload)
