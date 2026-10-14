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
