"""Offline regression checks of the decoded, repacked skin blueprint.

The small VM executes the shipped key-event control flow, with native game
calls mocked. It does not claim native mesh loading or in-game acceptance.
"""
import collections
import copy
import json
from pathlib import Path
from build_nte_all_roles import ROOT, read, walk

def normalize(value):
    if isinstance(value, dict):
        return {k: (None if k == 'ArrayInnerProp' and v == 0 else normalize(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value

def main():
    expected = read(ROOT / 'edited-functions.json')
    actual = read(ROOT / 'universal/validation-json/HT/Content/MOD/BP_Star.json')
    base = read(ROOT / 'universal/base-functions.json')
    measure = read(ROOT / 'universal-measure.json')
    for i, export in enumerate(expected['Exports']):
        if 'ScriptBytecode' in export:
            assert normalize(export['ScriptBytecode']) == normalize(actual['Exports'][i]['ScriptBytecode']), i
        else:
            assert export['Data'] == actual['Exports'][i]['Data'], i
    assert expected['Imports'] == actual['Imports']
    assert actual['NameMap'][:len(base['NameMap'])] == base['NameMap']
    for name in ['BP_UI', 'BP_TK', 'BP_SAVE', 'BP_Qiu', 'DT_FZ', 'S_FZ', 'SK_Qiu', 'SKEL_qiu']:
        old = read(ROOT / f'final-validation-json/HT/Content/MOD/{name}.json')
        new = read(ROOT / f'universal/validation-json/HT/Content/MOD/{name}.json')
        assert old['Exports'] == new['Exports'], name
    for i in list(range(3, 28)) + [29]:
        if i not in (15, 17):
            assert len(actual['Exports'][i]['ScriptBytecode']) == 2, i
    mesh = actual['Exports'][30]['ScriptBytecode']
    assert mesh[8]['ContextExpression']['StackNode'] == -107  # Original mesh refresh.
    assert mesh[8]['ContextExpression']['Parameters'][0] == mesh[4]['Variable']  # Captured old data.
    assert mesh[9]['ContextExpression']['Parameters'][2]['Variable']['New']['Path'] == ['InCharacterID']
    roles = collections.defaultdict(list)
    for row in read(ROOT / 'decoded-fashion-rows.json'):
        roles[row['player_id']].append(row)
    main_entries = [n['Parameters'][0]['Value'] for n in walk(actual['Exports'][17]['ScriptBytecode'])
                    if n.get('StackNode') == 3]
    outfit_entry = main_entries[0]
    simulations = 0
    for previous in [None, *roles]:
        for current in [None, 'unsupported', *roles]:
            for event in (15, 17):
                cached = copy.deepcopy(roles.get(previous, []))
                state = {'rows': cached, 'outfit': max(0, len(cached)-1), 'dye': 99, 'length': 99}
                applications = []
                body = actual['Exports'][event]['ScriptBytecode']
                address_to_index = {a: i for i, a in enumerate(measure[str(event)]['addresses'])}
                def kind(node): return node['$type'].split(',')[0].split('.')[-1]
                def evaluate(node):
                    token = kind(node)
                    if token == 'EX_IntConst': return node['Value']
                    if token == 'EX_Context': return evaluate(node['ContextExpression'])
                    if token == 'EX_FinalFunction':
                        if node['StackNode'] == -70: return len(state['rows'])
                        name = actual['Imports'][-node['StackNode']-1]['ObjectName']
                        if name == 'GetCurrentDisplayCharacterID': return current
                    if token == 'EX_StructMemberContext':
                        assert state['rows'], 'empty array read'
                        return state['rows'][0]['player_id']
                    if token == 'EX_CallMath':
                        left, right = map(evaluate, node['Parameters'])
                        if node['StackNode'] == -81: return left >= right
                        if node['StackNode'] == -78: return left == right
                    raise AssertionError(node)
                def apply():
                    assert state['rows'] and state['rows'][0]['player_id'] == current
                    assert 0 <= state['outfit'] < len(state['rows'])
                    count = state['rows'][state['outfit']]['dye_count']
                    assert 0 <= state['dye'] <= max(0, count-1)
                    state['length'] = count-1
                    applications.append((current, state['outfit'], state['dye']))
                pc = 0
                for _ in range(30):
                    node = body[pc]; token = kind(node)
                    if token == 'EX_Return': break
                    if token == 'EX_Jump' or (token == 'EX_JumpIfNot' and not evaluate(node['BooleanExpression'])):
                        pc = address_to_index[node['CodeOffset']]; continue
                    if token == 'EX_Let':
                        state['outfit' if pc == 3 else 'dye'] = 0
                    elif token == 'EX_LocalFinalFunction':
                        if node['StackNode'] == 31: apply()
                        elif node['Parameters'][0]['Value'] == outfit_entry:
                            if not state['rows'] or state['rows'][0]['player_id'] != current:
                                state['rows'] = copy.deepcopy(roles.get(current, []))
                            else:
                                state['outfit'] = (state['outfit']+1) % len(state['rows'])
                                state['dye'] = 0; apply()
                        else:
                            state['dye'] = 0 if state['dye'] >= state['length'] else state['dye']+1
                            apply()
                    pc += 1
                else: raise AssertionError('key helper did not terminate')
                assert bool(applications) == (current in roles)
                simulations += 1
    result = {'roles_in_table': len(roles), 'fashion_rows': sum(map(len, roles.values())),
              'key_event_simulations': simulations, 'packaged_ast_verified': True,
              'other_package_exports_unchanged': True, 'in_game_verified': False}
    (ROOT / 'universal/verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))

if __name__ == '__main__': main()
