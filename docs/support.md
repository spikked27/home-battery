# Support and confidence

| Feature | Scope |
|---|---|
| SUB/SBU labels | Panel-confirmed; SUB charging observed in the original installation |
| Serial configuration writes | Existing bridge whitelist and whole-snapshot readback verification |
| Full selector ranges | Bridge-advertised manual/site ranges, not every value physically tested |
| Charge currents | Battery-side DC interpretation from exact-model manual |
| Program 56 | Stored/readback validated; physical current-limiting effect unknown |
| BMS SOC/voltage threshold precedence | Not physically commissioned |
| Second-output timing | Configuration readable/editable; interactions not commissioned |
| Equalization | Inactive lead-acid settings; not a lithium charging strategy |
| Unknown priorities/codes | Neutral code labels; never guessed by scheduler |
| Battery temperature | From selected BMS sensor; not synthesized as inverter BMS temperature |
| Automatic switching | Only SUB/SBU; requires explicit commissioning switches |
| Charge target | Advisory; charging-off state not established |
| Capacity/runtime | Based on input capacity and reported SOC, not measured full capacity |
| Financial totals | Estimated cash flow, not verified utility bill savings |

The integration intentionally does not add firmware updates, raw serial command fields, arbitrary register writes or protocol brute force.
