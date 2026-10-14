"""Extend the reduced skin blueprint with reflected role getters and setters.

Works only on staged, previously decoded assets; never edits a game directory.
Requires the local UAssetAPI measurement helper used by the skin-only build.
"""
import copy
import json
import subprocess
from pathlib import Path

ROOT = Path('tools/skin-unlock-analysis')
TOOL = ROOT / 'SkinOnlyTool/bin/Release/net8.0/SkinOnlyTool.exe'
TYPE = 'UAssetAPI.Kismet.Bytecode.Expressions.'

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def expr(name, **fields):
    return {'$type': TYPE + name + ', UAssetAPI', **fields}

def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)

def main():
    asset = read(ROOT / 'universal/base-functions.json')
    old_measure = read(ROOT / 'universal/base-measure.json')
    records = {r['address']: r['expression'] for r in read(ROOT / 'ubergraph-addresses.json')}
    old_map = {int(k): v for k, v in read(ROOT / 'skin-only-plan.json')['address_map'].items()}
    exports = asset['Exports']
    code = exports[2]['ScriptBytecode']
    positions = {v: i for i, v in enumerate(old_measure['2']['addresses'])}
    at = lambda original: positions[old_map[original]]

    def add_import(name, template, outer):
        entry = copy.deepcopy(asset['Imports'][template])
        entry.update(ObjectName=name, OuterIndex=outer)
        asset['Imports'].append(entry)
        if name not in asset['NameMap']:
            asset['NameMap'].append(name)
        return -len(asset['Imports'])

    controller = add_import('HTPlayerController', 33, -125)
    actor_getter = add_import('GetPlayerCharacter', 62, controller)
    role_getter = add_import('GetCurrentDisplayCharacterID', 62, -34)
    empty = copy.deepcopy(exports[30]['ScriptBytecode'][9]['RValuePointer'])

    def context(target, child, pointer=None):
        return expr('EX_Context', ObjectExpression=copy.deepcopy(target), Offset=0,
                    PropertyType=0, RValuePointer=copy.deepcopy(pointer or empty),
                    ContextExpression=child)

    def actor(pointer=None):
        pc = expr('EX_CallMath', StackNode=-63,
                  Parameters=[expr('EX_Self'), expr('EX_IntConst', Value=0)])
        cast = expr('EX_DynamicCast', ClassPtr=controller, Target=pc)
        return context(cast, expr('EX_FinalFunction', StackNode=actor_getter, Parameters=[]), pointer)

    def role():
        cast = expr('EX_DynamicCast', ClassPtr=-34, Target=actor())
        return context(cast, expr('EX_FinalFunction', StackNode=role_getter, Parameters=[]),
                       records[443]['Value'])

    code[at(207)]['AssignmentExpression'] = actor(code[at(207)]['VariableExpression']['Variable'])
    for old in (233, 270, 311, 366, 406):
        code[at(old)] = expr('EX_Nothing')
    code[at(443)]['Expression'] = role()
    # BeginPlay still enables the two input keys, then returns without creating
    # the original on-screen shortcut widget. Suppress its text update helper too.
    code[at(2985)] = expr('EX_Jump', CodeOffset=old_map[13500])
    exports[31]['ScriptBytecode'] = [expr('EX_Return', ReturnExpression=expr('EX_Nothing')),
                                   expr('EX_EndOfScript')]

    mesh = copy.deepcopy(exports[30]['ScriptBytecode'])
    mesh[0]['AssignmentExpression'] = actor(mesh[0]['VariableExpression']['Variable'])
    # Preserve the original mod's proven refresh route. The protected native
    # SetFashionDyeData body cannot establish whether it refreshes a mesh itself.
    # Save the genuine old struct before replacing fields, then pass that old
    # value to the existing OnRep callback (never pass the new value as old).
    capture = expr('EX_Let', Value=copy.deepcopy(empty),
                   Variable=copy.deepcopy(mesh[6]['Expression']),
                   Expression=copy.deepcopy(mesh[6]['Variable']))
    # Keep the original temporary construction without erasing the captured old
    # value: write the two selected fields directly into the actor's live struct.
    assignments = []
    for source in mesh[4:6]:
        assignment = copy.deepcopy(source)
        assignment['Variable']['StructExpression'] = copy.deepcopy(mesh[6]['Variable'])
        assignments.append(assignment)
    mesh[8]['ContextExpression']['Parameters'] = [copy.deepcopy(capture['Variable'])]
    mesh[9]['ContextExpression']['Parameters'][2] = copy.deepcopy(records[443]['Variable'])
    # Preserve the original appearance option mask; introduce only the role ID
    # parameter required by the shared player-character material interface.
    exports[30]['ScriptBytecode'] = mesh[:4] + [capture] + assignments + mesh[7:]

    length = copy.deepcopy(records[470]['Expression'])
    # The helper has no ubergraph locals: use an empty result pointer for this nested getter.
    length['RValuePointer'] = copy.deepcopy(empty)
    nonempty = copy.deepcopy(records[1264]['AssignmentExpression'])
    nonempty['Parameters'] = [length, expr('EX_IntConst', Value=1)]
    equal = copy.deepcopy(records[1197]['AssignmentExpression'])
    equal['Parameters'][0] = role()
    event_targets = {}
    def call(entry):
        return expr('EX_LocalFinalFunction', StackNode=3,
                    Parameters=[expr('EX_IntConst', Value=old_map[entry])])
    for index, action in ((17, 207), (15, 1576)):
        reset_outfit = copy.deepcopy(records[1400])
        reset_outfit['Expression'] = expr('EX_IntConst', Value=0)
        reset_dye = copy.deepcopy(code[at(15)])
        body = [expr('EX_JumpIfNot', CodeOffset=0, BooleanExpression=copy.deepcopy(nonempty)),
                expr('EX_JumpIfNot', CodeOffset=0, BooleanExpression=copy.deepcopy(equal)),
                expr('EX_Jump', CodeOffset=0), reset_outfit, reset_dye, call(207),
                expr('EX_JumpIfNot', CodeOffset=0, BooleanExpression=copy.deepcopy(nonempty)),
                expr('EX_LocalFinalFunction', StackNode=31, Parameters=[]),
                expr('EX_JumpIfNot', CodeOffset=0, BooleanExpression=copy.deepcopy(nonempty)),
                call(action), expr('EX_Return', ReturnExpression=expr('EX_Nothing')),
                expr('EX_EndOfScript')]
        exports[index]['ScriptBytecode'] = body
        event_targets[index] = {0: 3, 1: 3, 2: 8, 6: 10, 8: 10}

    path = ROOT / 'edited-functions.json'
    path.write_text(json.dumps(asset, ensure_ascii=False), encoding='utf-8')
    subprocess.run([str(TOOL), str(ROOT), 'measure'], check=True)
    asset = read(path)
    measure = read(ROOT / 'universal-measure.json')
    remap = dict(zip(old_measure['2']['addresses'], measure['2']['addresses']))
    for node in walk(asset['Exports'][2]['ScriptBytecode']):
        for key in ('CodeOffset', 'PushingAddress'):
            if key in node:
                node[key] = remap[node[key]]
    for index, targets in event_targets.items():
        addresses = measure[str(index)]['addresses']
        for instruction, destination in targets.items():
            asset['Exports'][index]['ScriptBytecode'][instruction]['CodeOffset'] = addresses[destination]
    asset['Exports'][30]['ScriptBytecode'][3]['CodeOffset'] = measure['30']['addresses'][-2]
    for fn in asset['Exports']:
        for node in walk(fn.get('ScriptBytecode', [])):
            if node.get('StackNode') == 3 and node.get('$type', '').endswith('EX_LocalFinalFunction, UAssetAPI'):
                p = node['Parameters'][0]
                p['Value'] = remap[p['Value']]
    path.write_text(json.dumps(asset, ensure_ascii=False), encoding='utf-8')
    subprocess.run([str(TOOL), str(ROOT), 'rewrite'], check=True)
    (ROOT / 'universal/build-plan.json').write_text(json.dumps({
        'profile': 'skin-only-current-role', 'imports': [controller, actor_getter, role_getter],
        'role_cache_checked_per_key': True, 'input_events': [15, 17],
        'on_screen_hint': False,
        'native_implementation_and_in_game_result_verified': False,
    }, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
