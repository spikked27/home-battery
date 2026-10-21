"""Presentation and evidence only. No option values, commands or device access."""

# Name, manual program, explanation, confidence in meaning (not every setting value).
CATALOG = {
 'output_priority': ('Preferred power source', 1,
  'SUB: solar, then grid, then battery. SBU: solar, then battery, then grid. Switching to SUB started charging in this setup with SNU selected. Source preference does not independently enable or disable charging. Code 02 remains unidentified.', 'Confirmed for SUB/SBU; code 02 unknown'),
 'charger_priority': ('Allowed charging sources', 16,
  'SNU permits solar and utility charging. Code 02 stopped utility charging during a no-PV test and corresponds to the manual solar-only candidate; PV charging in that mode has not been physically tested. Charging permission is separate from actual AC load source.', 'Confirmed: SNU and utility-charge inhibition with code 02; solar behavior uncommissioned'),
 'utility_charge_current': ('Grid-to-battery charge limit (DC)', 11,
  'Maximum battery-side DC amps supplied by the grid charger. It counts toward the total charge limit in program 02. A lower total limit takes precedence. This is not AC amps drawn from the breaker.', 'High confidence: exact-model manual'),
 'total_charge_current': ('Total battery charge limit (DC)', 2,
  'Maximum combined solar and grid charging current at the battery, in DC amps. This does not include AC load current or set emergency battery-output power. Both charge selectors retain the 30 A DC site ceiling.', 'High confidence: exact-model manual'),
 'back_to_grid_voltage': ('Use grid below battery voltage', 12,
  'Low battery voltage threshold for transferring loads to available grid power in SBU mode. Battery/BMS mode can affect whether voltage or SOC thresholds apply.', 'High confidence: manual; transfer behavior not commissioned'),
 'back_to_battery_voltage': ('Resume battery above voltage', 13,
  'Recovery battery voltage threshold for returning loads to battery preference in SBU mode. This is not a charge-voltage target. BMS mode may change applicability.', 'High confidence: manual; transfer behavior not commissioned'),
 'display_auto_return': ('Return panel to main screen', 19,
  'Automatically return the inverter display to its main information screen.', 'High confidence: manual and stored setting'),
 'backlight': ('Panel backlight', 20, 'Enable the inverter display backlight.', 'High confidence: manual and stored setting'),
 'buzzer': ('Inverter alarm sound', 18, 'Enable the inverter audible alarm.', 'High confidence: manual and stored setting'),
 'equalization_voltage': ('Equalization voltage (inactive)', 31,
  'Stored lead-acid equalization voltage. Equalization is disabled in the current lithium/BMS profile; this is not the normal lithium charge voltage.', 'High confidence: manual; inactive in current profile'),
 'equalization_duration': ('Equalization hold time (inactive)', 33,
  'Stored lead-acid equalization duration in minutes; inactive in the current profile.', 'High confidence: manual; inactive in current profile'),
 'equalization_timeout': ('Equalization time limit (inactive)', 34,
  'Stored lead-acid equalization timeout in minutes; inactive in the current profile.', 'High confidence: manual; inactive in current profile'),
 'equalization_interval': ('Equalization interval (inactive)', 35,
  'Stored number of days between lead-acid equalization cycles; inactive in the current profile.', 'High confidence: manual; inactive in current profile'),
 'bms_shutdown_soc': ('Stop battery use below SOC', 38,
  'Low-SOC shutdown threshold using BMS-reported state of charge. The reported SOC is currently uncalibrated; this is not a validated backup-runtime reserve.', 'High confidence: manual; shutdown behavior not commissioned'),
 'grid_current_parameter': ('Grid-tie current (effect unverified)', 56,
  'The manual calls this GRID-tie current, in AC amps. The value can be stored and read back; its effect on this firmware has not been measured. Do not use it as a total AC supply or backup-output limit. The 32 A selector cap does not enforce a 32 A input budget.', 'Moderate confidence: label established; physical effect unverified'),
 'second_output_recovery_soc': ('Second output: restore above SOC', 64,
  'BMS SOC threshold for restoring the second AC output. Its terminal behavior and interaction with other conditions have not been commissioned.', 'High confidence: manual; physical behavior unverified'),
 'second_output_recovery_delay': ('Second output: restore delay', 66,
  'Delay in minutes before restoring the second AC output. Exact timing and interactions remain unverified.', 'High confidence: manual; physical behavior unverified'),
 'source_notification': ('Beep when primary source is lost', 22,
  'Manual: alarm when the primary source is interrupted. This is an inverter beep, not a Home Assistant notification.', 'High confidence: manual; trigger behavior unverified'),
 'overload_restart': ('Auto-restart after overload', 6,
  'Permit automatic inverter restart after an overload shutdown. This does not change its output rating.', 'High confidence: manual; fault recovery not commissioned'),
 'overtemperature_restart': ('Auto-restart after overheating', 7,
  'Permit automatic inverter restart after an overtemperature shutdown and recovery.', 'High confidence: manual; fault recovery not commissioned'),
 'bms_return_battery_soc': ('Resume battery above SOC', 40,
  'BMS SOC recovery threshold. Values 25/60/90/95 were accepted with full readback. Lowering it enabled one observed transfer, but repeated SUB-to-SBU tests remained on utility; this setting alone does not guarantee transfer.', 'High confidence: recovery purpose; repeatable physical transfer unresolved'),
 'bms_return_utility_soc': ('Use grid below battery SOC', 39,
  'BMS-reported SOC threshold for transferring to available grid power. Its precedence over voltage thresholds in the current BMS profile remains unverified.', 'High confidence: manual; transfer behavior not commissioned'),
 'second_output_discharge_duration': ('Second output: battery runtime limit', 65,
  'Timer in minutes for second-output operation while discharging. Zero disables this timer. The exact start/reset conditions and terminal behavior remain unverified.', 'High confidence: manual; timer behavior unverified'),
 'ac_input_range': ('Accepted grid-voltage range (code)', 3,
  'The manual lists UPS (95-145 V) and APL (65-145 V) for this 120 V model. The remote code-to-label mapping has not been panel-confirmed, so numeric codes are preserved. This is not a current limit.', 'High confidence for manual ranges; remote code mapping unknown'),
 'bms_restart_soc': ('Minimum battery SOC for startup', 41,
  'Manual: BMS SOC for startup. Whether this permits automatic restart or gates a manual start has not been established.', 'Moderate confidence: startup meaning; exact behavior unverified'),
}

CONTROL_NAMES = {key: item[0] for key, item in CATALOG.items()}
CONTROL_DETAILS = {key: {'manual_program': item[1], 'description': item[2],
                        'meaning_confidence': item[3],
                        'verification_scope': 'Consult verified_values for tested stored values; readback alone does not verify physical behavior.'}
                   for key, item in CATALOG.items()}
for _key in ('utility_charge_current', 'total_charge_current'):
 CONTROL_DETAILS[_key]['measurement_side'] = 'Battery DC'
CONTROL_DETAILS['grid_current_parameter']['measurement_side'] = 'Grid-tie AC (manual label)'
