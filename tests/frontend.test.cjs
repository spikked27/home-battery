/* Exercise actual panel rendering without browser, network or device commands. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
let Panel;
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../custom_components/home_battery/frontend.js'),'utf8'),{
  HTMLElement:class{},customElements:{define:(_name,type)=>{Panel=type;}}
});
const flow=data=>Panel.prototype.flow.call({},data);
const base={mode:'Battery',fresh:true,grid_voltage:120,soc:60,load_w:500,charge_w:200,discharge_w:0};
assert(flow({...base,inverter_pv_power:500}).includes('data-source="solar" data-target="inverter" class="route solaractive"'),'Measured solar generation feeds the inverter');
assert(!flow({...base,inverter_pv_power:null}).includes('route gridactive'),'Unknown solar and available utility do not prove utility supply in Battery mode');
assert(flow({...base,mode:'Line',inverter_pv_power:0}).includes('route gridactive'),'Actual Line mode shows utility input');
assert(!flow({...base,mode:'Line',grid_voltage:0}).includes('route gridactive'),'No utility arrow during outage');
assert(!flow({...base,inverter_pv_power:500}).includes('route batactive'),'Charging battery is not depicted supplying the inverter');
assert(flow({...base,charge_w:0,discharge_w:600}).includes('route batactive'),'Measured discharge in Battery mode activates the inverter supply arrow');
console.log('6 native power-flow rendering checks passed');
const now=Date.now();
const panel=Object.assign(Object.create(Panel.prototype),{historyHours:24,trends:{spread:[{t:now-86400000,v:.1},{t:now-43200000,v:null},{t:now-21600000,v:.2},{t:now,v:.2}]}});
const graph=panel.trendGraph('spread','Cell difference trend','mV','#fbbf24',1000);
assert(graph.includes('200 mV'),'Cell difference is converted from volts into millivolts');
assert.equal((graph.match(/<g fill="none"[^>]*>(.*?)<\/g>/)[1].match(/<path /g)||[]).length,2,'Unavailable interval must break the plotted series');
const missing=Object.assign(Object.create(Panel.prototype),{trends:{}}).trendGraph('load','Critical-load usage','W','#a78bfa');
assert(missing.includes('Waiting for recorded history'),'Empty history explains what is missing');
console.log('3 history rendering checks passed');
assert.equal(vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../custom_components/home_battery/frontend.js'),'utf8')+"\nhistoryFactor('load','kW')",{HTMLElement:class{},customElements:{define:()=>{}}}),1000,'kW load source history must display as W');
console.log('1 load-history unit conversion check passed');
const reference=Panel.prototype.flow.call({model:{settings:{commissioned:false}}},{...base,charge_w:0,discharge_w:600});
assert(reference.includes('Measured AC output')&&reference.includes('route batactive')&&!reference.includes('Reference loads'),'Show verified inverter supply independently of reference-meter commissioning');
console.log('1 reference-meter attribution check passed');
const source=fs.readFileSync(path.join(__dirname,'../custom_components/home_battery/frontend.js'),'utf8');
const bucket=vm.runInNewContext(source+"\nbucketHistory([{t:0,v:100},{t:50,v:300},{t:100,v:300}],0,100,1)",{HTMLElement:class{},customElements:{define:()=>{}}});
assert.equal(bucket[0].v,200,'Bucket averages must weight time, not sample count');
assert.equal(bucket[0].lo,100);assert.equal(bucket[0].hi,300);
const reserve=Panel.prototype.statusStrip.call({}, {soc:33,reserve_soc:20,runtime_hours:4.5});
assert(reserve.includes('33%')&&reserve.includes('20%'),'Current battery and reserve must appear together');
const cells=Panel.prototype.cellChart.call({},{cells:[3.5,3.55,3.6],cell_voltage_limits:{low:2.75,high:4.2}});
assert.equal((cells.match(/data-cell="/g)||[]).length,3,'Every cell gets its own vertical bar');
assert(cells.includes('All bars share'),'Comparison must disclose the common scale');
console.log('4 visual hierarchy and bucket checks passed');

const radar=fs.readFileSync('custom_components/home_battery/map/index.html','utf8');
const pathMatcher=radar.match(/filter\(f=>\/(.+?)\/\.test\(f.path\)/);
assert(pathMatcher,'Radar frame validation is present');
const framePattern=new RegExp(pathMatcher[1]);
assert(framePattern.test('/v2/radar/301654572b9d'),'Current hash frame paths supported');
assert(framePattern.test('/v2/radar/1792070400'),'Legacy numeric frames supported');
assert(!framePattern.test('/v2/radar/../../private'),'Traversal rejected');
assert(radar.includes('name="referrer" content="origin"'),'Basemap receives origin referrer without location query');
console.log('4 radar compatibility checks passed');

const waiting=Panel.prototype.transferNotice.call({}, {mode:'Line',source_transfer:{value:'SBU'}});
assert(waiting.includes('Waiting for inverter transfer')&&waiting.includes('Line'),'Waiting keeps actual source visible');
assert(!waiting.includes('class="error"'),'Expected recovery delay is not a fault banner');
assert.equal(Panel.prototype.transferNotice.call({}, {command_result:'Battery operation verified'}),'','Successful transfers do not leave a permanent banner');
const paused=Panel.prototype.transferNotice.call({}, {scheduler_status:'Fault latched'});
assert(paused.includes('Advanced')&&paused.includes('role="alert"'),'Real faults remain visible with a diagnostic destination');
console.log('4 transfer-status presentation checks passed');

assert(!source.includes('test_load_mode'),'Normal scheduling has no separate test mode');
assert(source.includes('Scheduling uses this selected meter for reserve and price planning.'),'Reference planning is explained without blocking normal scheduling');
console.log('2 normal scheduling presentation checks passed');

const chargeHeld=Panel.prototype.transferNotice.call({}, {utility_charging_blocked:true,charge_guard_status:'Charge target reached',has_bms_alarm:false});
assert(chargeHeld.includes('Utility charging paused')&&chargeHeld.includes('role="status"'),'Target stop is a normal state, not an error');
assert(chargeHeld.includes('Source control is shown separately'),'Charge stop is distinguished from load transfer');
const protectionHeld=Panel.prototype.transferNotice.call({}, {utility_charging_blocked:true,charge_guard_status:'BMS alarm',has_bms_alarm:true});
assert(protectionHeld.includes('role="alert"'),'BMS protection stays visible');
assert(!source.includes('Charge target (model assumption)'),'The implemented charge stop is no longer described as advisory');
console.log('4 charging-safeguard presentation checks passed');
const recovering=Panel.prototype.transferNotice.call({}, {utility_charging_blocked:true,charge_guard_status:'BMS alarm',has_bms_alarm:true,high_charge_recovery:true});
assert(recovering.includes('BMS permits recovery discharge; charging stays off.'),'Explain directional recovery without hiding the alarm');
console.log('1 directional recovery presentation check passed');

const helpers=vm.runInNewContext(source+'\n({bucketHistory,mergeHistory})',{HTMLElement:class{},customElements:{define:()=>{}}});
const shortGap=helpers.bucketHistory([{t:0,v:1},{t:30,v:null},{t:31,v:2},{t:60,v:2}],0,60,1);
assert.equal(shortGap.filter(r=>r.v!==null).length,2,'A short outage must not erase the valid portions of its bucket');
assert.equal(shortGap.find(r=>r.v===null).from,30);assert.equal(shortGap.find(r=>r.v===null).to,31);
assert.equal(shortGap.filter(r=>r.v!==null).reduce((n,r)=>n+r.ms,0),59,'Preserve all measured time around the actual gap');
const recent=helpers.mergeHistory([{t:0,v:-1.4}],[{t:10000,v:5.9},{t:20000,v:5.9}]);
assert.equal(recent.at(-1).v,5.9,'Live charging samples extend cached discharging history');
const charging=Object.assign(Object.create(Panel.prototype),{model:{data:{current:5.9}},currentHistory:[{t:now-86400000,v:-1.4},{t:now-30000,v:-1.4}],liveTrends:{current:[{t:now-20000,v:5.9},{t:now,v:5.9}]}}).currentGraph();
assert(charging.includes('Charging · 5.9 A'),'Live charge direction must be explicit');
assert(charging.includes('aria-label="Live reading"'),'Show the current sample even before a full average bucket accumulates');
const noHistory=Object.assign(Object.create(Panel.prototype),{model:{data:{current:5.9}}}).currentGraph();
assert(noHistory.includes('Charging · 5.9 A'),'Live charging remains visible when historical data is missing');
console.log('8 gap precision and live-current checks passed');
(async()=>{
 const saved=[{t:now-10000,v:1.4},{t:now,v:1.4}];
 const offline=Object.assign(Object.create(Panel.prototype),{model:{history_sources:{current:'sensor.current'},entities:{recorded_savings_total:'sensor.money'}},trends:{current:saved},_hass:{states:{},callApi:async()=>{throw Error('offline')},callWS:async()=>({})}});
 await offline.history();assert.strictEqual(offline.trends.current,saved,'Transient history API failure must preserve the last successful data');
 assert(offline.historyErrors.current,'History refresh failure remains distinguishable from missing recordings');
 console.log('2 history refresh recovery checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});

const isolated=Panel.prototype.flow.call({model:{settings:{commissioned:false}}},{...base,charge_w:0,discharge_w:72,inverter_output_power:7});
assert(isolated.includes('7 W AC')&&isolated.includes('72 W DC'),'AC output and battery-side draw remain separate');
assert(isolated.includes('marker-end="url(#hb-bat-arrow)"'),'Active battery path has an explicit visible arrowhead');
assert(isolated.includes('fill="#fbbf24"')&&!isolated.includes('context-stroke'),'Arrowheads use explicit colors supported across browsers');
const chargePath=flow({...base,mode:'Line',inverter_pv_power:0});
assert(chargePath.includes('data-source="inverter" data-target="battery" class="route chargeactive"'),'Charging arrow points from inverter into battery');
const stale=flow({...base,fresh:false,mode:'Line',inverter_pv_power:0});
assert(!/class="route (grid|bat|charge|solar)active"/.test(stale),'Stale readings cannot activate energy arrows');
assert(stale.includes('Unknown')&&stale.includes('Waiting for live readings'),'Stale flow is labeled instead of declaring an outage');
const fieldPanel=Object.assign(Object.create(Panel.prototype),{model:{entities:{limit:'number.limit',auto:'switch.auto'}},_hass:{states:{'number.limit':{state:'unavailable',attributes:{friendly_name:'Home Battery Current limit',min:2,max:30,step:1}},'switch.auto':{state:'unavailable',attributes:{friendly_name:'Home Battery Automatic scheduling'}}}}});
assert(fieldPanel.field('limit').includes('disabled')&&fieldPanel.field('auto').includes('disabled'),'Unavailable controls cannot be edited');
assert(fieldPanel.field('limit').includes('Current limit')&&!fieldPanel.field('limit').includes('Battery Current limit'),'Control labels remove only the integration prefix');
const unknownHealth=Panel.prototype.health.call({model:{attributes:{}},tile:Panel.prototype.tile,cellChart:()=>''},{fresh:false,healthy:false,alarms:'No alarms',cells:[],cell_spread:null});
assert(unknownHealth.includes('Waiting for live readings')&&!unknownHealth.includes('0 mV'),'Missing battery data must not look like zero cell difference or a healthy status');
const stylesheet=fs.readFileSync('custom_components/home_battery/charts.css','utf8');
assert(stylesheet.includes('prefers-reduced-motion')&&stylesheet.includes('energy-travel'),'Animated directional flow respects reduced-motion preferences');
console.log('10 whole-dashboard state and control checks passed');

const lookup=vm.runInNewContext(source+'\nhistoryAt',{HTMLElement:class{},customElements:{define:()=>{}}});
const events=[{t:100,v:1.234},{t:200,v:null},{t:300,v:-5.678}];
assert.equal(lookup(events,99),null,'No invented data before the first recording');
assert.equal(lookup(events,150).v,1.234,'Hover uses recorded precision, not a bucket average');
assert.equal(lookup(events,250),null,'Do not bridge unavailable intervals');
assert.equal(lookup(events,300).v,-5.678,'Keep signed discharge values');
assert(graph.includes('data-chart="spread"')&&graph.includes('chart-tooltip'),'History charts expose pointer inspection');
assert(graph.includes('tabindex="0"'),'History inspection is keyboard accessible');
const bounds={low:2.75,high:4.2};
const fixed1=Panel.prototype.cellChart.call({},{cells:[3.5,3.55],cell_voltage_limits:bounds});
const fixed2=Panel.prototype.cellChart.call({},{cells:[4.01,4.02],cell_voltage_limits:bounds});
assert(fixed1.includes('2.75–4.2 V')&&fixed2.includes('2.75–4.2 V'),'Cell scale remains fixed as measured voltages change');
assert(!fixed1.includes('data-cell-scale'),'No automatic or arbitrary detail scale');
assert(Panel.prototype.cellChart.call({},{cells:[4.3],cell_voltage_limits:bounds}).includes('Outside BMS limits'),'Out-of-range readings are identified without expanding the scale');
assert(Panel.prototype.cellChart.call({},{cells:[4.0]}).includes('Waiting for configured BMS'),'Do not guess voltage limits for an unknown chemistry');
console.log('10 hover and fixed-voltage-scale checks passed');

const learningPanel=Object.assign(Object.create(Panel.prototype),{model:{entities:{own:'sensor.renamed_derived'},sources:{load_entity:'sensor.closet'},settings:{learning_history_days:14},learning:{status:'Ready',available_days:12,history_days:14,coverage_percent:86,typical_error_w:24,validation_hours:48,expected_daily_kwh:6}},_hass:{states:{'sensor.closet':{state:'250',attributes:{friendly_name:'IT closet',unit_of_measurement:'W'}},'sensor.panel':{state:'.8',attributes:{friendly_name:'Critical panel',unit_of_measurement:'kW'}},'sensor.daily':{state:'4',attributes:{friendly_name:'Daily energy',unit_of_measurement:'kWh'}},'sensor.renamed_derived':{state:'55',attributes:{unit_of_measurement:'W'}}}}});
assert.equal(learningPanel.loadCandidates().length,2,'Offer only external power sensors, not energy totals or our own renamed sensors');
assert.equal(learningPanel.loadCandidates('critical')[0][0],'sensor.panel','Search by human readable name');
const learningCard=learningPanel.learningSummary();
assert(learningCard.includes('IT closet')&&learningCard.includes('12 days')&&learningCard.includes('14 days'),'Name the source and actual available history');
assert(learningCard.includes('24 W')&&learningCard.includes('48 checked hours'),'Explain real held-out prediction error');
const loadForm=learningPanel.loadSetup();
assert(loadForm.includes('What should this battery power?')&&loadForm.includes('Save & learn'),'Plain language learning setup');
assert(loadForm.includes('14 days — recommended')&&loadForm.includes('90 days'),'Offer understandable history choices');
assert(loadForm.includes('pauses automatic scheduling'),'Explain the consequence of selecting a different meter');
assert(!learningCard.includes('guaranteed'),'Do not promise guaranteed savings or prediction accuracy');
console.log('8 load selection and learning presentation checks passed');
for(const id of ['sensor.it_closet_battery_planning_load','sensor.daly_bms_battery_power','sensor.renamed_bms_dc'])learningPanel._hass.states[id]={state:'500',attributes:{unit_of_measurement:'W',friendly_name:'Battery estimate'}};
learningPanel.model.excluded_load_entities=['sensor.renamed_bms_dc'];
assert.equal(learningPanel.loadCandidates().length,2,'Do not offer legacy estimates or BMS DC sensors, including renamed device entities');
assert.equal(learningPanel.loadCandidates()[0][0],'sensor.closet','Put the currently selected load first');
console.log('2 measured-load candidate boundary checks passed');

learningPanel.model.entities.planning_goal='select.preference';
learningPanel.model.settings.planning_goal='More Savings';
learningPanel._hass.states['select.preference']={state:'More Savings',attributes:{}};
const preferences=learningPanel.savingsPreference();
assert.equal((preferences.match(/data-profile=/g)||[]).length,3,'Offer the three savings preferences');
assert.equal((preferences.match(/aria-pressed="true"/g)||[]).length,1,'Show exactly one selected preference');
assert(preferences.includes('requested backup time')&&!preferences.includes('50% more')&&!preferences.includes('minimum reserve'),'All profiles honor one explicit backup-hours target');
assert(preferences.includes('all profiles use live load readings'),'Do not wait for learning to finish');
learningPanel.model.settings.automatic_enabled=true;
assert(learningPanel.learningSummary(true).includes('Automatic scheduling enabled · Live-load planning'),'Show enabled scheduling with live fallback');
learningPanel.model.data={peak_forecast_wh:2000};
assert(learningPanel.learningSummary(true).includes('Learned peak planning'),'Only describe a forecast as controlling planning when it passes backend gates');
learningPanel._hass.states['select.preference'].state='unavailable';
assert.equal((learningPanel.savingsPreference().match(/ disabled/g)||[]).length,3,'Disable profile actions when the select is unavailable');
console.log('7 savings preference and learning fallback checks passed');

const timelinePanel=Object.create(Panel.prototype),start=Date.UTC(2026,9,23,18)/1000;
const timeline={status:'Estimated',timezone:'America/New_York',start,end:start+86400,basis:'Current-load estimate',profile:'More Savings',message:'Updates with conditions.',assumptions:'Not a command queue.',points:[{t:start,soc:80,reserve:20},{t:start+86400,soc:70,reserve:20}],segments:[{start,end:start+3600,action:'battery',tariff:'Peak',price:.5,soc_start:80,soc_end:70,reason:'Reserve protected'},{start:start+3600,end:start+86400,action:'utility',tariff:'Off-peak',price:.2,soc_start:70,soc_end:70,reason:'Save for peak'}]};
const timelineCard=timelinePanel.anticipatedSchedule({schedule_preview:timeline});
assert(timelineCard.includes('Next 24 hours')&&timelineCard.includes('Use battery now'),'Make the next action readable at a glance');
assert(timelineCard.includes('Use utility around')&&timelineCard.includes('Fri'),'Name the next change with a local day and time');
assert.equal((timelineCard.match(/data-schedule-step=/g)||[]).length,2,'Each planned period is inspectable');
assert(timelineCard.includes('80% → 70%')&&timelineCard.includes('Dashed: outage reserve'),'Show estimated SOC and reserve together');
assert(timelineCard.includes('Current-load estimate')&&timelineCard.includes('Estimated, not fixed'),'Disclose fallback and uncertainty');
assert(timelineCard.includes('scroll horizontally')&&timelineCard.includes('tabindex="0"'),'Allow accessible horizontal navigation on mobile');
const pausedSchedule=timelinePanel.anticipatedSchedule({schedule_preview:{status:'Paused',message:'Manual hold',segments:[]}});
assert(pausedSchedule.includes('Manual hold')&&!pausedSchedule.includes('Use battery now'),'Never present a paused controller as active');
console.log('7 anticipated schedule rendering checks passed');

const groupPeriods=vm.runInNewContext(source+'\nschedulePeriods',{HTMLElement:class{},customElements:{define:()=>{}}});
const splitUtility={...timeline,segments:[timeline.segments[0],
 {...timeline.segments[1],end:start+7200,reason:'Allocation used'},
 {...timeline.segments[1],start:start+7200,reason:'Backup time covered',tariff:'Peak',price:.5,soc_end:68}
]};
const originalSegments=JSON.stringify(splitUtility.segments),grouped=groupPeriods(splitUtility);
assert.equal(grouped.length,2,'Adjacent utility periods are one visible action despite different reasons and rates');
assert.equal(grouped[1].start,start+3600);assert.equal(grouped[1].end,start+86400);
assert.equal(grouped[1].soc_end,68,'Merged period preserves the final forecast SOC');
assert(grouped[1].reason.includes('Allocation used')&&grouped[1].reason.includes('Backup time covered'),'Keep both explanations in period details');
assert.equal(grouped[1].tariff,'Mixed rates','Do not mislabel a period that crosses tariffs');
assert.equal(JSON.stringify(splitUtility.segments),originalSegments,'Presentation grouping must not mutate controller data');
assert.equal((timelinePanel.anticipatedSchedule({schedule_preview:splitUtility}).match(/data-schedule-step=/g)||[]).length,2,'Render only the grouped periods');
timelinePanel.scheduleSelectedTime=start+8000;
assert.equal(timelinePanel.selectedScheduleIndex(splitUtility),1,'Retain a selected time when reason boundaries are merged');
assert.equal(groupPeriods({segments:[splitUtility.segments[1],{...splitUtility.segments[2],start:start+7300}]}).length,2,'Do not bridge missing forecast time');
console.log('10 action-based timeline grouping checks passed');

const coldPanel=Object.assign(Object.create(Panel.prototype),{model:{settings:{thermal_enabled:true,thermal_extra_budget:.25}},field:key=>`control:${key}`});
const coldCard=coldPanel.thermalCard({thermal:{status:'Waiting for colder hours',temperature_c:12,delay_until:start,cost_today:.02,message:'Needed charging only',model:{passive_hours:40,heat_credit_used:false}}});
assert(coldCard.includes('12 °C')&&coldCard.includes('Waiting for colder hours'),'Put measured temperature beside cold-weather status');
assert(coldCard.includes('thermal_enabled')&&coldCard.includes('thermal_availability')&&coldCard.includes('thermal_extra_budget'),'Show timing, availability and spending controls together');
assert(coldCard.includes('no predicted heating')&&coldCard.includes('No discharge-current commands'),'Do not imply heating or arbitrary discharge control');
assert(!coldPanel.thermalCard({thermal:{}},true).includes('control:'),'Compact main/weather card does not duplicate configuration controls');
console.log('4 cold-weather dashboard checks passed');

const scheduleOff=Panel.prototype.transferNotice.call({}, {scheduler_status:'Observe only'});
assert(scheduleOff.includes('Automatic scheduling is off')&&scheduleOff.includes('scheduled source changes will not run'),'Do not confuse a recommendation with an enabled schedule');
const costPanel=Object.assign(Object.create(Panel.prototype),{field:()=>'',model:{settings:{commissioned:false,capacity_kwh:5.2,charge_target:95},attributes:{projected_savings_day:{baseline_cost_day:1.65,operating_cost_day:1.35,load_kwh_day:7.16,shifted_kwh_day:3.1,charge_limit_a:9}}}});
const costs=costPanel.savings({reserve_soc:20,projected_savings_day:.3,projected_savings_month:9,projected_savings_year:110,current_price:.518,overnight_price:.128,tariff:'Peak'});
assert(costs.includes('Cost without battery')&&costs.includes('Cost with battery'),'Explain the purchases behind net savings');
assert(costs.includes('3.9 kWh DC')&&costs.includes('At current prices'),'Expose the usable energy budget and current-rate assumption');
assert(!costPanel.savings({reserve_soc:null}).includes('4.94 kWh DC'),'An unknown reserve must not be treated as zero');
console.log('4 savings explanation and disabled-schedule checks passed');

assert(!source.includes('minimum_reserve'),'Do not present a second percentage reserve setting');
const hoursReserve=Panel.prototype.statusStrip.call({model:{settings:{backup_hours:2}}},{soc:80,reserve_soc:17.5,runtime_hours:10});
assert(hoursReserve.includes('2 h target')&&hoursReserve.includes('calculated reserve'),'Explain the hours-to-percentage relationship beside battery SOC');
console.log('2 hours-only reserve presentation checks passed');

assert(!source.includes('adds backup headroom immediately'),'No stale claim of an implicit backup-hours multiplier');

// A real render replaces the timeline DOM. Simulate that browser boundary,
// including focus events, rather than only checking generated HTML strings.
const inspection=Object.assign(Object.create(Panel.prototype),{
 tab:'overview',renderedTab:'overview',scrollTop:640,
 model:{version:'test',settings:{commissioned:false},data:{schedule_preview:timeline}},
 overview:()=>'',statusStrip:()=>'',transferNotice:()=>'',historyRange:()=>'',
 learningSummary:()=>'',trendGraph:()=>'',currentGraph:()=>'',
 bindControls(){this.bindSchedule();}
});
let timelineNodes,regionNode,detailNode,rootHTML;
const inspectionRoot={activeElement:null,
 querySelectorAll:q=>q==='[data-schedule-step]'?timelineNodes:[],
 querySelector:q=>q==='.schedule-scroll'?regionNode:q==='[data-schedule-detail]'?detailNode:q.startsWith('[data-schedule-step=')?timelineNodes[Number(q.match(/"(\d+)"/)[1])]:null
};
Object.defineProperty(inspectionRoot,'innerHTML',{get:()=>rootHTML,set:v=>{
 rootHTML=v;inspectionRoot.activeElement=null;regionNode=inspection.model.data.schedule_preview.segments.length?{scrollLeft:0}:null;detailNode={textContent:''};
 timelineNodes=inspection.model.data.schedule_preview.segments.map((_,i)=>({
  dataset:{scheduleStep:String(i)},attrs:{},tagName:'BUTTON',
  hasAttribute:name=>name==='data-schedule-step',setAttribute(k,v){this.attrs[k]=v;},
  focus(options){assert(options.preventScroll);inspectionRoot.activeElement=this;this.onfocus?.();}
 }));
}});
inspection.shadowRoot=inspectionRoot;inspectionRoot.innerHTML='initial';inspection.bindSchedule();
timelineNodes[1].onclick();regionNode.scrollLeft=320;inspectionRoot.activeElement=timelineNodes[1];
const selectedClock=inspection.scheduleSelectedTime;
timelineNodes[0].onpointerenter?.({pointerType:'touch'});
assert.equal(inspection.scheduleSelectedTime,selectedClock,'A touch/layout pointer-enter must not overwrite an explicitly selected future period');
timelineNodes[0].onpointerenter?.({pointerType:'mouse'});
timelineNodes[0].onfocus?.();
assert.equal(inspection.scheduleSelectedTime,selectedClock,'Hover and restored focus cannot change an explicit selection');
inspection.render();
assert.equal(regionNode.scrollLeft,320,'A telemetry render must preserve horizontal timeline position');
assert.equal(inspection.scrollTop,640,'A telemetry render must preserve page position');
assert.equal(timelineNodes[1].attrs['aria-pressed'],'true','Keep the selected later period after refresh');
assert(detailNode.textContent.includes('Use utility'),'Keep later-period details instead of resetting to the first period');
assert.equal(inspectionRoot.activeElement,timelineNodes[1],'Restore keyboard focus without scrolling');
inspection.model.data.schedule_preview={...timeline,start:start+10,segments:[
 {...timeline.segments[0],start:start+10},
 {...timeline.segments[1],end:start+7200},
 {...timeline.segments[1],start:start+7200,action:'charge'}
]};
inspection.render();
assert.equal(inspection.scheduleSelectedTime,selectedClock,'Keep the inspected clock time when forecast boundaries change');
assert.equal(timelineNodes[2].attrs['aria-pressed'],'true','Follow the clock time across a split, not the old segment index');
assert(detailNode.textContent.includes('Charge battery'),'Show the newly forecast action at the selected time');
inspection.model.data.schedule_preview={segments:[]};
inspection.render();
assert.equal(inspection.scheduleSelectedTime,selectedClock,'A temporarily unavailable forecast must not erase the inspected time');
inspection.model.data.schedule_preview=timeline;
inspection.render();
assert.equal(timelineNodes[1].attrs['aria-pressed'],'true','Restore the selected period when forecast data returns');
assert.equal(regionNode.scrollLeft,320,'Restore horizontal position when forecast data returns');

// A newly created HA panel must recover UI state for this entry without
// leaking it into another installation. No device settings are involved.
inspection._panel={config:{entry_id:'timeline-entry'}};
inspection.scheduleScrollLeft=320;inspection.saveScheduleView();
const remounted=Object.assign(Object.create(Panel.prototype),{refresh(){}});
remounted.panel={config:{entry_id:'timeline-entry'}};
assert.equal(remounted.scheduleSelectedTime,selectedClock,'HA remount preserves the inspected clock time');
assert.equal(remounted.scheduleScrollLeft,320,'HA remount preserves the timeline scroll offset');
remounted.panel={config:{entry_id:'another-entry'}};
assert.equal(remounted.scheduleSelectedTime,null,'Separate entries do not share a selection');
assert.equal(remounted.scheduleScrollLeft,0,'Separate entries do not share a scroll offset');
inspection.scheduleSelectedTime=start-10;
assert.equal(inspection.selectedScheduleIndex(inspection.model.data.schedule_preview),0,'An expired time falls back to the current period');
assert.equal(inspection.scheduleSelectedTime,null,'Do not keep an expired inspection anchor');
console.log('19 timeline refresh, interaction and remount continuity checks passed');

(async()=>{
 const input={tagName:'INPUT',blur(){actionRoot.activeElement=null;}},actionRoot={activeElement:null};
 const saving=Object.assign(Object.create(Panel.prototype),{shadowRoot:actionRoot,model:{entities:{backup_hours:'number.hours'}},
  _hass:{callService:async()=>{}},refresh:async()=>{assert.equal(actionRoot.activeElement,null,'Saved input must not block fresh savings rendering');},error:'old'});
 actionRoot.activeElement=input;await saving.action('backup_hours','number','set_value',{value:1});
 assert.equal(saving.error,'');
 const other={tagName:'INPUT'};actionRoot.activeElement=input;
 saving._hass.callService=async()=>{actionRoot.activeElement=other;};saving.refresh=async()=>{};
 await saving.action('backup_hours','number','set_value',{value:2});
 assert.equal(actionRoot.activeElement,other,'Do not steal focus if the user has moved to another input');
 let releasePoll,calls=0;
 const polling=Object.assign(Object.create(Panel.prototype),{_panel:{config:{entry_id:'test'}},_hass:{callWS:async()=>{
  calls++;if(calls===1)await new Promise(resolve=>{releasePoll=resolve;});return {data:{}};
 }},loading:false,captureLive:()=>{},history:async()=>{},render:()=>{}});
 const first=polling.refresh();await polling.refresh();releasePoll();await first;
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(calls,2,'A save during polling must request a follow-up refresh instead of disappearing');
 console.log('4 settings-save refresh checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});

const patchDOM=vm.runInNewContext(source+'\npatchLiveDOM',{HTMLElement:class{},customElements:{define:()=>{}}});
class TestDOMNode {
 constructor(tag,attrs={},children=[]){this.nodeType=tag==='#text'?3:tag==='#root'?11:1;this.localName=tag;this.namespaceURI='html';this.values={...attrs};this.childNodes=[];this.nodeValue='';for(const c of children)this.insertBefore(c,null);}
 get id(){return this.values.id||'';}get attributes(){return Object.entries(this.values).map(([name,value])=>({name,value}));}
 hasAttribute(k){return k in this.values;}getAttribute(k){return this.values[k]??null;}setAttribute(k,v){this.values[k]=v;}removeAttribute(k){delete this.values[k];}
 get firstChild(){return this.childNodes[0]||null;}get nextSibling(){return this.parent?.childNodes[this.parent.childNodes.indexOf(this)+1]||null;}
 insertBefore(node,before){if(node.parent)node.parent.removeChild(node);const index=before?this.childNodes.indexOf(before):this.childNodes.length;this.childNodes.splice(index,0,node);node.parent=this;}
 removeChild(node){this.childNodes.splice(this.childNodes.indexOf(node),1);node.parent=null;}
 cloneNode(){const n=new TestDOMNode(this.localName,this.values,this.childNodes.map(c=>c.cloneNode(true)));n.nodeValue=this.nodeValue;return n;}
}
const textNode=value=>{const n=new TestDOMNode('#text');n.nodeValue=value;return n;};
const oldRegion=new TestDOMNode('div',{class:'schedule-scroll'},[new TestDOMNode('button',{class:'schedule-step battery'},[textNode('old time')])]);
oldRegion.scrollLeft=231;
const oldDetails=new TestDOMNode('details',{open:''},[textNode('Help')]);
const oldCard=new TestDOMNode('section',{class:'schedule-card'},[oldRegion,oldDetails]);
const liveRoot=new TestDOMNode('#root',{},[new TestDOMNode('main',{},[oldCard])]);
const newCard=new TestDOMNode('section',{class:'schedule-card'},[new TestDOMNode('div',{class:'schedule-scroll'},[new TestDOMNode('button',{class:'schedule-step battery'},[textNode('new time')])]),new TestDOMNode('details',{},[textNode('Updated help')])]);
patchDOM(liveRoot,new TestDOMNode('#root',{},[new TestDOMNode('main',{},[new TestDOMNode('p',{class:'note'},[textNode('New notice')]),newCard])]));
assert.equal(liveRoot.firstChild.childNodes[1],oldCard,'Retain the actual timeline card when an earlier notice is inserted');
assert.equal(oldCard.firstChild,oldRegion,'Retain the actual scrolling element, not a replacement with a restored offset');
assert.equal(oldRegion.scrollLeft,231,'Preserve native scroll state through data updates');
assert.equal(oldRegion.firstChild.firstChild.nodeValue,'new time','Retaining the timeline must still update its forecast');
assert(oldDetails.hasAttribute('open'),'Keep the user-expanded explanation open across updates');
patchDOM(liveRoot,new TestDOMNode('#root',{},[new TestDOMNode('main',{},[newCard])]));
assert.equal(liveRoot.firstChild.firstChild,oldCard,'Removing a transient notice must not recreate the timeline');
assert.equal(liveRoot.firstChild.childNodes.length,1,'Remove stale siblings after reconciliation');
assert.equal(Panel.prototype.scheduleLabel({purpose:'reserve_recovery',action:'charge'}),'Restore backup','Distinguish reserve recovery from cheap-price charging');
console.log('8 persistent timeline DOM and recovery-label checks passed');

assert.equal(vm.runInNewContext(source+'\nPANEL_VERSION',{HTMLElement:class{},customElements:{define:()=>{}}}),JSON.parse(fs.readFileSync('custom_components/home_battery/manifest.json','utf8')).version,'The dashboard must identify its own loaded bundle version accurately');

const allowanceStatus=Panel.prototype.statusStrip.call({model:{settings:{backup_hours:1}}},{soc:8,reserve_soc:9,runtime_hours:1.1,storm:false});
assert(allowanceStatus.includes('Backup time covered')&&!allowanceStatus.includes('soc-fill low'),'Do not call a consumed planning allowance a failed outage target');
assert(Panel.prototype.statusStrip.call({model:{settings:{backup_hours:1}}},{soc:8,reserve_soc:50,runtime_hours:1.1,storm:true}).includes('Below reserve'),'Storm reserve remains authoritative');
const limitedReserve=Panel.prototype.statusStrip.call({model:{settings:{backup_hours:1}}},{soc:70,reserve_soc:20,runtime_hours:8,reserve_details:{inverter_floor_active:true,inverter_grid_soc:20,inverter_shutdown_soc:10}});
assert(limitedReserve.includes('Inverter grid floor 20%'),'Explain the effective inverter floor next to the single hours target');
assert(limitedReserve.includes('bottom 10%'),'Do not promise inaccessible shutdown energy as outage runtime');
