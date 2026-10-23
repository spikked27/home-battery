"""Supervisory utility-charge inhibition; BMS protections remain authoritative.

This cannot stop PV charging, operate without HA/MQTT, or replace a BMS.
Only latches persist; recovery must be observed again after each restart.
"""
from .policy import numeric

CHARGE_OFF = 'Solar only (utility charging disabled)'
CHARGE_ON = 'SNU (solar + utility)'
RECOVERY_SECONDS = 180


class ChargeGuard:
    def __init__(self, saved=None):
        self.target_latched = bool((saved or {}).get('target_latched'))
        self.cell_latched = bool((saved or {}).get('cell_latched'))
        self.alarm_latched = bool((saved or {}).get('alarm_latched'))
        self.safe_since = None
        self.reason = 'Waiting for fresh battery readings'

    def saved(self):
        return {'target_latched': self.target_latched, 'cell_latched': self.cell_latched,
                'alarm_latched': self.alarm_latched}

    def evaluate(self, data, settings, now):
        soc = numeric(data.get('soc'))
        ceiling = settings.get('charge_cell_ceiling', 0)
        cells = data.get('cells', [])
        complete = bool(cells) and all(numeric(v) is not None and 0 < v < 5 for v in cells)
        high = max(cells) if complete else None
        if data.get('fresh') and soc is not None and soc >= settings['charge_target']:
            self.target_latched = True
        if ceiling and high is not None and high >= ceiling:
            self.cell_latched = True
        if data.get('fresh') and (not data.get('healthy') or data.get('has_bms_alarm')):
            self.alarm_latched = True
        if not data.get('fresh') or soc is None or not 0 <= soc <= 100:
            reason = 'Waiting for fresh battery readings'
        elif not data.get('healthy') or data.get('has_bms_alarm'):
            reason = 'BMS alarm or inverter fault: utility charging blocked'
        elif ceiling and not complete:
            reason = 'Cell readings unavailable: utility charging blocked'
        elif self.target_latched and soc > settings['charge_target'] - 5:
            reason = 'Charge target reached; recharge below target minus 5%'
        elif self.cell_latched and (not ceiling or high is None):
            reason = 'Cell ceiling recovery cannot be verified'
        elif self.cell_latched and high > ceiling - .05:
            reason = 'Cell ceiling reached; waiting for 50 mV recovery'
        else:
            reason = ''
        recovering = self.target_latched or self.cell_latched or self.alarm_latched
        if reason:
            self.safe_since = None
        elif recovering:
            if self.safe_since is None:
                self.safe_since = now
            if now - self.safe_since < RECOVERY_SECONDS:
                reason = 'Recovery readings must stay clear for 3 minutes'
            else:
                self.target_latched = self.cell_latched = self.alarm_latched = False
        self.reason = reason
        return reason
