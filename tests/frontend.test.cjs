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
assert(!flow({...base,inverter_pv_power:500}).includes('route chargeactive'),'Solar charging must not be attributed to utility');
assert(!flow({...base,inverter_pv_power:null}).includes('route chargeactive'),'Unknown solar power must not imply grid charging');
assert(flow({...base,inverter_pv_power:0}).includes('route chargeactive'),'Grid charging is shown when solar is measured zero');
assert(!flow({...base,inverter_pv_power:0,grid_voltage:0}).includes('route chargeactive'),'No utility arrow during outage');
assert(!flow({...base,inverter_pv_power:500}).includes('route batactive'),'Charging battery is not depicted supplying loads');
assert(flow({...base,charge_w:0,discharge_w:600}).includes('route batactive'),'Measured battery discharge activates the load arrow');
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
assert(reference.includes('Reference loads')&&!reference.includes('route batactive'),'Uncommissioned meter must not imply the inverter supplies those loads');
console.log('1 reference-meter attribution check passed');
const source=fs.readFileSync(path.join(__dirname,'../custom_components/home_battery/frontend.js'),'utf8');
const bucket=vm.runInNewContext(source+"\nbucketHistory([{t:0,v:100},{t:50,v:300},{t:100,v:300}],0,100,1)",{HTMLElement:class{},customElements:{define:()=>{}}});
assert.equal(bucket[0].v,200,'Bucket averages must weight time, not sample count');
assert.equal(bucket[0].lo,100);assert.equal(bucket[0].hi,300);
const reserve=Panel.prototype.statusStrip.call({}, {soc:33,reserve_soc:20,runtime_hours:4.5});
assert(reserve.includes('33%')&&reserve.includes('20%'),'Current battery and reserve must appear together');
const cells=Panel.prototype.cellChart.call({},{cells:[3.5,3.55,3.6]});
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

assert(source.includes("'test_load_mode','commissioned'"),'Backup plan exposes explicit test authorization');
assert(source.includes('Test-load scheduling is authorized; this meter remains a reference.'),'Test scheduling does not claim that the reference meter is connected');
console.log('2 test-load authorization presentation checks passed');
