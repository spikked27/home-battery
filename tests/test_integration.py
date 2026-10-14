"""HA-backed configuration, transport and lifecycle checks; MQTT writes are mocked."""
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
import pytest_asyncio
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.exceptions import HomeAssistantError
from custom_components.home_battery.coordinator import BatteryCoordinator
from custom_components.home_battery.config_flow import validate_sources
from custom_components.home_battery.const import DOMAIN


@pytest_asyncio.fixture
async def coordinator(hass,monkeypatch):
    monkeypatch.setattr("custom_components.home_battery.coordinator.mqtt.is_connected",lambda _hass:True)
    entry=MockConfigEntry(domain=DOMAIN,title="Test battery",unique_id="lab/inverter",data={
        "mqtt_root":"lab/inverter","soc_entity":"sensor.soc","load_entity":"sensor.load",
        "charge_power_entity":"sensor.charge","discharge_power_entity":"sensor.drain","alarms_entity":"sensor.alarms"})
    entry.add_to_hass(hass)
    result=BatteryCoordinator(hass,entry)
    for entity,value,unit in [("soc",80,"%"),("load",500,"W"),("charge",0,"W"),("drain",600,"W")]:
        hass.states.async_set("sensor."+entity,value,{"unit_of_measurement":unit})
    hass.states.async_set("sensor.alarms","No alarms")
    result.topics.update({"status":{"status":"ready"},"raw_readings":{"HSTS":{"ascii":"(00 B010000 000 1000\r","age_seconds":0}},"telemetry/grid_voltage":"120",
                          "control/output_priority/attributes":{"allowed_values":["SUB","SBU"]},"control/output_priority/state":"SUB"})
    import time
    result.received.update({key:time.time() for key in ("status","raw_readings","telemetry/grid_voltage")})
    yield result
    await result.async_close()


def message(key,payload,retain=False):
    return SimpleNamespace(topic="lab/inverter/"+key,payload=json.dumps(payload) if isinstance(payload,dict) else payload,retain=retain)


async def test_source_units_are_validated(hass):
    hass.states.async_set("sensor.energy",2,{"unit_of_measurement":"kWh"})
    assert validate_sources(hass,{"load_entity":"sensor.energy"})=={"load_entity":"invalid_source"}
    hass.states.async_set("sensor.kw",.5,{"unit_of_measurement":"kW"})
    assert validate_sources(hass,{"load_entity":"sensor.kw"})=={}


async def test_discovery_preserves_renames_and_numeric_cell_order(hass):
    from custom_components.home_battery.discovery import suggested_sources
    entries={str(i):SimpleNamespace(platform="mqtt",disabled_by=None,device_id="battery",unique_id=unique,entity_id=entity)
        for i,(unique,entity) in enumerate([("daly_bms_soc","sensor.renamed_soc"),("daly_bms_cell_10_voltage","sensor.group_ten"),("daly_bms_cell_2_voltage","sensor.group_two"),("daly_bms_cell_1_voltage","sensor.group_one")])}
    with patch("custom_components.home_battery.discovery.er.async_get",return_value=SimpleNamespace(entities=entries)):
        found=suggested_sources(hass)
    assert found["soc_entity"]=="sensor.renamed_soc"
    assert found["cell_entities"]==["sensor.group_one","sensor.group_two","sensor.group_ten"]


async def test_discovery_does_not_pick_between_multiple_batteries(hass):
    from custom_components.home_battery.discovery import suggested_sources
    entries={key:SimpleNamespace(platform="mqtt",disabled_by=None,device_id=key,unique_id="daly_bms_soc",entity_id="sensor."+key) for key in ("one","two")}
    with patch("custom_components.home_battery.discovery.er.async_get",return_value=SimpleNamespace(entities=entries)):
        assert "soc_entity" not in suggested_sources(hass)


async def test_mqtt_root_detected_without_publish_and_listener_removed(hass):
    from custom_components.home_battery.discovery import detected_root
    from unittest.mock import Mock
    unsubscribe=Mock()
    async def subscribe(_hass,topic,callback):
        assert topic=="homeassistant/sensor/hpvinv09/telemetry_output_power/config"
        callback(SimpleNamespace(payload='{"state_topic":"test/inverter/telemetry/output_power"}'))
        return unsubscribe
    with (patch("custom_components.home_battery.discovery.mqtt.is_connected",return_value=True),
          patch("custom_components.home_battery.discovery.mqtt.async_subscribe",side_effect=subscribe),
          patch("custom_components.home_battery.discovery.mqtt.async_publish") as publish):
        assert await detected_root(hass)=="test/inverter"
    unsubscribe.assert_called_once()
    publish.assert_not_called()


async def test_retained_telemetry_cannot_establish_freshness(coordinator):
    coordinator.received.clear()
    coordinator._message(message("status",{"status":"ready"},True))
    assert not coordinator.measurements()["fresh"]


