"""Reduce parsed NTE Kismet code to skin/dye switching. Never touches game files."""
import base64
import copy
import json
from pathlib import Path
import re
import struct

ROOT = Path("tools/skin-unlock-analysis")
TYPE = "UAssetAPI.Kismet.Bytecode.Expressions."
def kind(x): return x["$type"].split(",")[0].split(".")[-1]
def expr(name, **kw): return {"$type": TYPE + name + ", UAssetAPI", **kw}

def main():
    parsed = json.loads((ROOT / "json-parsed/HT/Content/MOD/BP_Star.json").read_text(encoding="utf-8-sig"))
    original = json.loads((ROOT / "json/HT/Content/MOD/BP_Star.json").read_text(encoding="utf-8-sig"))
    rows = json.loads((ROOT / "ubergraph-addresses.json").read_text(encoding="utf-8"))
    records = {r["address"]: copy.deepcopy(r["expression"]) for r in rows}
    addresses = sorted(records)
    sizes = {a: b-a for a,b in zip(addresses, addresses[1:])}
    sizes[13500] = 2
    assert addresses[-1] == 13500
    # Keep input initialization; jump directly to the small skin notification widget.
    records[2985] = expr("EX_Jump", CodeOffset=3955)
    sizes[2985] = 5
    # Follow execution-flow stack semantics, keeping only reachable skin branches.
    roots = [207, 1576, 2936]
    pending = [(a, (13500,)) for a in roots]
    seen = set()
    kept = {0,5}
    next_address = {a:b for a,b in zip(addresses,addresses[1:])}
    while pending:
        address, stack = pending.pop()
        if (address,stack) in seen: continue
        seen.add((address,stack)); kept.add(address)
        x = records[address]; token = kind(x)
        def follow(a,s=stack):
            assert a in records, (address,token,a)
            pending.append((a,s))
        if token == "EX_Return": continue
        if token == "EX_Jump": follow(x["CodeOffset"])
        elif token == "EX_JumpIfNot":
            follow(x["CodeOffset"]); follow(next_address[address])
        elif token == "EX_PushExecutionFlow":
            assert len(stack)<20
            follow(next_address[address],stack+(x["PushingAddress"],))
        elif token in ("EX_PopExecutionFlow","EX_PopExecutionFlowIfNot"):
            assert stack, (address,token)
            follow(stack[-1],stack[:-1])
            if token.endswith("IfNot"): follow(next_address[address])
        else:
            assert token not in ("EX_ComputedJump","EX_EndOfScript")
            if address==2985: follow(3955)
            else: follow(next_address[address])
    ordered=sorted(kept)
    # Hide the old crosshair child, while retaining the clothing-change notification.
    hide=copy.deepcopy(records[92])
    geometry=copy.deepcopy(records[5224]["Expression"]["ObjectExpression"])
    hide["ObjectExpression"]=geometry
    assert kind(geometry)=="EX_Context"
    assert geometry["ContextExpression"]["Variable"]["New"]["Path"]==["zhong"]
    mapping={}; offset=0
    for address in ordered:
        mapping[address]=offset
        offset+=sizes[address]
        if address==4230: offset+=59 # Context(1+31+12+15) in VM memory
    def remap(x):
        if isinstance(x,dict):
            token=kind(x) if "$type" in x else ""
            if token in ("EX_Jump","EX_JumpIfNot"):x["CodeOffset"]=mapping[x["CodeOffset"]]
            elif token=="EX_PushExecutionFlow":x["PushingAddress"]=mapping[x["PushingAddress"]]
            for v in x.values():remap(v)
        elif isinstance(x,list):
            for v in x:remap(v)
    code=[]
    for address in ordered:
        x=copy.deepcopy(records[address]); remap(x)
        if address==4230:code.append(hide)
        code.append(x)
    code.append(expr("EX_EndOfScript"))
    parsed["Exports"][2]["ScriptBytecode"]=code
    inert=[expr("EX_Return",ReturnExpression=expr("EX_Nothing")),expr("EX_EndOfScript")]
    keep_events={15,17,28}
    for i in range(3,30):
        if i not in keep_events:
            parsed["Exports"][i]["ScriptBytecode"]=copy.deepcopy(inert)
        else:
            call=next(x for x in parsed["Exports"][i]["ScriptBytecode"] if kind(x)=="EX_LocalFinalFunction")
            call["Parameters"][0]["Value"]=mapping[call["Parameters"][0]["Value"]]
    forbidden=re.compile("K2_SetWorldLocation|K2_AddActorWorldOffset|K2_AddWorldOffset|K2_DestroyActor|SetEnableGravity|SaveGameToSlot|LoadGameFromSlot|CreateSaveGameObject|LineTraceSingleByProfile|Velocity|GetAIController|IsInputKeyDown")
    # Resolve imports as well as expression/property names in the retained body.
    retained_text="\n".join("\n".join(r["text"]) for r in rows if r["address"] in kept)
    assert not forbidden.search(retained_text),forbidden.findall(retained_text)
    data=base64.b64decode(original["Exports"][32]["Data"])
    count=struct.unpack_from("<I",data,2)[0]
    assert count==25 and len(data)==6+30*count+4
    bindings=[];report=[]
    for i in range(count):
        r=data[6+i*30:6+(i+1)*30]
        assert r[:7]==bytes.fromhex("800d02000b0003")
        key=original["NameMap"][struct.unpack_from("<I",r,7)[0]]
        function=original["NameMap"][struct.unpack_from("<I",r,19)[0]]
        if key in ("Equals","Hyphen"):
            assert function in ("InpActEvt_Equals_K2Node_InputKeyEvent","InpActEvt_Hyphen_K2Node_InputKeyEvent")
            bindings.append(r);report.append({"key":key,"function":function})
    assert len(bindings)==2
    new_bindings=data[:2]+struct.pack("<I",2)+b"".join(bindings)+data[-4:]
    (ROOT/"skin-bindings.base64").write_text(base64.b64encode(new_bindings).decode(),encoding="utf-8")
    (ROOT/"edited-functions.json").write_text(json.dumps(parsed,ensure_ascii=False,indent=2),encoding="utf-8")
    receipt={"original_instructions":len(rows)+1,"retained_original_instructions":len(kept),"new_instructions":len(code),"address_map":mapping,"bindings":report,"removed_input_events":23,"tick_disabled":True,"original_script_memory_size":13503,"new_script_memory_size":offset+1,"forbidden_calls_reachable":False}
    (ROOT/"skin-only-plan.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf-8")
    print({k:v for k,v in receipt.items() if k!="address_map"})

if __name__=="__main__":main()