async def test_control_waits_for_result_and_confirmed_state(coordinator):
    async def publish(*args,**kwargs):
        assert args[1]=="lab/inverter/control/output_priority/set"
        assert args[2]=="SBU" and kwargs["retain"] is False and kwargs["qos"]==0
        coordinator._message(message("control/output_priority/state","SBU"))
        coordinator._message(message("last_result",{"control":"output_priority","status":"verified","timestamp":datetime.now(timezone.utc).isoformat()}))
    with patch("custom_components.home_battery.coordinator.mqtt.async_publish",side_effect=publish) as mocked:
        await coordinator.async_control("output_priority","SBU")
        assert mocked.call_count==1
    assert coordinator.pending is None and coordinator.command_error is None
    assert coordinator.hold_until>0


async def test_bridge_failure_latches_and_blocks_followup(coordinator):
    async def publish(*args,**kwargs):
        coordinator._message(message("last_result",{"control":"output_priority","status":"failed","error":"Readback mismatch","timestamp":datetime.now(timezone.utc).isoformat()}))
    with patch("custom_components.home_battery.coordinator.mqtt.async_publish",side_effect=publish):
        with pytest.raises(HomeAssistantError,match="Readback mismatch"):
            await coordinator.async_control("output_priority","SBU")
        with pytest.raises(HomeAssistantError,match="not ready"):
            await coordinator.async_control("output_priority","SBU")
    assert coordinator.command_error


async def test_charge_ceiling_even_if_bridge_advertises_more(coordinator):
    coordinator.topics["control/total_charge_current/attributes"]={"allowed_values":["40 A"]}
    with pytest.raises(HomeAssistantError,match="ceiling"):
        await coordinator.async_control("total_charge_current","40 A")


async def test_automatic_requires_commissioning(coordinator):
    with pytest.raises(HomeAssistantError,match="Confirm"):
        await coordinator.async_setting("automatic_enabled",True)


async def test_settings_update_without_restarting_serial_or_mqtt(coordinator):
    with patch.object(coordinator.hass.config_entries,"async_update_entry") as update:
        await coordinator.async_setting("backup_hours",3)
        assert coordinator.settings["backup_hours"]==3
        update.assert_called_once()


async def test_shutdown_persists_accounting_without_command(coordinator):
    with patch.object(coordinator.store,"async_save",new_callable=AsyncMock) as save:
        await coordinator.async_close()
        assert coordinator.stopped
        assert save.call_args.args[0]["ledger"]["avoided"]==0


async def test_unconfigured_optional_sensors_are_none(coordinator):
    d=coordinator.measurements()
    assert d["temperature"] is None and d["cells"]==[]
    assert d["fresh"] and d["healthy"]


async def test_nonzero_inverter_status_pauses_planning(coordinator):
    coordinator.topics["raw_readings"]["HSTS"]["ascii"]="(61 L010000 000 1000\r"
    assert not coordinator.measurements()["healthy"]
    coordinator.recompute()
    assert coordinator.data["plan"]=="Paused"


async def test_stale_hsts_not_rejuvenated_by_new_raw_publication(coordinator):
    coordinator.topics["raw_readings"]["HSTS"]["age_seconds"]=80
    assert not coordinator.measurements()["fresh"]


async def test_malformed_mqtt_json_ignored(coordinator):
    before=dict(coordinator.topics)
    coordinator._message(SimpleNamespace(topic="lab/inverter/status",payload="[]",retain=False))
    assert coordinator.topics==before


async def test_setup_unload_registers_panel_and_removes_runtime(hass,coordinator):
    from custom_components.home_battery import async_setup_entry, async_unload_entry
    hass.data[DOMAIN]={}
    with (patch("custom_components.home_battery.coordinator.BatteryCoordinator.async_start",new_callable=AsyncMock),
          patch.object(hass.config_entries,"async_forward_entry_setups",new_callable=AsyncMock) as forward,
          patch("custom_components.home_battery.panel_custom.async_register_panel",new_callable=AsyncMock) as panel,
          patch.object(hass.config_entries,"async_unload_platforms",new_callable=AsyncMock,return_value=True),
          patch("custom_components.home_battery.frontend.async_remove_panel") as remove):
        assert await async_setup_entry(hass,coordinator.entry)
        assert coordinator.entry.entry_id in hass.data[DOMAIN]
        assert panel.call_args.kwargs["webcomponent_name"]=="home-battery-panel"
        assert len(forward.call_args.args[1])==6
        assert await async_unload_entry(hass,coordinator.entry)
        assert coordinator.entry.entry_id not in hass.data[DOMAIN]
        remove.assert_called_once()


async def test_configuration_entities_use_enum_categories(coordinator):
    from homeassistant.const import EntityCategory
    from custom_components.home_battery.number import BatteryNumber
    from custom_components.home_battery.select import BatterySelect,InverterSelect
    from custom_components.home_battery.switch import BatterySwitch
    from custom_components.home_battery.sensor import BatterySensor
    entities=[BatteryNumber(coordinator,"backup_hours","Backup",1,10,1,"h"),
              BatterySelect(coordinator,"planning_goal","Priority"),
              InverterSelect(coordinator,"output_priority","Source"),
              BatterySwitch(coordinator,"automatic_enabled","Automatic"),
              BatterySensor(coordinator,"bridge_status","Bridge",None,None,None)]
    for entity in entities:
        assert isinstance(entity.entity_category,EntityCategory)
        assert entity.entity_category.value in {"config","diagnostic"}


async def test_live_heartbeat_keeps_unchanged_zero_valid(coordinator):
    import time
    old=time.time()
    coordinator.sources["battery_heartbeat_topic"]="bms/state/voltage"
    coordinator.source_seen["battery_heartbeat_topic"]=old+200
    with patch("custom_components.home_battery.coordinator.time.time",return_value=old+200):
        assert coordinator.entity_number("charge_power_entity",{"W"})==0
        coordinator.source_seen.clear()
        assert coordinator.entity_number("charge_power_entity",{"W"}) is None


async def test_unloaded_integration_cannot_transmit(coordinator):
    coordinator.stopped=True
    with patch("custom_components.home_battery.coordinator.mqtt.async_publish") as publish:
        with pytest.raises(HomeAssistantError,match="unloaded"):
            await coordinator.async_control("output_priority","SBU")
        publish.assert_not_called()


async def test_cash_and_energy_accounting_exclude_stale_gaps(coordinator):
    import time
    clock=time.time()
    coordinator.settings.update(price_source="Manual prices",manual_super_rate=.1,manual_off_rate=.2,manual_peak_rate=.3)
    with patch.object(coordinator,"fetch_context",new_callable=AsyncMock):
        with patch("custom_components.home_battery.coordinator.time.time",return_value=clock):
            await coordinator.async_tick()
        with patch("custom_components.home_battery.coordinator.time.time",return_value=clock+30):
            await coordinator.async_tick()
        assert coordinator.ledger["avoided"]>0
        assert coordinator.ledger["energy_out"]==pytest.approx(.005)
        before=coordinator.ledger["avoided"]
        with patch("custom_components.home_battery.coordinator.time.time",return_value=clock+300):
            await coordinator.async_tick()
        assert coordinator.ledger["avoided"]==before
        assert coordinator.ledger["energy_out"]==pytest.approx(.005)


async def test_fresh_nws_all_clear_does_not_expire_with_unchanged_entity(coordinator):
    import time
    coordinator.sources.update(nws_alert_zone="NYZ080",alert_entity="sensor.stale_alerts")
    coordinator.hass.states.async_set("sensor.stale_alerts",0)
    coordinator.nws_seen=time.time()
    assert coordinator.storm()==(False,"Automatic advice")
    coordinator.nws_alerts=["High Wind Warning"]
    assert coordinator.storm()[0]
    coordinator.nws_seen=0
    assert coordinator.storm()==(True,"Automatic advice: alerts stale, reserve held")


async def test_disconnected_mqtt_never_queues_commands(coordinator):
    with (patch("custom_components.home_battery.coordinator.mqtt.is_connected",return_value=False),
          patch("custom_components.home_battery.coordinator.mqtt.async_publish") as publish):
        with pytest.raises(HomeAssistantError,match="disconnected"):
            await coordinator.async_control("output_priority","SBU")
        publish.assert_not_called()


async def test_mqtt_burst_queues_one_ui_refresh(coordinator):
    with patch.object(coordinator,"recompute") as recompute:
        coordinator._message(message("telemetry/grid_voltage","121"))
        handle=coordinator.refresh_handle
        coordinator._message(message("telemetry/output_power","501"))
        assert coordinator.refresh_handle is handle
        recompute.assert_not_called()
        handle.cancel();coordinator.refresh_handle=None


async def test_manual_same_value_still_verified_by_bridge(coordinator):
    coordinator.topics["control/output_priority/state"]="SBU"
    async def publish(*args,**kwargs):
        coordinator._message(message("last_result",{"control":"output_priority","status":"verified_no_change","timestamp":datetime.now(timezone.utc).isoformat()}))
    with patch("custom_components.home_battery.coordinator.mqtt.async_publish",side_effect=publish) as publish:
        await coordinator.async_control("output_priority","SBU")
        publish.assert_called_once()


async def test_unavailable_weather_is_not_an_all_clear(coordinator):
    coordinator.sources["weather_entity"]="weather.failed"
    coordinator.hass.states.async_set("weather.failed","unavailable")
    assert coordinator.storm()==(True,"Automatic advice: weather stale, reserve held")
